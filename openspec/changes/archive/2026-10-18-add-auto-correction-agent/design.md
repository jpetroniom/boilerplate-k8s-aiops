# Design

## Context

Já existem (changes anteriores) o `Report`/`ReportStatus` com `queries.py`, `agents/analysis.py` (`build_model`, `build_agent`, `message_text`, config por env), a rota `/reports/{id}` com `render_report_detail(request, session, id, message, status_code)` e o template `report_detail.html`, e o `lifespan` que injeta o `sessionmaker` e recupera órfãos `EM_ANALISE`. O botão de `add-web-interface` já envia `POST /reports/{id}/fix` e a rota ainda não existe. O MCP Server expõe 23 tools (verificado), incluindo as de escrita. Motivação em proposal.md; requisitos em specs/auto-correction.

## Goals / Non-Goals

**Goals:**
- Transição de status atômica e decidida antes da resposta; correção fora do request.
- Reaproveitar o que o agente de análise já tem (modelo, construção do agente, extração de texto).
- Classificação do veredito e carga das tools testáveis sem LLM nem cluster.

**Non-Goals:**
- Whitelist, dry-run, restrição por namespace, aprovação extra, rollback, fila externa, polling/JS.

## Decisions

**1. Módulo `agents/correction.py`.** Contém `get_max_iterations()` (`CORRECTION_MAX_ITERATIONS`), o prompt do PRD (constante com `{report_markdown}` por `replace`), `parse_verdict`, `load_all_tools` e `correct(markdown, model=None, tools=None) -> str`. Reusa `build_model`, `build_agent`, `message_text` e `_positive_number` de `analysis.py`. Alternativa: parametrizar o `analyze`; rejeitada porque prompt, tools e saída diferem.

**2. Veredito.** `parse_verdict(text)` aplica regex multilinha `^[\s>*#-]*(CORRIGIDO|FALHA)\s*:\s*(.*)$` e usa a **primeira** ocorrência ancorada (o PRD não define empate; a primeira reflete a conclusão que o prompt exige logo no início, e um segundo token no corpo costuma ser citação). Sem match → `FALHA_CORRECAO` + warning. Devolve `(status, resumo)`.

**3. Todas as tools.** `load_all_tools` usa `MultiServerMCPClient({"k8s": {"transport": "http", "url": ...}})` sem filtro; falha de conexão levanta uma exceção própria tratada como `FALHA_CORRECAO`. O `recursion_limit` do LangGraph é ajustado como no agente de análise (`3 × limite + 5`).

**4. Dispatch.** A rota (em `web/router.py`) valida a existência (404), tenta `begin_correction(session, id)` — `UPDATE reports SET status='CORRIGINDO' WHERE id=:id AND status IN ('COMPLETO','FALHA_CORRECAO') RETURNING id` — e, se nenhuma linha voltar, responde 409 via `render_report_detail` (mensagem "Correção já em andamento" quando o status atual é `CORRIGINDO`; "Este relatório não permite correção no status atual" nos demais). Com sucesso, agenda `BackgroundTasks.add_task(run_correction, sessionmaker, report_id)` e responde `RedirectResponse(303)`. A tarefa abre sua própria sessão e recebe apenas o UUID. Alternativa: fila externa; fora do escopo do PRD.

**5. `run_correction`.** Carrega o relatório, chama `correct` e grava com `finish_correction(session, id, status, result)` — `UPDATE ... WHERE status='CORRIGINDO'` (condicional, para não sobrescrever uma recuperação) com `correction_result`. Qualquer exceção (MCP, API, banco na leitura) é logada e termina em `FALHA_CORRECAO` com o erro como resultado; erro ao gravar é logado com o texto da resposta (sem fallback em arquivo). Não propaga exceções para o servidor.

**6. Coluna e exibição.** Migration `0002` adiciona `correction_result TEXT NULL`. `report_detail.html` mostra a seção "Resultado da Correção" quando o campo existe, renderizada com o mesmo `render_markdown` sanitizado (a resposta do agente também deriva de texto do cluster).

**7. Startup.** `recover_orphans` ganha o par `CORRIGINDO → FALHA_CORRECAO` (função `recover_corrections`), chamada no `lifespan` junto da recuperação de `EM_ANALISE`.

**8. Configuração.** `CORRECTION_MAX_ITERATIONS` inválida usa 25 com warning; documentada no `CLAUDE.md` e no `.env.example`.

## Risks / Trade-offs

- [Prompt injection: o relatório deriva de texto do cluster e o agente tem escrita irrestrita, sem aprovação adicional] → aceito pelo PRD na v1; validar somente em cluster descartável; evoluir para whitelist/dry-run/aprovação.
- [Interface sem autenticação dispara correções para qualquer um na rede] → restringir por rede; documentado no `CLAUDE.md`.
- [Trabalho em background se perde no restart] → recuperação para `FALHA_CORRECAO` e reacionamento pelo botão.
- [Verificação imediata pode gerar falso `FALHA_CORRECAO` em pods ainda subindo] → limitação conhecida do PRD.
- [Sem chave da Anthropic a validação real do agente fica pendente] → testes com modelo falso e MCP real; execução com Claude registrada como pendente.

## Migration Plan

1. `uv run alembic upgrade head` aplica `0002`.
2. Subir o MCP Server e a aplicação com `ANTHROPIC_API_KEY`.

Rollback: `alembic downgrade -1` remove a coluna; a rota `/fix` deixa de existir ao reverter o código.
