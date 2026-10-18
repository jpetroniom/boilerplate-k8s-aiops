# CLAUDE.md

## Sobre o projeto

<!-- TODO: Descreva o proposito do seu agente aqui -->
Boilerplate para agente inteligente com FastAPI + LangChain + MCP Server.

## Comandos

```bash
# Instalar dependencias
uv sync

# Executar aplicacao
uv run uvicorn my_agent_app.main:app --host 0.0.0.0 --port 8000

# Subir o banco de dados (Docker so provisiona PostgreSQL + pgAdmin)
docker compose up -d

# Subir o MCP Server Kubernetes localmente via npx (transport HTTP/streamable, porta 3001)
# Requer Node.js/npx instalado e kubeconfig em ~/.kube/config
ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes

# Aplicar migrations do banco de dados (cria a tabela reports)
uv run alembic upgrade head
```

A aplicacao roda localmente via `uv`; o Docker e usado apenas para o banco de dados.
O MCP Server roda localmente via `npx` expondo transport HTTP, e o LangChain conecta por HTTP (`MCP_SERVER_URL`).

Testes: `uv run pytest` (pytest + pytest-asyncio, em `tests/`). Nao ha linter configurado ainda.

## Arquitetura

O codigo da aplicacao fica em `src/my_agent_app/` e e empacotado via hatchling (`pyproject.toml`).

- **Models** (`models/`) — `Report` (tabela `reports`: id UUID, markdown, status, `event_uids TEXT[]` com GIN, timestamps), enum `ReportStatus` e queries async (deduplicacao, relatorio do lote, swap condicional, recuperacao de orfaos). Migrations em `migrations/` (Alembic async)
- **Agents** (`agents/`) — `correction.py` (agente de correcao do PRD 004: prompt, `load_all_tools` sem filtro, `parse_verdict` e `run_correction` em background) e `analysis.py` (config, prompt, tools MCP de leitura, agente `create_agent` + `ModelCallLimitMiddleware`) e `report_parser.py` (Markdown da resposta -> um relatorio por problema)
- **Database** (`database.py`) — Engine async SQLAlchemy + asyncpg, configurado via `DATABASE_URL`
- **API** (`api/router.py`) — Health check
- **Interface Web** (`web/router.py`, `web/rendering.py`) — Pagina inicial, `GET /reports` (listagem por `created_at` decrescente, com badge de status e severidade lida do Markdown) e `GET /reports/{id}` (UUID; Markdown renderizado e sanitizado com `markdown` + `nh3`; botao "Executar correcao" so para `COMPLETO`/`FALHA_CORRECAO`, que envia `POST /reports/{id}/fix`; a rota valida (404/409), move para `CORRIGINDO` de forma atomica, responde 303 e roda `run_correction` via `BackgroundTasks`; o detalhe exibe o "Resultado da Correcao"). `render_report_detail(..., message, status_code)` reexibe o detalhe com uma mensagem (usada pelo PRD 004 no 409). Banco indisponivel responde 503. Templates Jinja2 em `src/my_agent_app/templates/`

- **Collector** (`collector/`) — Coleta periodica de eventos Warning do cluster, iniciada pelo `lifespan` do FastAPI. `client.py` (autenticacao in-cluster/kubeconfig e listagem em `asyncio.to_thread`), `transform.py` (recencia, filtro e contrato de saida; funcoes puras), `handler.py` (`EventHandler`: pipeline de analise do PRD 002 — dedup, relatorio `EM_ANALISE`, agente, relatorios por problema) e `loop.py` (`EventCollector`: coleta imediata no startup, marca d'agua em memoria e despacho fire-and-forget)

## Variaveis de ambiente

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| `ANTHROPIC_API_KEY` | Chave de API da Anthropic | (obrigatorio) |
| `DATABASE_URL` | Connection string PostgreSQL async | `postgresql+asyncpg://aiops:aiops123@localhost:5432/aiops_k8s` |
| `EVENT_COLLECTION_INTERVAL_MINUTES` | Intervalo da coleta de eventos Warning do cluster, em minutos (valor invalido usa o padrao e gera warning) | `3` |
| `AGENT_MODEL_PROVIDER` | Provedor do modelo dos agentes: `anthropic` (usa `ANTHROPIC_API_KEY`) ou `gemini` (usa `GOOGLE_API_KEY`, ha cota gratuita) | `anthropic` |
| `GOOGLE_API_KEY` | Chave de API do Gemini (so com `AGENT_MODEL_PROVIDER=gemini`) | (opcional) |
| `AGENT_MODEL_NAME` | Modelo dos agentes de analise e correcao | `claude-haiku-4-5` (`gemini-flash-latest` com `gemini`) |
| `AGENT_MAX_ITERATIONS` | Maximo de chamadas ao modelo por analise (invalido usa o padrao e gera warning) | `25` |
| `ANALYSIS_STALE_TIMEOUT_MINUTES` | Minutos ate um relatorio `EM_ANALISE` ser marcado `INCOMPLETO` na deduplicacao; manter acima do pior caso de runtime do agente | `30` |
| `CORRECTION_GRACE_MINUTES` | Carencia, em minutos, apos um relatorio virar `CORRIGIDO`: eventos dele que reaparecem nesse periodo sao ignorados (evita relatorio redundante); depois disso a reincidencia e reanalisada (invalido usa o padrao e gera warning) | `15` |
| `CORRECTION_MAX_ITERATIONS` | Maximo de chamadas ao modelo por correcao (invalido usa o padrao e gera warning) | `25` |
| `MCP_SERVER_URL` | Endpoint HTTP do MCP Server Kubernetes (via npx) | `http://localhost:3001/mcp` |

## Infraestrutura (docker-compose)

O Docker provisiona **apenas o banco de dados** (PostgreSQL + pgAdmin). A aplicacao e o MCP Server rodam localmente.

| Servico | Porta | Credenciais |
|---------|-------|-------------|
| PostgreSQL 17 | 5432 | aiops / aiops123 / aiops_k8s |
| pgAdmin | 5050 | admin@admin.com / admin123 |

## Acesso ao cluster Kubernetes (coletor de eventos)

O coletor usa a configuracao in-cluster quando disponivel e, caso contrario, o kubeconfig local (`~/.kube/config`). A identidade usada precisa de permissao de `list` em `events` do grupo `events.k8s.io`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: aiops-event-reader
rules:
  - apiGroups: ["events.k8s.io"]
    resources: ["events"]
    verbs: ["list"]
```

Sem essa permissao o log indica o erro 403 e o loop continua tentando a cada ciclo.

## Analise de causa raiz

Cada lote de eventos vira relatorios no PostgreSQL. Fluxo: dedup por `metadata.uid` -> relatorio `EM_ANALISE` -> agente (somente `kubectl_get`, `kubectl_describe` e `kubectl_logs` do MCP) -> um relatorio `COMPLETO` por problema. Falhas (MCP, API do Claude, resposta sem problemas) deixam o relatorio do lote `INCOMPLETO` e nunca chegam ao coletor. Eventos de relatorios `INCOMPLETO` sao reanalisados na recorrencia; os de `CORRIGIDO` tambem, exceto dentro da carencia pos-correcao (`CORRECTION_GRACE_MINUTES`). Pre-requisitos: `docker compose up -d`, `uv run alembic upgrade head`, MCP Server no ar e a chave do provedor (`ANTHROPIC_API_KEY`, ou `GOOGLE_API_KEY` com `AGENT_MODEL_PROVIDER=gemini`). Os PRDs foram escritos para o Claude; outros modelos funcionam, mas a qualidade do diagnostico e o formato da resposta podem variar.

**Seguranca:** a interface web nao tem autenticacao na v1. Restrinja o acesso por rede (VPN, ingress interno); qualquer pessoa com acesso a rede pode disparar correcoes no cluster (PRD 004).

## Correcao automatica

`POST /reports/{id}/fix` (botao "Executar correcao") aceita relatorios `COMPLETO` ou `FALHA_CORRECAO`, move para `CORRIGINDO` antes de responder (UPDATE condicional atomico; outro status ou clique repetido = 409) e executa o agente em background. O resultado vem do veredito `CORRIGIDO:`/`FALHA:` na resposta (sem veredito = `FALHA_CORRECAO`) e a resposta fica em `correction_result`. `CORRIGINDO` orfao no startup vira `FALHA_CORRECAO` e pode ser reacionado. Requer `ANTHROPIC_API_KEY` e o MCP Server no ar; aplique `uv run alembic upgrade head`.

**Atencao (v1):** o agente recebe TODAS as tools do MCP, inclusive escrita, sem whitelist, dry-run, restricao de namespace ou aprovacao adicional, e a interface nao tem autenticacao. O relatorio que ele executa deriva de texto do cluster processado por um LLM (risco de prompt injection com escrita no cluster). Use somente em cluster descartavel (ex.: kind) e restrinja o acesso a interface por rede.
