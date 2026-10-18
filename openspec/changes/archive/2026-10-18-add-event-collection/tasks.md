# Tasks

## 1. Setup

- [x] 1.1 Adicionar a dependência `kubernetes` (`uv add kubernetes`) e dependências de teste (`pytest`, `pytest-asyncio`) como grupo dev; verificar com `uv sync` e `uv run python -c "import kubernetes"`
- [x] 1.2 Criar a estrutura `collector/` (`client.py`, `transform.py`, `handler.py`, `loop.py`) e verificar que os módulos importam sem erro

## 2. Transformação e filtro (funções puras)

- [x] 2.1 Implementar a leitura de `EVENT_COLLECTION_INTERVAL_MINUTES` com padrão 3 e warning para valor inválido; verificar com testes para valor válido, não numérico, zero e negativo
- [x] 2.2 Implementar a recência (`series.last_observed_time` → `event_time` → `deprecated_last_timestamp`) e o descarte com warning de eventos sem timestamp; verificar com testes de evento recorrente, sem series, legado e sem timestamp
- [x] 2.3 Implementar o filtro por tipo Warning e por marca d'água (marca `None` = sem filtro); verificar com testes de eventos antigos/recentes e da marca ausente
- [x] 2.4 Implementar a transformação para o contrato de saída (`note` → `message`, `regarding` → `involved_object`, namespace vazio para cluster-scoped, timestamp ISO 8601); verificar o payload contra o contrato em teste

## 3. Cliente do cluster

- [x] 3.1 Implementar a autenticação (`load_incluster_config` com fallback para `load_kube_config`) e a listagem via `EventsV1Api.list_event_for_all_namespaces` com `field_selector="type=Warning"` dentro de `asyncio.to_thread`; verificar com teste usando cliente falso que o event loop não é bloqueado
- [x] 3.2 Tratar erros de conectividade e de RBAC (403) com log claro indicando a permissão necessária, sem lançar para o loop; verificar com testes que simulam `ApiException` 403 e erro de conexão

## 4. Handler e loop

- [x] 4.1 Criar `EventHandler` com `async def handle(events)` que imprime no stdout e captura suas próprias exceções; verificar com teste que uma exceção interna não se propaga
- [x] 4.2 Implementar o loop: coleta imediata no startup sem marca d'água, depois sleep e marca d'água, avançando só em coleta bem-sucedida e capturando o instante antes da listagem; verificar com testes de primeira coleta sem marca, avanço da marca e marca preservada após falha
- [x] 4.3 Implementar o despacho fire-and-forget com `set` de tasks vivas e `add_done_callback(discard)`, sem despachar lote vazio; verificar com teste de que o ciclo prossegue com um handler lento e de que lote vazio não chama o handler
- [x] 4.4 Integrar o loop ao `lifespan` do `main.py`, cancelando o loop e as tasks pendentes no shutdown; verificar subindo a aplicação, observando a coleta imediata nos logs e encerrando sem tasks pendentes

## 5. Documentação e integração

- [x] 5.1 Documentar `EVENT_COLLECTION_INTERVAL_MINUTES` e o ClusterRole necessário (`list` em `events` de `events.k8s.io`) no `CLAUDE.md`; verificar que o manifesto de exemplo aplica com `kubectl apply --dry-run=client`
## 6. Validação local com kind

Cenário: cluster kind local e os manifestos de `manifestos-k8s/`. `nginx.yaml` usa a imagem inexistente `ngin:latest` (gera `Failed`/`ErrImagePull`/`BackOff`); `kube-news.yaml` tem senha divergente entre banco e app (gera falhas e `BackOff` em 10 réplicas). Em todas as validações os eventos coletados devem aparecer no stdout da aplicação.

- [x] 6.1 Preparar o cluster kind (reutilizar o `kube-news` existente ou criar um novo), apontar o kubeconfig para ele e verificar com `kubectl cluster-info` e `kubectl get nodes`
- [x] 6.2 Aplicar `manifestos-k8s/nginx.yaml` e `manifestos-k8s/kube-news.yaml`, aguardar os pods falharem e verificar com `kubectl get events -A --field-selector type=Warning` que existem eventos Warning em mais de um recurso
- [x] 6.3 Subir a aplicação com `EVENT_COLLECTION_INTERVAL_MINUTES=1` e verificar que, no startup, a coleta imediata imprime no stdout os eventos Warning já existentes (sem aguardar o intervalo), cada um com `uid`, `type`, `reason`, `message`, `namespace`, `involved_object` e `timestamp`
- [x] 6.4 Comparar a saída do stdout com `kubectl get events -A --field-selector type=Warning -o json` e verificar que os UIDs impressos correspondem aos do cluster, que nenhum evento Normal aparece e que há eventos de pelo menos dois namespaces/recursos distintos
- [x] 6.5 Provocar um novo evento Warning (por exemplo, `kubectl rollout restart deployment/nginx` ou criar um pod com imagem inválida em outro namespace) e verificar que o ciclo seguinte imprime o novo evento, com a marca d'água evitando reimprimir os antigos
- [x] 6.6 Verificar o evento recorrente: confirmar que um evento com `series` (ex.: `BackOff` contínuo) volta a ser impresso quando o `series.lastObservedTime` avança, com o `timestamp` correspondente
- [x] 6.7 Verificar a resiliência: parar o kind (`docker stop`) e confirmar que o log registra o erro e o loop continua; religar e confirmar que a coleta retoma sem reiniciar a aplicação
- [x] 6.8 Verificar o RBAC: executar com um kubeconfig/ServiceAccount sem permissão de `list` em `events` e confirmar que o log indica a permissão necessária sem derrubar a aplicação
- [x] 6.9 Verificar o restart: reiniciar a aplicação e confirmar que a coleta inicial reimprime os Warning ainda vivos no cluster
- [x] 6.10 Remover os recursos de teste (`kubectl delete -f manifestos-k8s/`) e registrar o resultado das validações no PR ou na descrição da change

## Workflow follow-up

- Arquivar a change após a revisão e a aprovação do time de SRE.
