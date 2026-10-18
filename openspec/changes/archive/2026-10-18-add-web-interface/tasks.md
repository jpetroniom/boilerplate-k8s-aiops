# Tasks

## 1. Consultas e utilitários

- [x] 1.1 Adicionar `nh3` (`uv add nh3`) e implementar `list_reports`/`get_report` em `models/queries.py`; verificar com testes contra o PostgreSQL de ordenação por `created_at` decrescente, lista vazia e busca por id inexistente
- [x] 1.2 Implementar `extract_severity` e a renderização segura do Markdown (`markdown` + `nh3`) em módulo da web; verificar com testes de severidade presente/ausente, tabela, lista, código, link `https`, `<script>`, `onerror=` e `javascript:`

## 2. Rotas e templates

- [x] 2.1 Adicionar o link "Relatórios" ao cabeçalho de `base.html`, o mapa status → classe de badge e os estilos da listagem e do Markdown renderizado; verificar com teste de que o link aparece em `/` e em `/reports`
- [x] 2.2 Criar `GET /reports` e o template `reports.html` (ID, data, badge, severidade, link para o detalhe, mensagem de lista vazia); verificar com testes de ordem, badge por status, severidade ausente e lista vazia
- [x] 2.3 Criar `GET /reports/{id}` (`uuid.UUID`) e `report_detail.html` com Markdown renderizado, badge e botão "Executar correção" condicional a `COMPLETO`/`FALHA_CORRECAO`; verificar com testes por status, UUID inexistente (404) e id não UUID (422)
- [x] 2.4 Implementar `render_report_detail` com `message` e `status_code` para reexibir o detalhe com "Correção já em andamento"; verificar com teste que renderiza o detalhe com a mensagem e status 409
- [x] 2.5 Tratar falha do banco na listagem e no detalhe com `error.html` e 503 ("Banco de dados indisponível, tente novamente em instantes"); verificar com testes que simulam erro do SQLAlchemy nas duas rotas

## 3. Documentação

- [x] 3.1 Documentar no `CLAUDE.md` as rotas, a ausência de autenticação na v1 e a dependência do botão no PRD 004; verificar relendo o arquivo

## 4. Validação local

Cenário: PostgreSQL do compose com relatórios inseridos à mão (um por status) e a aplicação rodando. Não depende de `ANTHROPIC_API_KEY`.

- [x] 4.1 Aplicar `alembic upgrade head`, inserir um relatório por status com Markdown no formato do PRD 002 e subir a aplicação; verificar com `curl` que `GET /reports` retorna 200 com todos, ordenados e com os badges corretos
- [x] 4.2 Verificar com `curl` o detalhe de cada status (botão apenas em `COMPLETO` e `FALHA_CORRECAO`), um UUID inexistente (404), um id inválido (422) e um relatório com `<script>` no Markdown (sem script no HTML)
- [x] 4.3 Parar o PostgreSQL (`docker compose stop postgres`) e verificar 503 com a mensagem em `/reports` e `/reports/{id}`; religar e confirmar que as páginas voltam sem reiniciar a aplicação
- [x] 4.4 Abrir `/reports` e um detalhe em um navegador, conferir visualmente tabela e listas do Markdown, e registrar o resultado em `validation.md` da change
