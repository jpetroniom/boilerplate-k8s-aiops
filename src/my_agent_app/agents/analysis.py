import json
import logging
import os

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp import McpError
from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_MODELS = {"anthropic": DEFAULT_MODEL, "google_genai": "gemini-flash-latest"}
PROVIDER_ALIASES = {"gemini": "google_genai", "google": "google_genai", "google-genai": "google_genai"}
DEFAULT_MAX_ITERATIONS = 25
DEFAULT_STALE_TIMEOUT_MINUTES = 30
DEFAULT_MCP_SERVER_URL = "http://localhost:3001/mcp"
READ_TOOLS = ("kubectl_get", "kubectl_describe", "kubectl_logs")


class AnalysisAborted(Exception):
    """A analise nao pode ser executada (infra indisponivel); o relatorio do lote fica INCOMPLETO."""


def _positive_number(name: str, default: float, cast) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = cast(raw)
    except ValueError:
        value = 0
    if not 0 < value < float("inf"):
        logger.warning("%s invalido (%r); usando %s", name, raw, default)
        return default
    return value


def get_model_provider() -> str:
    raw = (os.getenv("AGENT_MODEL_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    return PROVIDER_ALIASES.get(raw, raw)


def get_model_name() -> str:
    return os.getenv("AGENT_MODEL_NAME") or DEFAULT_MODELS.get(get_model_provider(), DEFAULT_MODEL)


def get_max_iterations() -> int:
    return int(_positive_number("AGENT_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS, int))


def get_stale_timeout_minutes() -> float:
    return _positive_number("ANALYSIS_STALE_TIMEOUT_MINUTES", DEFAULT_STALE_TIMEOUT_MINUTES, float)


def get_mcp_server_url() -> str:
    return os.getenv("MCP_SERVER_URL") or DEFAULT_MCP_SERVER_URL


PROMPT = """Voce e um analista especializado em diagnostico Kubernetes. Sua funcao e investigar e identificar problemas usando as ferramentas disponiveis.

Voce recebeu os seguintes eventos Warning coletados do cluster:

{events}

## REGRAS
- Apenas diagnostica e sugere correcoes. NUNCA execute kubectl_patch, kubectl_apply ou kubectl_delete.
- Use APENAS os parametros documentados das tools.
- Investigue por PROBLEMA AGRUPADO, nao por evento individual.
- Se ja tiver causa raiz + evidencias suficientes, passe ao proximo problema.
- NUNCA chame a mesma ferramenta com os mesmos parametros duas vezes.
- Em **Eventos**, liste o uid de CADA evento recebido em exatamente um problema.

## COMO INVESTIGAR
Voce tem 3 ferramentas de leitura. Use-as IMEDIATAMENTE para coletar evidencias:
- **kubectl_get**: visao geral dos recursos (status, restarts, idade). Use `name` OU `labelSelector`, NUNCA ambos juntos.
- **kubectl_describe**: detalhes completos (eventos, conditions, configuracao).
- **kubectl_logs**: logs do container. Use `previous: true` para logs de execucao anterior.

Para cada problema recebido:
1. Chame kubectl_describe no recurso afetado para obter detalhes
2. Se necessario, chame kubectl_logs para ver erros da aplicacao
3. Com as evidencias coletadas, escreva o relatorio

## TRATAMENTO DE ERROS
- "name cannot be provided when a selector is specified" -> Use APENAS name OU labelSelector
- Se uma ferramenta falhar 2 vezes, registre o erro como evidencia e prossiga

## SEVERIDADE
- **CRITICO**: Pod/Deployment indisponivel, servico fora do ar
- **ALTO**: Restarts frequentes, OOMKilled, recursos esgotados
- **MEDIO**: Warnings recorrentes mas servico funcional
- **BAIXO**: Eventos informativos, problemas cosmeticos

## FORMATO DE RESPOSTA (Markdown)

# Relatorio de Diagnostico Kubernetes

## Resumo
| Total | Criticos | Altos | Medios | Baixos |
|-------|----------|-------|--------|--------|
| X     | X        | X     | X      | X      |

---

## Problema 1: [causa raiz resumida]
- **Severidade:** CRITICO | ALTO | MEDIO | BAIXO
- **Namespace:** namespace-afetado
- **Recursos Afetados:** pod1, deployment/nome
- **Eventos:** uid-evento-1, uid-evento-2

### Causa Raiz
Descricao clara do problema.

### Evidencias
- evidencia 1
- evidencia 2

### Solucao Recomendada
Acao especifica para corrigir.

### Comando Sugerido
kubectl patch deployment nome -n namespace --type=merge -p '{"spec":...}'

Repita a secao para cada problema. Responda APENAS com o relatorio markdown."""


def build_prompt(events: list[dict]) -> str:
    return PROMPT.replace("{events}", json.dumps(events, ensure_ascii=False, indent=2))


async def tolerate_mcp_errors(request, handler):
    """Devolve ao modelo o erro de protocolo do MCP (ex.: parametros invalidos) para ele tentar de novo.

    O adaptador so devolve ao modelo resultados com isError=True; um McpError (o servidor respondeu com um
    erro JSON-RPC) subiria e derrubaria a execucao inteira. Falhas de transporte nao sao McpError e continuam
    abortando a analise.
    """
    try:
        return await handler(request)
    except McpError as exc:
        logger.warning("Tool %s rejeitada pelo MCP Server: %s", request.name, exc)
        return CallToolResult(content=[TextContent(type="text", text=f"Erro da tool {request.name}: {exc}")], isError=True)


def build_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {"k8s": {"transport": "http", "url": get_mcp_server_url()}}, tool_interceptors=[tolerate_mcp_errors]
    )


def select_read_tools(tools) -> list:
    """Mantem somente as tools de leitura; aborta se alguma delas nao existir."""
    by_name = {tool.name: tool for tool in tools}
    missing = [name for name in READ_TOOLS if name not in by_name]
    if missing:
        raise AnalysisAborted(f"MCP Server nao expoe as tools de leitura: {missing}")
    return [by_name[name] for name in READ_TOOLS]


async def load_read_tools(client=None) -> list:
    client = client or build_mcp_client()
    try:
        tools = await client.get_tools()
    except Exception as exc:
        raise AnalysisAborted(f"MCP Server indisponivel: {exc}") from exc
    return select_read_tools(tools)


def build_agent(model, tools: list, max_iterations: int):
    return create_agent(
        model,
        tools,
        middleware=[ModelCallLimitMiddleware(run_limit=max_iterations, exit_behavior="end")],
    )


def build_model(model_name: str | None = None):
    """Modelo do agente. Claude por padrao; AGENT_MODEL_PROVIDER=gemini usa o Gemini (GOOGLE_API_KEY)."""
    return init_chat_model(model_name or get_model_name(), model_provider=get_model_provider(), max_retries=3)


def message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return content or ""


async def analyze(events: list[dict], model=None, tools: list | None = None) -> str:
    """Executa o agente sobre o lote e devolve o Markdown da resposta final."""
    max_iterations = get_max_iterations()
    tools = tools if tools is not None else await load_read_tools()
    agent = build_agent(model or build_model(), tools, max_iterations)
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": build_prompt(events)}]},
        config={"recursion_limit": 3 * max_iterations + 5},
    )
    return message_text(result["messages"][-1])
