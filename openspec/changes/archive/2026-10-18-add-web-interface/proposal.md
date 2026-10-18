# Proposal

## Why

Os relatórios de causa raiz (change `add-root-cause-analysis-agent`, PRD 002) ficam apenas no PostgreSQL: o operador precisa consultar o banco para ler o diagnóstico e não há ponto de acionamento para a correção (PRD 004). Esta change implementa o PRD 003, a interface web que dá visibilidade aos relatórios e o botão que aciona a correção.

## What Changes

- Adicionar `GET /reports`: listagem de todos os relatórios por `created_at` decrescente, com ID, data, status (badge) e severidade lida do Markdown, cada item levando ao detalhe.
- Adicionar `GET /reports/{id}` (`id` validado como UUID): status e Markdown completo renderizado em HTML.
- Exibir o botão "Executar correção" (formulário `POST /reports/{id}/fix`, endpoint do PRD 004) apenas para relatórios `COMPLETO` ou `FALHA_CORRECAO`.
- Tratar erros: lista vazia ("Nenhum relatório encontrado"), banco indisponível (`error.html` com 503) e relatório inexistente (404 informativo).
- Sanitizar o HTML gerado a partir do Markdown, já que o conteúdo vem de um LLM alimentado por texto do cluster.
- Adicionar o link "Relatórios" ao cabeçalho de `base.html` e estilos para o Markdown renderizado.
- Oferecer à rota de correção (PRD 004) a forma de reexibir o detalhe com a mensagem "Correção já em andamento" quando responder 409.

## Capabilities

### New Capabilities
- `report-web-interface`: listagem e detalhe web dos relatórios de análise, com acionamento condicional da correção e tratamento de erros.

### Modified Capabilities

(nenhuma)

## Impact

- Código: `src/my_agent_app/web/router.py` (rotas), `templates/` (`reports.html`, `report_detail.html`, `base.html`, `error.html`), `models/queries.py` (listagem e busca por id).
- Dependências: `markdown` já declarada; adicionar `nh3` para sanitização.
- API: novas rotas `GET /reports` e `GET /reports/{id}`; o botão depende de `POST /reports/{id}/fix` (PRD 004), que ainda não existe.
- Documentação: `CLAUDE.md` (módulo web) e aviso de que a v1 não tem autenticação.
- Fora do escopo: autenticação, filtros, paginação, métricas agregadas, execução da correção.
