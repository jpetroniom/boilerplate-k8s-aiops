# Design

## Context

O `EventHandler` (`collector/handler.py`) hoje imprime o lote no stdout e o `EventCollector` o despacha de forma fire-and-forget (change `add-event-collection`). O projeto já tem `sqlalchemy` + `asyncpg`, `alembic` declarado (sem configuração), `langchain`, `langchain-anthropic` e `langchain-mcp-adapters` (0.3.0), mas `models/` e `agents/` estão vazios. O `lifespan` cria um engine e o `sessionmaker` próprios em `app.state`; `database.py` também define um engine e um `Base` de módulo. Motivação em proposal.md; requisitos em specs/root-cause-analysis e specs/analysis-reports.

## Goals / Non-Goals

**Goals:**
- Pipeline `dedup → insert-first → agente → parse → swap` isolado do coletor, com lógica pura (parse, config) testável sem banco, LLM ou cluster.
- Falhas da análise nunca chegam ao coletor.
- Ponto de entrada estável para os PRDs 003 e 004 (modelo `Report` e seus status).

**Non-Goals:**
- Trava atômica de concorrência na deduplicação, saída estruturada do agente, limite de reanálises, deduplicação por `involvedObject` + `reason`.
- Interface web e correção (PRDs 003 e 004).

## Decisions

**1. Módulos.** `models/report.py` (modelo + enum de status), `models/queries.py` (dedup, insert-first, swap, recuperação), `agents/analysis.py` (config, tools, agente, prompt), `agents/report_parser.py` (parse do Markdown, puro) e `collector/handler.py` (`EventHandler` que orquestra). Alternativa: tudo no handler; rejeitada porque o parse e as queries precisam de testes isolados.

**2. Banco via Alembic.** Configuração assíncrona (`alembic init -t async`) usando `get_database_url()` e `Base.metadata`; migration inicial cria `reports` com `event_uids TEXT[]` e índice GIN. Alternativa: `create_all` no startup; rejeitada porque os PRDs 003/004 evoluirão o esquema (`correction_result`). `status` é `String` validada por enum Python (evita migration a cada novo status); `updated_at` com `onupdate`.

**3. Sessão do handler.** O `EventHandler` recebe o `sessionmaker` do `lifespan` (injeção em `EventCollector(handler=...)`) e abre uma `AsyncSession` por operação. Alternativa: usar `database.async_session` global; rejeitada para manter um único engine, descartado no shutdown.

**4. Deduplicação em uma consulta.** Primeiro marca `EM_ANALISE` estagnados como `INCOMPLETO` (`UPDATE ... WHERE status='EM_ANALISE' AND created_at < now() - timeout`), depois seleciona os uids do lote presentes em relatórios ativos (`event_uids && :uids`, usando o GIN) e filtra o lote em memória. Falha do banco: loga e descarta o lote. O insert-first usa o mesmo `commit` curto, antes de chamar o agente (sem trava atômica, risco aceito no PRD).

**5. Agente com `create_agent`.** `ChatAnthropic(model=AGENT_MODEL_NAME, max_retries=3)`; tools de `MultiServerMCPClient({"k8s": {"transport": "http", "url": MCP_SERVER_URL}}).get_tools()` filtradas por nome para `{kubectl_get, kubectl_describe, kubectl_logs}`; `ModelCallLimitMiddleware(run_limit=N, exit_behavior="end")`. O cliente e o agente são criados por análise (a conexão MCP é barata e uma falha vira `INCOMPLETO` sem estado global). Se alguma das três tools não existir, a análise é abortada com erro claro. O prompt do PRD fica como constante em `agents/analysis.py`, com `{events}` preenchido por `json.dumps` do lote.

**6. Parse tolerante.** `report_parser` divide a resposta em blocos `## Problema N`, extrai severidade, namespace, recursos, uids de **Eventos** e guarda o texto do bloco (mais o cabeçalho de resumo) como Markdown do relatório. Uids que não pertencem ao lote são ignorados; uids do lote ausentes geram warning. Resposta sem blocos = inconclusiva. Alternativa: saída estruturada; fica como evolução (decisão D1 do PRD).

**7. Swap condicional.** Uma transação: `SELECT ... FOR UPDATE` do relatório do lote; se `status != 'EM_ANALISE'`, aborta e descarta o resultado; senão deleta o relatório do lote e insere os relatórios por problema como `COMPLETO`. Persistência com retry/backoff (3 tentativas); falha definitiva loga o erro com o Markdown, sem arquivo.

**8. Resultado inconclusivo/abortado.** Marca o relatório do lote `INCOMPLETO` com um UPDATE condicional (`WHERE status='EM_ANALISE'`), mantendo os `event_uids` do lote para rastreabilidade.

**9. Configuração.** Funções de leitura de env (`AGENT_MAX_ITERATIONS`, `ANALYSIS_STALE_TIMEOUT_MINUTES`) validam e usam o padrão com warning, no mesmo padrão de `get_interval_minutes`. A `ANTHROPIC_API_KEY` ausente aborta a análise com log (não derruba a aplicação).

**10. Recuperação no startup.** O `lifespan` executa o `UPDATE` dos `EM_ANALISE` órfãos para `INCOMPLETO` antes de iniciar o coletor; se o banco estiver indisponível, loga e segue.

## Risks / Trade-offs

- [Dedup sem trava atômica pode analisar duas vezes em despachos simultâneos] → insert-first estreita a janela; trava fica para depois.
- [Parse depende do formato Markdown do LLM] → parser tolerante, warning para uid não mapeado, resposta sem problemas vira `INCOMPLETO`.
- [`ANALYSIS_STALE_TIMEOUT_MINUTES` menor que o pior caso do agente descarta resultado válido] → swap condicional e padrão de 30 min; documentar.
- [Reanálise de `INCOMPLETO` a cada recoleta gasta tokens] → aceito no PRD.
- [Sem `ANTHROPIC_API_KEY` não há validação ponta a ponta com o modelo real] → testes com modelo e MCP falsos; validação real registrada como pendente se a chave não existir.
- [Reiniciar a aplicação durante o desenvolvimento recoleta e reanalisa] → absorvido pela dedup.

## Migration Plan

1. `docker compose up -d` para o PostgreSQL.
2. `uv run alembic upgrade head` cria `reports`.
3. Subir o MCP Server (`npx`) e a aplicação com `ANTHROPIC_API_KEY`.

Rollback: `alembic downgrade -1` remove a tabela; o coletor volta a funcionar com o handler anterior.
