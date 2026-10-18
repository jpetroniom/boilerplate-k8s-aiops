# Proposal

## Why

Os eventos Warning já são coletados (change `add-event-collection`, PRD 001), mas o `EventHandler` apenas os imprime: o diagnóstico de causa raiz continua manual (30 min a 2 h), dependente da experiência do operador e sem registro padronizado. Esta change implementa o PRD 002, que transforma cada lote de eventos em relatórios de diagnóstico persistidos, base para a interface web (PRD 003) e para a correção automática (PRD 004).

## What Changes

- Substituir o `EventHandler` placeholder por um pipeline de análise: deduplicar os eventos por `metadata.uid`, criar o relatório `EM_ANALISE` (insert-first), investigar e persistir os relatórios por problema.
- Criar o modelo `Report` (id UUID, markdown, status, `event_uids` `TEXT[]` com índice GIN, `created_at`, `updated_at`) e a criação da tabela via Alembic (o projeto ainda não tem Alembic configurado).
- Deduplicar por existência de relatório ativo (`EM_ANALISE`, `COMPLETO`, `CORRIGINDO`, `FALHA_CORRECAO`) que contenha o uid; reanalisar eventos de relatórios `CORRIGIDO` ou `INCOMPLETO`.
- Marcar como `INCOMPLETO` os relatórios `EM_ANALISE` estagnados (`ANALYSIS_STALE_TIMEOUT_MINUTES`, padrão 30) na consulta de deduplicação, e os órfãos no startup.
- Criar o agente de análise com LangChain (`create_agent`) e `ChatAnthropic` (`AGENT_MODEL_NAME`, padrão `claude-haiku-4-5`, `max_retries=3`), conectado ao MCP Server Kubernetes por `langchain-mcp-adapters` (`MCP_SERVER_URL`), com **somente** as tools `kubectl_get`, `kubectl_describe` e `kubectl_logs`.
- Limitar as iterações com `AGENT_MAX_ITERATIONS` (padrão 25) via `ModelCallLimitMiddleware(exit_behavior="end")`.
- Fazer o parse da resposta Markdown em um relatório por problema (campo **Eventos** mapeia os uids) e substituir o relatório do lote por eles, na mesma transação, **somente se ainda estiver `EM_ANALISE`**.
- Falhas (MCP indisponível, API do Claude, banco, resposta sem problemas) deixam o relatório do lote `INCOMPLETO` e nunca se propagam ao coletor.

## Capabilities

### New Capabilities
- `root-cause-analysis`: deduplicação dos eventos recebidos, investigação de causa raiz por agente com tools somente de leitura e tratamento de falhas da análise.
- `analysis-reports`: relatórios de diagnóstico persistidos por problema, com ciclo de vida de status e recuperação de análises estagnadas ou interrompidas.

### Modified Capabilities

(nenhuma; o `EventHandler` é o ponto de extensão definido na change `add-event-collection`, cujo contrato de entrada não muda)

## Impact

- Código: `src/my_agent_app/agents/` (agente e parse), `src/my_agent_app/models/` (modelo e queries), `collector/handler.py` (novo `EventHandler`), `main.py` (lifespan: recuperação no startup e injeção do sessionmaker), Alembic (novo).
- Dependências: nenhuma nova obrigatória (`langchain`, `langchain-anthropic`, `langchain-mcp-adapters` e `asyncpg` já estão no projeto); `alembic` já declarado.
- Configuração: `ANTHROPIC_API_KEY` (obrigatória para a análise), `AGENT_MODEL_NAME`, `AGENT_MAX_ITERATIONS`, `ANALYSIS_STALE_TIMEOUT_MINUTES`, `MCP_SERVER_URL`; documentar no `CLAUDE.md` e no `.env.example`.
- Infra: PostgreSQL (docker compose), MCP Server Kubernetes via `npx` (transport HTTP) e acesso ao cluster.
- Fora do escopo: interface web (PRD 003), correção (PRD 004), histórico de eventos brutos, trava atômica de concorrência na deduplicação, saída estruturada do agente.
