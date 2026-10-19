# Boilerplate: FastAPI + LangChain Agent + MCP

Boilerplate para criar agentes inteligentes com:

- **FastAPI** (async) como backend
- **LangChain** como framework de agentes (Claude por padrao; Gemini opcional)
- **MCP Server Kubernetes** para o agente ler e alterar o cluster
- **Coleta de eventos Warning** do cluster, analise de causa raiz e correcao automatica (PRDs em `docs/prds/`)
- **PostgreSQL** + SQLAlchemy async para persistencia
- **Alembic** para migrations
- **Jinja2** para interface web com dark theme

## Como usar

### 1. Copiar o boilerplate

```bash
cp -r boilerplate/ ~/projetos/meu-novo-agente/
cd ~/projetos/meu-novo-agente/
```

### 2. Renomear o package

Renomeie `my_agent_app` para o nome do seu projeto em todos os arquivos:

```bash
# Renomear diretorio
mv src/my_agent_app src/meu_agente

# Substituir em todos os arquivos
find . -type f -name "*.py" -o -name "*.toml" -o -name "*.ini" -o -name "*.md" -o -name "*.html" | \
  xargs sed -i 's/my_agent_app/meu_agente/g; s/my-agent-app/meu-agente/g; s/My Agent App/Meu Agente/g'
```

### 3. Configurar ambiente

```bash
cp .env.example .env
# Edite .env com suas configuracoes (ANTHROPIC_API_KEY, etc)
```

Para usar o Gemini (ha cota gratuita) em vez do Claude, defina `AGENT_MODEL_PROVIDER=gemini` e `GOOGLE_API_KEY`. Os prompts foram escritos para o Claude; com outros modelos a qualidade do diagnostico e o formato da resposta podem variar. A lista completa de variaveis esta no `CLAUDE.md`.

### 4. Subir o banco de dados

O Docker provisiona **apenas o banco** (PostgreSQL + pgAdmin):

```bash
docker compose up -d
```

### 5. Instalar dependencias e aplicar as migrations

```bash
uv sync
uv run alembic upgrade head
```

### 6. Subir o MCP Server (via npx)

O MCP Server Kubernetes roda localmente via `npx` expondo transport HTTP (streamable). Requer **Node.js/npx** instalado e um **kubeconfig** valido em `~/.kube/config`:

```bash
ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes
```

O agente LangChain conecta a esse servidor por HTTP em `http://localhost:3001/mcp` (`MCP_SERVER_URL`).

### 7. Executar

A aplicacao roda localmente via `uv`:

```bash
uv run uvicorn meu_agente.main:app --host 0.0.0.0 --port 8000
```

Abra `http://localhost:8000/reports` para ver os relatorios. O coletor roda junto com a aplicacao (coleta imediata no startup e depois a cada `EVENT_COLLECTION_INTERVAL_MINUTES`) e usa o kubeconfig local ou a configuracao in-cluster.

## Fluxo

1. **Coleta** (PRD 001): lista os eventos Warning do cluster periodicamente.
2. **Analise** (PRD 002): um agente com tools MCP somente de leitura investiga o lote e grava um relatorio `COMPLETO` por problema (status `EM_ANALISE` durante a analise, `INCOMPLETO` se falhar). Eventos de relatorio `CORRIGIDO` recem-concluido ficam em carencia (`CORRECTION_GRACE_MINUTES`) para nao gerar relatorio redundante.
3. **Interface** (PRD 003): `GET /reports` e `GET /reports/{id}` exibem os relatorios (Markdown sanitizado).
4. **Correcao** (PRD 004): o botao "Executar correcao" (`POST /reports/{id}/fix`) aciona um agente com **todas** as tools do MCP, inclusive escrita; o resultado vira `CORRIGIDO` ou `FALHA_CORRECAO`.

> **Seguranca:** a interface nao tem autenticacao e o agente de correcao escreve no cluster sem whitelist, dry-run nem aprovacao. Use somente em cluster descartavel (ex.: kind) e restrinja o acesso por rede.

## Estrutura

```
src/my_agent_app/
├── main.py              # FastAPI + lifespan
├── database.py          # SQLAlchemy async engine
├── api/router.py        # Health check
├── web/                 # Rotas (/, /reports, /reports/{id}, /fix) e renderizacao do Markdown
├── templates/           # Templates HTML (dark theme)
├── agents/              # Agentes de analise e de correcao, parser dos relatorios
├── collector/           # Coleta de eventos Warning, transformacao e pipeline de analise
└── models/              # Report, status e queries
migrations/              # Alembic async (reports, correction_result)
tests/                   # pytest (PostgreSQL real, modelo e tools falsos)
docs/prds/               # PRDs 001-004
openspec/                # Specs e changes arquivadas (com validation.md)
```

Testes: `uv run pytest`.

## Stack

| Tecnologia | Uso |
|------------|-----|
| FastAPI + Uvicorn | Backend async |
| SQLAlchemy 2.0 + asyncpg | ORM async com PostgreSQL |
| Alembic | Migrations |
| LangChain (Claude ou Gemini) | Framework de agentes IA |
| MCP Server Kubernetes | Tools de leitura e escrita no cluster |
| Jinja2 | Interface web server-side |
| Docker Compose | Banco de dados local (PostgreSQL + pgAdmin) |
| Node.js + npx | Runtime do MCP Server Kubernetes (transport HTTP) |
| UV + hatchling | Package manager + build system |
