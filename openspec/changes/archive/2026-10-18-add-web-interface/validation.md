# Resultado das validações locais

Ambiente: PostgreSQL 17 do compose, `alembic upgrade head`, aplicação em `uvicorn`, relatórios inseridos à mão (um por status, com Markdown no formato do PRD 002). Testes automatizados: 100 passando (`uv run pytest`), incluindo `tests/test_web.py` (rotas, badges, botão, 404, 422, 503, sanitização) e `tests/test_rendering.py`.

| Tarefa | Resultado |
|--------|-----------|
| 4.1 | `GET /reports` 200 com todos os relatórios, do mais recente ao mais antigo, com o badge correto por status e severidade (ou "—" quando ausente) |
| 4.2 | Botão "Executar correção" apenas em `COMPLETO` e `FALHA_CORRECAO`; UUID inexistente 404 ("Relatório não encontrado"); `/reports/abc` 422; no relatório com `<script>`, `onerror=` e `javascript:` nada disso chega ao HTML, e tabela e bloco de código são renderizados |
| 4.3 | Com o PostgreSQL parado: 503 com "Banco de dados indisponível, tente novamente em instantes" em `/reports` e `/reports/{id}`, `/api/health` segue 200; ao religar as páginas voltam a 200 sem reiniciar a aplicação |
| 4.4 | Conferência visual em Chromium headless (capturas de tela): cabeçalho com "Relatórios", tabela da listagem com badges, detalhe com títulos, lista, tabela, bloco de código e botão |

## Observações

- O formulário do botão envia `POST /reports/{id}/fix`, rota do PRD 004 que ainda não existe; o clique só funcionará após aquela change.
- Os horários são exibidos em UTC (coluna rotulada).
- Ao subir a aplicação, relatórios `EM_ANALISE` pré-existentes viram `INCOMPLETO` (recuperação de órfãos do PRD 002), então o relatório `EM_ANALISE` da validação foi inserido com a aplicação já no ar.
