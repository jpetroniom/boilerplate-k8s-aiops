# Resultado das validações locais

Ambiente: kind `kube-news`, PostgreSQL 17 do compose, MCP Server Kubernetes via `npx` (HTTP, porta 3001). Testes automatizados: 73 passando (`uv run pytest`), incluindo 12 de queries e 13 do handler contra um PostgreSQL real e o agente com modelo e tools falsos.

| Tarefa | Resultado |
|--------|-----------|
| 1.1–1.3 | Alembic async conecta; migration `0001` cria `reports` com GIN em `event_uids`; `downgrade`/`upgrade` OK |
| 3.3 | Relatório `EM_ANALISE` inserido à mão virou `INCOMPLETO` no startup (log de warning) |
| 5.1 | O MCP expõe 23 tools (incluindo `kubectl_apply`, `kubectl_patch`, `kubectl_delete`); apenas `kubectl_get`, `kubectl_describe` e `kubectl_logs` chegam ao agente |
| 5.2 | Validada com o **Gemini** (`gemini-flash-latest`, resolvido para `gemini-3.8-flash`), no lugar do Claude. kind com `nginx` (imagem inexistente) e `kubenews` (senha do banco divergente), MCP real, aplicação com `AGENT_MODEL_PROVIDER=gemini`. O lote de 6 eventos criou o relatório `EM_ANALISE` e, ao final, 2 relatórios `COMPLETO` com 3 `event_uids` cada. O ciclo seguinte (1 min) abriu um novo lote `EM_ANALISE` com 7 uids novos, que terminou `INCOMPLETO` por `429 RESOURCE_EXHAUSTED` (cota gratuita), tratado como o spec manda: erro logado e aplicação de pé |
| 5.3 | Validada com o **Gemini**. Os 2 relatórios têm severidade, namespace, recursos, eventos, causa raiz, evidências, solução recomendada e comando sugerido. O diagnóstico do `kubenews` foi correto (`DB_PASSWORD=pg123` no app contra `POSTGRES_PASSWORD=pg1234` no Postgres, com a evidência do log) e o do `nginx` também (imagem `ngin:latest`). Nenhum uid já vinculado a relatório `COMPLETO` foi reanalisado no ciclo seguinte (0 em comum) |
| 5.4 | Com o MCP fora do ar: log "MCP Server indisponivel", 1 relatório `INCOMPLETO` com os 120 uids do lote e aplicação de pé. Sem a chave (MCP no ar): análise abortada com o erro de autenticação e mesmo resultado `INCOMPLETO` |

## Observações sobre a validação com o Gemini

- O Claude real **não** foi exercitado (sem `ANTHROPIC_API_KEY`); as tarefas 5.2 e 5.3 foram validadas com outro modelo, via `AGENT_MODEL_PROVIDER=gemini` (`GOOGLE_API_KEY`). A qualidade do diagnóstico e o formato da resposta com o Claude podem diferir.
- A cota gratuita do Gemini pode retornar `429`; o lote fica `INCOMPLETO` e é reanalisado na recorrência dos eventos.
- A validação revelou que um erro de protocolo do MCP (ex.: parâmetro inválido) derrubava a execução do agente em vez de voltar ao modelo; corrigido por um interceptor (`tolerate_mcp_errors`), em commit posterior.
