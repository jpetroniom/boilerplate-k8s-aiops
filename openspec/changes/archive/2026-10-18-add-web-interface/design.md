# Design

## Context

`web/router.py` tem só a rota `/` e instancia `Jinja2Templates`; `base.html` define o cabeçalho, os estilos de badge (`badge-processing` a `badge-execution-failed`) e `error.html` aceita `status_code` e `message`. O `sessionmaker` fica em `app.state` (criado no `lifespan`); `models/` já tem `Report`, `ReportStatus` e `queries.py` (change `add-root-cause-analysis-agent`). `markdown` já é dependência. Motivação em proposal.md; requisitos em specs/report-web-interface.

## Goals / Non-Goals

**Goals:**
- Rotas finas, com consulta isolada em `queries.py` e lógica pura (severidade, renderização) testável sem banco.
- HTML do Markdown seguro por construção.
- Ponto de integração claro com o PRD 004.

**Non-Goals:**
- Autenticação, paginação, filtros, polling/JS, seção "Resultado da Correção" (coluna `correction_result` pertence ao PRD 004).

## Decisions

**1. Sessão por request via dependência.** Uma dependência FastAPI abre `AsyncSession` a partir de `request.app.state.sessionmaker`. Erros `SQLAlchemyError`/`OSError` viram resposta 503 com `error.html`. Alternativa: handler global de exceções; rejeitada para não mascarar erros de outras rotas.

**2. Consultas em `queries.py`.** `list_reports(session)` seleciona `id, status, created_at, markdown` ordenado por `created_at DESC`; `get_report(session, id)`. Sem paginação, como definido no PRD.

**3. Severidade lida do Markdown.** Função pura `extract_severity(markdown)` com regex sobre `**Severidade:**` (mesmo padrão do `report_parser`); devolve `None` quando ausente (lote `INCOMPLETO`), exibido como "—". Alternativa: coluna `severity`; rejeitada porque o PRD define a leitura do Markdown e evita migration.

**4. Markdown seguro.** `markdown.markdown(text, extensions=["tables", "fenced_code"])` seguido de `nh3.clean` com lista de tags/atributos permitidos (títulos, listas, tabelas, `code`/`pre`, `a[href]` com esquemas `http`/`https`/`mailto`). Alternativa: `html.escape` antes de converter; rejeitada porque quebra `>` e `&` legítimos. Nova dependência: `nh3`.

**5. Badge por mapa.** Dicionário status → classe CSS como filtro/global Jinja, mantendo `base.html` como dono dos estilos.

**6. Botão como formulário.** `<form method="post" action="/reports/{id}/fix">` renderizado só se o status estiver em `{COMPLETO, FALHA_CORRECAO}`; sem JS. Até o PRD 004 existir a rota responde 404/405, o que é documentado e coberto por teste da condição de exibição, não do endpoint.

**7. Mensagem de 409.** `web/router.py` expõe `render_report_detail(request, session, report_id, message=None, status_code=200)`; o detalhe recebe `message` opcional. A rota de correção do PRD 004 chama essa função com "Correção já em andamento" e `status_code=409`. O template já suporta o parâmetro nesta change.

**8. Cabeçalho.** `base.html` ganha o link "Relatórios" e os estilos da listagem e do Markdown (tabelas, `pre`, `code`) dentro do bloco de estilos comum ou de `extra_style`.

## Risks / Trade-offs

- [Sem autenticação, qualquer um com acesso à rede lê os relatórios e (com o PRD 004) dispara correções] → documentar no `CLAUDE.md`; restringir por rede.
- [Listagem sem paginação cresce com o histórico] → aceito na v1; carrega `markdown` completo só para extrair severidade → mitigação futura: coluna `severity`.
- [Sanitização remove HTML que o relatório precisaria] → lista de tags cobre o formato do prompt; ajustar se necessário.
- [Botão aponta para rota inexistente até o PRD 004] → ordem de entrega 003 → 004; validação do clique fica para o PRD 004.

## Open Questions

- Nenhuma que mude specs ou tarefas.
