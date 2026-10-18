# Design

## Context

O `main.py` já tem um `lifespan` que cria o engine e o sessionmaker; `collector/` existe apenas como pacote vazio. O SDK `kubernetes` é síncrono, e a aplicação roda via uvicorn em um único event loop. Motivação e escopo em proposal.md; requisitos em specs/event-collection.

## Goals / Non-Goals

**Goals:**
- Loop de coleta isolado em `collector/`, com ciclo de vida atrelado ao `lifespan`.
- Lógica de filtro e transformação pura e testável sem cluster.
- Ponto de extensão estável (`EventHandler`) para o PRD 002.

**Non-Goals:**
- Deduplicação, persistência e análise (PRD 002).
- Marca d'água persistente: ela fica em memória e a recuperação pós-restart vem da coleta inicial sem marca d'água.
- Limite de concorrência dos handlers e dedup atômica: pertencem ao PRD 002, que é quem consome o lote.

## Decisions

**1. Módulos separados por responsabilidade.** `client` (autenticação e listagem), `transform` (recência, filtro, contrato; funções puras), `handler` (`EventHandler`) e `loop` (agendamento e despacho). Alternativa: um arquivo único; rejeitada porque a parte pura precisa de testes sem I/O.

**2. `EventsV1Api.list_event_for_all_namespaces` com `field_selector="type=Warning"`.** Reduz o payload no servidor. O filtro de tipo continua também em memória como proteção, e o filtro de recência é só em memória, porque a API não filtra por `series.lastObservedTime`. Alternativa: `CoreV1Api`; rejeitada porque o PRD define `events.k8s.io/v1` e o contrato mapeia `note`/`regarding`. Os campos do SDK são snake_case (`series.last_observed_time`, `deprecated_last_timestamp`).

**3. Chamadas síncronas via `asyncio.to_thread`.** Evita bloquear o event loop. Alternativa: `kubernetes_asyncio`; rejeitada por ser dependência diferente da definida no PRD.

**4. Marca d'água em memória, com primeira coleta sem marca.** `watermark = None` no início significa "sem filtro de recência". Após cada coleta bem-sucedida, ela passa a ser o instante de início da listagem (capturado antes da chamada), de modo que eventos emitidos durante a listagem não se percam; o overlap eventual é absorvido pela dedup do PRD 002. Alternativa: usar o maior timestamp visto nos eventos; rejeitada porque não avança em ciclos vazios e depende do relógio do apiserver.

**5. Primeira coleta antes do primeiro sleep.** O loop é `coletar -> dormir`, não `dormir -> coletar`, eliminando o atraso inicial.

**6. Despacho com conjunto de tasks vivas.** `asyncio.create_task` mantém só referência fraca; o loop guarda as tasks em um `set` e usa `add_done_callback(discard)`. No shutdown, o `lifespan` cancela o loop e as tasks pendentes. O `EventHandler.handle` captura suas próprias exceções.

**7. Configuração lida na criação do loop.** `EVENT_COLLECTION_INTERVAL_MINUTES` é validado em uma função própria que devolve 3 com warning em caso de valor inválido.

**8. Falha de autenticação ou carga do kubeconfig no startup não derruba a aplicação.** O erro é logado e a coleta é tentada de novo a cada ciclo, para que a API e a interface web continuem de pé.

## Risks / Trade-offs

- [Evento one-shot cujo despacho falhe depois da marca d'água avançar é perdido] → risco aceito no PRD; a coleta inicial sem marca cobre restarts enquanto o evento viver no cluster (TTL padrão de 1h).
- [Cada restart recoleta todos os Warning vivos, gerando reanálise de INCOMPLETO/CORRIGIDO no PRD 002, com custo de tokens em desenvolvimento com `--reload`] → absorvido pela dedup; avaliar carência pós-CORRIGIDO no PRD 002.
- [Despachos sem limite de concorrência podem acumular handlers] → tratar com semáforo no `EventHandler` do PRD 002.
- [403 recorrente gera log de erro a cada ciclo] → aceitar na v1; reduzir o nível após a primeira ocorrência é melhoria futura.
- [Relógio local diferente do apiserver] → o overlap resultante é absorvido pela dedup.
