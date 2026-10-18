# Tasks

## 1. Banco

- [x] 1.1 Adicionar `correction_result` ao `Report` e criar a migration `0002`; verificar com `alembic upgrade head`, `\d reports`, `downgrade` e `upgrade`
- [x] 1.2 Implementar em `models/queries.py` `begin_correction` (UPDATE condicional atômico), `finish_correction` (condicional a `CORRIGINDO`) e `recover_corrections`; verificar com testes contra o PostgreSQL de transição, status inválidos, duas chamadas concorrentes (apenas uma vence) e recuperação de órfãos

## 2. Agente de correção

- [x] 2.1 Implementar `get_max_iterations` (`CORRECTION_MAX_ITERATIONS`) e `parse_verdict` em `agents/correction.py`; verificar com testes de valor válido/inválido, veredito após prosa, com marcadores Markdown, menção no meio de frase e ausência de veredito (warning)
- [x] 2.2 Implementar `load_all_tools` (sem filtro) e `correct` com o prompt do PRD, reutilizando `build_model`/`build_agent`; verificar com testes de que as tools de escrita são mantidas, MCP indisponível levanta erro, o relatório vai ao prompt e o limite de iterações encerra sem veredito
- [x] 2.3 Implementar `run_correction` (carrega o relatório, chama o agente, classifica e grava resultado/status, trata MCP/API/banco sem propagar); verificar com testes de CORRIGIDO, FALHA, sem veredito, MCP indisponível e erro da API

## 3. Web

- [x] 3.1 Implementar `POST /reports/{id}/fix`: 404, 409 via `render_report_detail` com a mensagem adequada, 303 e `BackgroundTasks` com sessão própria; verificar com testes de cada status, relatório inexistente, redirect, execução em segundo plano e duas requisições simultâneas
- [x] 3.2 Exibir a seção "Resultado da Correção" (sanitizada) em `report_detail.html` apenas quando houver resultado; verificar com testes com e sem `correction_result` e com HTML malicioso no resultado
- [x] 3.3 Chamar `recover_corrections` no `lifespan` junto da recuperação de `EM_ANALISE`; verificar subindo a aplicação com um relatório `CORRIGINDO` e confirmando `FALHA_CORRECAO`

## 4. Documentação

- [x] 4.1 Documentar no `CLAUDE.md` e no `.env.example` `CORRECTION_MAX_ITERATIONS`, o fluxo de correção e o aviso de acesso irrestrito ao cluster e de risco de prompt injection; verificar relendo os arquivos

## 5. Validação local

Cenário: kind descartável, PostgreSQL do compose, MCP Server via `npx`, aplicação rodando. Os passos que chamam o Claude exigem `ANTHROPIC_API_KEY`; sem ela, registrar como pendente em vez de marcar.

- [x] 5.1 Com modelo roteirizado e o MCP real, aplicar `manifestos-k8s/nginx.yaml` no kind, inserir um relatório `COMPLETO` com o comando de correção e executar `POST /reports/{id}/fix`; verificar `CORRIGINDO` imediato, 303, a ação aplicada no cluster, o status final e a seção "Resultado da Correção"
- [x] 5.2 Verificar o 409 (clique repetido durante `CORRIGINDO` e status inválidos), o 404 e que a página exibe a mensagem
- [x] 5.3 Verificar a resiliência: MCP parado durante o fix resulta em `FALHA_CORRECAO`; reiniciar a aplicação com `CORRIGINDO` órfão resulta em `FALHA_CORRECAO` e o botão volta a aparecer
- [x] 5.4 Executar a correção com o Claude real sobre o `nginx` com imagem inexistente e confirmar `CORRIGIDO` com o recurso saudável (requer `ANTHROPIC_API_KEY`)
- [x] 5.5 Remover os recursos de teste e registrar o resultado em `validation.md` da change
