import logging
import re
import uuid

from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from my_agent_app.agents.analysis import (
    _positive_number,
    build_agent,
    build_model,
    get_mcp_server_url,
    message_text,
)
from my_agent_app.models import ReportStatus, queries

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 25
_VERDICT = re.compile(r"^[\s>*#-]*(CORRIGIDO|FALHA)\s*:\s*(.*)$", re.MULTILINE)


class CorrectionAborted(Exception):
    """A correcao nao pode ser executada (infra indisponivel); o relatorio fica FALHA_CORRECAO."""


def get_max_iterations() -> int:
    return int(_positive_number("CORRECTION_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS, int))


PROMPT = """Voce e um agente AIOps especializado em correcao de problemas em clusters Kubernetes.
Voce opera no padrao ReAct: para cada acao, primeiro raciocine, depois execute, depois observe o resultado.

Abaixo esta o relatorio de diagnostico com as correcoes recomendadas:

{report_markdown}

## REGRAS
- Execute as correcoes descritas no relatorio. NAO corrija problemas pre-existentes sem relacao com o relatorio (esses sim estao fora de escopo).
- POREM, se a SUA propria correcao introduzir um novo erro ou deixar o recurso pior, isso NAO esta fora de escopo: foi voce que causou e voce DEVE corrigir ate o recurso ficar saudavel.
- Ao editar um container existente (image, env, resources, probes) com kubectl_patch, use patchType "strategic" OU kubectl_apply. NUNCA use merge patch simples sobre a lista `containers`: o merge substitui o container inteiro e APAGA os campos nao citados (env, image, probes, ports).
- NUNCA delete namespaces, PersistentVolumeClaims ou recursos em kube-system.
- NUNCA escale deployments para 0 replicas (a menos que o relatorio peca explicitamente).
- Se um recurso nao existir mais, registre e passe ao proximo passo.
- NUNCA repita a mesma chamada de ferramenta com os mesmos parametros: se falhar, leia a mensagem de erro e tente uma abordagem diferente.
- Se o mesmo passo falhar 2 vezes mesmo com abordagens diferentes, registre o erro e siga adiante.

## COMO CORRIGIR (padrao ReAct)
Para CADA passo de correcao do relatorio, siga este ciclo:

### 1. RACIOCINAR
Antes de agir, responda mentalmente:
- Qual e o estado atual esperado do recurso?
- Qual acao vou executar e por que?
- O que pode dar errado?

### 2. VERIFICAR ESTADO ATUAL
Use kubectl_get ou kubectl_describe para confirmar que o problema ainda existe.
- Se o problema ja foi resolvido, registre como "Ja resolvido" e pule para o proximo.

### 3. EXECUTAR A CORRECAO
Use a ferramenta apropriada (kubectl_patch, kubectl_apply, kubectl_scale, kubectl_rollout, etc.).
Ao alterar um container, prefira patchType "strategic" ou kubectl_apply para PRESERVAR os demais campos (env, image, probes, ports). Nunca remova variaveis de ambiente, a imagem ou probes que ja existiam, a menos que o relatorio peca.

### 4. VALIDAR O RESULTADO
Apos executar, use kubectl_get ou kubectl_describe para verificar de fato a SAUDE do recurso afetado:
- O recurso esta no estado esperado?
- O pod esta Running E Ready (sem CrashLoopBackOff, sem restarts subindo, sem novos erros em eventos/logs)?
- A sua correcao NAO introduziu nenhum erro novo?

Se a validacao mostrar que a SUA correcao causou um novo erro ou deixou o pod quebrado (ex.: saiu de ImagePullBackOff mas entrou em CrashLoop porque o patch apagou variaveis de ambiente), NAO trate isso como "fora de escopo": foi a sua acao que causou, entao CORRIJA. Volte ao ciclo (raciocine -> verifique -> execute -> valide) ate o recurso ficar saudavel, respeitando o limite de iteracoes.

So considere o problema CORRIGIDO quando o recurso afetado estiver comprovadamente saudavel (pod Running e Ready, Deployment Available, sem novos erros). Se, depois das suas tentativas, o recurso continuar quebrado, responda FALHA explicando o que ficou pendente.

## FORMATO DE RESPOSTA
IMPORTANTE: A PRIMEIRA LINHA da sua resposta DEVE ser exatamente uma destas (sem markdown, sem emoji, sem formatacao):
- CORRIGIDO: [resumo de uma linha]
- FALHA: [resumo de uma linha]

Depois da primeira linha, use o formato abaixo:

## Acoes Executadas

### Problema 1: [titulo do problema do relatorio]
- **Status:** Corrigido | Falha | Ja resolvido | Recurso nao encontrado
- **Acao:** o que foi feito
- **Validacao:** resultado da verificacao pos-correcao

### Problema 2: ...

## Resumo
- Corrigidos: X
- Falhas: X
- Ja resolvidos: X
- Total: X"""


def build_prompt(report_markdown: str) -> str:
    return PROMPT.replace("{report_markdown}", report_markdown)


def parse_verdict(text: str) -> tuple[ReportStatus, str]:
    """Veredito `CORRIGIDO:`/`FALHA:` ancorado no inicio de uma linha (a primeira ocorrencia vale)."""
    match = _VERDICT.search(text or "")
    if match is None:
        logger.warning("Resposta do agente de correcao sem veredito (CORRIGIDO:/FALHA:); tratando como FALHA_CORRECAO")
        return ReportStatus.FALHA_CORRECAO, ""
    status = ReportStatus.CORRIGIDO if match.group(1) == "CORRIGIDO" else ReportStatus.FALHA_CORRECAO
    return status, match.group(2).strip()


async def load_all_tools(client=None) -> list:
    """Todas as tools do MCP, inclusive as de escrita (acesso irrestrito na v1, por decisao do PRD)."""
    client = client or MultiServerMCPClient({"k8s": {"transport": "http", "url": get_mcp_server_url()}})
    try:
        return await client.get_tools()
    except Exception as exc:
        raise CorrectionAborted(f"MCP Server indisponivel: {exc}") from exc


async def correct(report_markdown: str, model=None, tools: list | None = None) -> str:
    """Executa o agente de correcao e devolve a resposta final."""
    max_iterations = get_max_iterations()
    tools = tools if tools is not None else await load_all_tools()
    agent = build_agent(model or build_model(), tools, max_iterations)
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": build_prompt(report_markdown)}]},
        config={"recursion_limit": 3 * max_iterations + 5},
    )
    return message_text(result["messages"][-1])


async def run_correction(sessionmaker: async_sessionmaker, report_id: uuid.UUID, correct_fn=correct) -> None:
    """Tarefa em background: abre a propria sessao e nunca propaga excecoes."""
    try:
        async with sessionmaker() as session:
            report = await queries.get_report(session, report_id)
        if report is None:
            logger.error("Relatorio %s nao encontrado ao iniciar a correcao", report_id)
            return
        response = await correct_fn(report.markdown)
        status, summary = parse_verdict(response)
        logger.info("Correcao do relatorio %s terminou como %s: %s", report_id, status.value, summary)
    except Exception as exc:
        logger.error("Correcao do relatorio %s abortada (%s: %s)", report_id, type(exc).__name__, exc)
        status, response = ReportStatus.FALHA_CORRECAO, f"FALHA: correcao abortada ({type(exc).__name__}: {exc})"
    try:
        async with sessionmaker() as session:
            await queries.finish_correction(session, report_id, status, response)
    except Exception:
        logger.exception("Nao foi possivel gravar o resultado da correcao %s. Resposta:\n%s", report_id, response)
