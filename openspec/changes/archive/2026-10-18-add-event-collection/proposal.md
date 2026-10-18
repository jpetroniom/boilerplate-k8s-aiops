# Proposal

## Why

A descoberta de eventos problemáticos no cluster Kubernetes é manual (`kubectl get events`), o que atrasa a detecção e aumenta a indisponibilidade. Esta change implementa a coleta automática de eventos Warning (PRD 001), primeira etapa do pipeline AIOps; sem ela, o PRD 002 (análise de causa raiz) não tem entrada.

## What Changes

- Adicionar a dependência `kubernetes` (Python SDK) ao projeto.
- Criar, em `collector/`, um loop assíncrono iniciado e cancelado pelo `lifespan` do FastAPI, com intervalo configurável por `EVENT_COLLECTION_INTERVAL_MINUTES` (padrão 3).
- Listar eventos `events.k8s.io/v1` de todos os namespaces, filtrando `type=Warning`, via `asyncio.to_thread`.
- Filtrar por recência com marca d'água em memória, usando a precedência `series.lastObservedTime` → `eventTime` → `deprecatedLastTimestamp`.
- Executar a **primeira coleta imediatamente no startup, sem marca d'água** (todos os Warning ainda vivos no cluster), para recuperar eventos não tratados após restart; o loop normal passa a usar a marca d'água depois dela.
- Transformar os eventos no contrato de saída (dicts desacoplados do SDK) e despachá-los em lote, de forma fire-and-forget, a um `EventHandler` placeholder que imprime no stdout.
- Manter referências fortes às tasks de despacho para que não sejam coletadas pelo GC, e cancelá-las no shutdown.
- Tratar falhas de conectividade e RBAC com log, sem interromper o loop.

## Capabilities

### New Capabilities
- `event-collection`: coleta periódica de eventos Warning do cluster, filtro de recência, contrato de saída e despacho assíncrono ao handler.

### Modified Capabilities

(nenhuma)

## Impact

- Código: `src/my_agent_app/collector/` (novo), `src/my_agent_app/main.py` (lifespan).
- Dependências: `kubernetes` em `pyproject.toml` / `uv.lock`.
- Configuração: nova variável `EVENT_COLLECTION_INTERVAL_MINUTES`; documentar no `CLAUDE.md`.
- Infra: a aplicação precisa de acesso ao cluster (kubeconfig ou in-cluster) e de um ClusterRole com `list` em `events` (`events.k8s.io`).
- Fora do escopo: persistência de eventos, deduplicação (PRD 002), eventos Normal, multi-cluster.
