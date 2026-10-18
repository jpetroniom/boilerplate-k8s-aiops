# Tasks

## 1. Banco de dados

- [x] 1.1 Configurar o Alembic assíncrono (`alembic.ini`, `migrations/env.py` usando `get_database_url()` e `Base.metadata`); verificar com `uv run alembic current` contra o PostgreSQL do compose
- [x] 1.2 Criar o modelo `Report` e o enum de status em `models/`, e a migration inicial com `event_uids TEXT[]` e índice GIN; verificar com `alembic upgrade head`, `\d reports` no `psql` e `downgrade`/`upgrade` sem erro
- [x] 1.3 Implementar as queries em `models/queries.py` (marcar estagnados, filtrar uids ativos, criar relatório do lote, marcar INCOMPLETO condicional, swap condicional, recuperação de órfãos); verificar com testes contra o PostgreSQL cobrindo evento novo, em tratamento, CORRIGIDO, INCOMPLETO, estagnado e swap abortado

## 2. Agente de análise

- [x] 2.1 Implementar a leitura de `AGENT_MODEL_NAME`, `AGENT_MAX_ITERATIONS` e `ANALYSIS_STALE_TIMEOUT_MINUTES` com padrões e warning para valor inválido; verificar com testes de valor válido, não numérico, zero e negativo
- [x] 2.2 Implementar o parse da resposta (`agents/report_parser.py`): resumo, blocos de problema, severidade, namespace, recursos, uids de Eventos; verificar com testes de dois problemas, resposta vazia, uid fora do lote e uid do lote não referenciado
- [x] 2.3 Implementar o carregamento das tools MCP filtradas para `kubectl_get`, `kubectl_describe` e `kubectl_logs`; verificar com teste que tools de escrita não passam e que a falta de uma tool de leitura aborta
- [x] 2.4 Implementar o agente (`create_agent` + `ChatAnthropic(max_retries=3)` + `ModelCallLimitMiddleware(exit_behavior="end")`) com o prompt do PRD; verificar com modelo falso que o loop executa uma tool e respeita o limite

## 3. Pipeline do handler

- [x] 3.1 Implementar o `EventHandler` (dedup → insert-first → agente → parse → swap ou INCOMPLETO) com captura de todas as exceções; verificar com testes de lote duplicado, falha do MCP, falha da API, banco indisponível, resposta sem problemas e relatório tornado INCOMPLETO durante a análise
- [x] 3.2 Implementar a persistência com retry/backoff e log do Markdown na falha definitiva; verificar com teste que simula falha do banco nas tentativas
- [x] 3.3 Integrar ao `lifespan`: recuperação de órfãos no startup e `EventCollector(handler=EventHandler(sessionmaker))`; verificar subindo a aplicação com um relatório `EM_ANALISE` pré-inserido e confirmando a mudança para INCOMPLETO

## 4. Documentação

- [x] 4.1 Documentar no `CLAUDE.md` e no `.env.example` as variáveis `AGENT_MODEL_NAME`, `AGENT_MAX_ITERATIONS`, `ANALYSIS_STALE_TIMEOUT_MINUTES` e o comando de migration; verificar relendo os arquivos

## 5. Validação local

Cenário: kind local, PostgreSQL do compose, MCP Server via `npx` e os manifestos de `manifestos-k8s/`. Os passos que chamam o Claude exigem `ANTHROPIC_API_KEY`; sem ela, registrar o passo como pendente em vez de marcá-lo.

- [x] 5.1 Subir PostgreSQL e MCP Server (`ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes`) e verificar que a lista de tools do MCP contém `kubectl_get`, `kubectl_describe` e `kubectl_logs`
- [ ] 5.2 Aplicar `manifestos-k8s/` no kind e verificar que a aplicação cria o relatório `EM_ANALISE` e depois relatórios `COMPLETO` com `event_uids` no banco
- [ ] 5.3 Verificar que os relatórios seguem a estrutura (resumo, severidade, causa raiz, evidências, solução, comando sugerido) e que o próximo ciclo não reanalisa os uids já vinculados
- [x] 5.4 Verificar a resiliência: parar o MCP Server e confirmar relatório `INCOMPLETO` e aplicação de pé; reiniciar a aplicação com um `EM_ANALISE` órfão e confirmar `INCOMPLETO`
- [x] 5.5 Remover os recursos de teste e registrar o resultado das validações em `validation.md` da change
