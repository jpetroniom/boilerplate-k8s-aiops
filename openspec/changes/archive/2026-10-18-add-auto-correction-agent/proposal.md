# Proposal

## Why

Os relatórios de causa raiz (PRD 002) trazem a solução e o comando sugerido, mas a correção continua manual: o operador lê o relatório, interpreta os passos e executa comandos no cluster, o que aumenta o MTTR e abre espaço para erro de execução. Esta change implementa o PRD 004, o agente que executa a correção a partir do botão da interface (PRD 003) e verifica se o problema foi resolvido.

## What Changes

- Adicionar `POST /reports/{id}/fix`: valida o relatório (404 se não existir, 409 se o status não for `COMPLETO`/`FALHA_CORRECAO`), faz a transição atômica para `CORRIGINDO` no próprio request e responde `303` para o detalhe; a correção roda em background.
- Criar o agente de correção (LangChain `create_agent`, `AGENT_MODEL_NAME`, `max_retries=3`) conectado ao MCP Server Kubernetes com **todas** as tools (acesso irrestrito, decisão do PRD), limitado por `CORRECTION_MAX_ITERATIONS` (padrão 25).
- Injetar o Markdown do relatório no prompt do PRD; o agente executa os passos e valida a saúde do recurso afetado, corrigindo o que a própria correção quebrar.
- Classificar o resultado pelo veredito `CORRIGIDO:` / `FALHA:` em qualquer linha da resposta (sem veredito = `FALHA_CORRECAO` com warning) e atualizar o status (`CORRIGINDO` → `CORRIGIDO` ou `FALHA_CORRECAO`).
- Persistir a resposta do agente em nova coluna `correction_result` (migration) e exibi-la no detalhe do relatório, na seção "Resultado da Correção".
- Marcar como `FALHA_CORRECAO`, no startup, os relatórios `CORRIGINDO` órfãos; falhas de MCP ou da API do Claude também resultam em `FALHA_CORRECAO`.
- Usar `render_report_detail` (change `add-web-interface`) para responder 409 com mensagem na página.

## Capabilities

### New Capabilities
- `auto-correction`: acionamento da correção a partir de um relatório, execução pelo agente com acesso irrestrito ao cluster, verificação pós-correção, classificação do resultado e recuperação de correções interrompidas.

### Modified Capabilities

(nenhuma; o detalhe do relatório e o fluxo de status foram definidos em changes ainda não arquivadas, então o comportamento novo fica nesta capacidade)

## Impact

- Código: `agents/correction.py` (novo), `web/router.py` (rota `/fix`), `models/` (coluna `correction_result`, queries de transição e resultado), `main.py` (recuperação no startup), template `report_detail.html`, migration Alembic.
- Dependências: nenhuma nova.
- Configuração: `CORRECTION_MAX_ITERATIONS`; reutiliza `AGENT_MODEL_NAME`, `MCP_SERVER_URL` e `ANTHROPIC_API_KEY`; documentar no `CLAUDE.md` e no `.env.example`.
- Segurança: o agente altera o cluster sem whitelist, dry-run, restrição de namespace ou aprovação adicional, e a interface não tem autenticação; o Markdown que ele recebe deriva de texto do cluster processado por um LLM (risco de prompt injection com escrita no cluster). Aceito na v1 pelo PRD; deve ser exercitado apenas em cluster descartável.
- Fora do escopo: whitelist, dry-run, restrição por namespace, aprovação humana extra, rollback automático, polling/JS na página.
