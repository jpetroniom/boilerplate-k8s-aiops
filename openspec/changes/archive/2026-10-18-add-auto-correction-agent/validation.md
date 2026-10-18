# Resultado das validações locais

Ambiente: kind descartável (`kube-news`), PostgreSQL 17 do compose, MCP Server Kubernetes real via `npx` (HTTP, porta 3001) e a aplicação rodando. Testes automatizados: 141 passando (`uv run pytest`), incluindo `tests/test_correction.py`, as consultas de transição (inclusive 8 chamadas concorrentes, uma vence) e as rotas `/fix` em `tests/test_web.py`.

**Modelo roteirizado:** sem `ANTHROPIC_API_KEY`, a aplicação foi iniciada por um lançador de validação que troca somente `build_model` por um modelo com respostas fixas (consulta o deployment, aplica o `kubectl_patch` strategic, consulta os pods e responde `CORRIGIDO:`). O MCP, o cluster, o banco, a rota, o background e as transições de status são reais; o raciocínio do LLM não foi exercitado.

| Tarefa | Resultado |
|--------|-----------|
| 5.1 | Deployment `nginx` em `ImagePullBackOff` (`ngin:latest`). `POST /reports/{id}/fix` em relatório `COMPLETO`: 303 para `/reports/{id}`, status `CORRIGINDO` logo após a resposta, `CORRIGIDO` ao final, imagem no cluster alterada para `nginx:latest` pelo `kubectl_patch` via MCP, e o detalhe exibe o badge `CORRIGIDO`, a seção "Resultado da Correção" e nenhum botão. O pod novo ainda estava em `ContainerCreating` quando o agente respondeu (limitação conhecida do PRD: verificação imediata, sem aguardar estabilização) |
| 5.2 | `POST` em `CORRIGIDO` 409 ("Este relatório não permite correção no status atual"); em `CORRIGINDO` 409 ("Correção já em andamento"); em `INCOMPLETO` 409; relatório inexistente 404 ("Relatório não encontrado"); 6 `POST` simultâneos em relatório `COMPLETO`: um 303 e cinco 409, com uma única correção executada (log) |
| 5.3 | Com o MCP parado: `POST` 303, relatório `FALHA_CORRECAO` com "MCP Server indisponivel" em `correction_result`, aplicação viva. Reinício com um `CORRIGINDO` órfão: warning no log, status `FALHA_CORRECAO` e botão "Executar correção" de volta |
| 5.4 | Validada com o **Gemini** (`gemini-flash-latest`), no lugar do Claude. `nginx` em `ImagePullBackOff` (`ngin:latest`), relatório `COMPLETO` gerado pela análise. `POST /reports/{id}/fix`: 303, `CORRIGINDO`, e `CORRIGIDO` em ~30 s; imagem no cluster alterada para `nginx:latest`, pod novo `1/1 Running` com 0 reinícios, resultado na seção "Resultado da Correção". A primeira tentativa terminou `FALHA_CORRECAO`: o Gemini enviou `patchData` como texto e o MCP respondeu `McpError -32600`, que derrubava a execução. Com o interceptor `tolerate_mcp_errors` o erro volta ao modelo, que corrige a chamada na tentativa seguinte (warning no log) e conclui |

## Observações sobre a validação com o Gemini

- O Claude real **não** foi exercitado (sem `ANTHROPIC_API_KEY`); a 5.4 foi validada com outro modelo, via `AGENT_MODEL_PROVIDER=gemini`. A conduta do agente com o Claude pode diferir.
- Nesta execução a aplicação rodou com `KUBECONFIG` inexistente apenas para o coletor não consumir a cota gratuita; o agente de correção usa o MCP Server, que enxerga o cluster normalmente.
- Falso `FALHA_CORRECAO` por verificação imediata (limitação do PRD) não ocorreu: o agente aguardou o rollout concluir.
