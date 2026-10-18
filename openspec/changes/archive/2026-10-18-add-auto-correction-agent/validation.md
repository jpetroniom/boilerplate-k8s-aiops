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

## Execução ponta a ponta com o Gemini

Fluxo completo em um único processo, sem intervenção entre as etapas: kind com `manifestos-k8s/` (10 pods `kubenews` em `CrashLoopBackOff` por senha de banco divergente e `nginx` com imagem inexistente, 26 eventos Warning), PostgreSQL, MCP Server real e a aplicação com `AGENT_MODEL_PROVIDER=gemini` (`gemini-3.5-flash`, resolvido para `gemini-3.6-flash`).

| Etapa | Resultado |
|-------|-----------|
| Coleta imediata | 26 eventos Warning no startup, em um lote |
| Análise (PRD 002) | Relatório `EM_ANALISE` (26 uids) por ~85 s, depois 2 relatórios `COMPLETO`: `kubenews` (20 eventos, falha de autenticação no banco) e `nginx` (6 eventos, imagem `ngin:latest`), ambos `CRITICO`, com todas as seções |
| Interface (PRD 003) | `/reports` lista os dois; o detalhe do `nginx` renderiza o Markdown e exibe "Executar correção" |
| Correção (PRD 004) | `POST /reports/{id}/fix`: 303, `CORRIGINDO`, `CORRIGIDO` em ~45 s; imagem `nginx:latest`, pod `1/1 Running`; seção "Resultado da Correção" na página. O Gemini repetiu o `patchData` como texto, o MCP recusou e o interceptor devolveu o erro ao modelo, que corrigiu a chamada |

### Limitações observadas

- **Cota gratuita:** o limite diário do plano gratuito é por modelo (20 requisições/dia/projeto). Uma tentativa anterior com `gemini-3.8-flash` terminou `INCOMPLETO` com `429`; a execução acima usou outro modelo, com cota própria.
- **Relatório redundante após a correção:** no ciclo seguinte (3 min), 3 dos 6 uids do relatório `CORRIGIDO` do `nginx` foram recoletados e, como o spec manda reanalisar eventos de relatório `CORRIGIDO`, geraram um novo relatório `COMPLETO` sobre um problema já resolvido (o agente anotou, nas evidências, que o deployment já estava saudável). O botão "Executar correção" voltaria a aparecer nesse relatório. É a consequência prevista no `design.md` do PRD 002 ("avaliar carência pós-CORRIGIDO"), e uma carência ou o descarte de eventos anteriores à correção reduziria o ruído.
- Os 10 pods do `kubenews` seguiram em `CrashLoopBackOff` (a correção do `kubenews` não foi tentada nesta execução).

## Correção do `kubenews` com o Gemini (caso adversarial)

Cenário: os 10 pods do `kubenews` em falha porque `DB_PASSWORD=pg123` no deployment e `POSTGRES_PASSWORD=pg1234` no Postgres. O deployment tem um container com imagem, porta e 4 variáveis (`DB_DATABASE`, `DB_PASSWORD`, `DB_USERNAME`, `DB_HOST`). O relatório `COMPLETO` (inserido à mão com o diagnóstico que o Gemini já havia gerado, para poupar a cota) sugeria deliberadamente um **`merge patch`** sobre a lista `containers` com só `DB_PASSWORD`, que apagaria a imagem, a porta e as demais variáveis. Modelo: `gemini-3-flash-preview`.

| Verificação | Resultado |
|-------------|-----------|
| `POST /reports/{id}/fix` | 303, `CORRIGINDO`, `CORRIGIDO` em ~55 s |
| Cirurgia da correção | Só `DB_PASSWORD` mudou (`pg123` → `pg1234`); imagem `fabricioveronez/kube-news:v1`, porta 8080 e as outras 3 variáveis preservadas; 1 container, 10 réplicas |
| Saúde | 10/10 pods `1/1 Running`, deployment `10/10` disponível |
| Regra do prompt | O agente não seguiu o `merge patch` do relatório e usou patch estratégico, como o prompt manda |
| Erros de tool | 4 chamadas rejeitadas pelo MCP (`patchData` como texto em `kubectl_patch`, uma falha em `kubectl_apply` e outra em `kubectl_generic`); o interceptor devolveu cada erro ao modelo, que tentou outra abordagem e concluiu |

Limitação: foi um único caso; o comportamento do agente com outros modelos (inclusive o Claude) pode diferir, e o PRD mantém o acesso irrestrito ao cluster sem whitelist nem dry-run.
