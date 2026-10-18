# Resultado das validações locais (kind)

Cluster: kind `kube-news` (v1.34.0), recriado para a validação. Manifestos: `manifestos-k8s/` (`nginx.yaml` e `kube-news.yaml`), removidos ao final. Testes automatizados: 31 passando (`uv run pytest`).

| Tarefa | Resultado |
|--------|-----------|
| 6.1 | Cluster criado; `kubectl cluster-info` e `kubectl get nodes` OK |
| 6.2 | Eventos Warning em vários recursos (10 pods `kubenews`, `nginx`, pods de `kube-system`) |
| 6.3 | Coleta imediata no startup imprimiu 42 eventos com `uid`, `type`, `reason`, `message`, `namespace`, `involved_object` e `timestamp` |
| 6.4 | Os 42 UIDs impressos são idênticos aos de `kubectl get events -A --field-selector type=Warning -o json`; só Warning; namespaces `default`, `kube-system`, `local-path-storage` |
| 6.5 | `rollout restart deployment/nginx`: os 3 UIDs novos foram impressos nos ciclos seguintes; eventos antigos sem mudança não foram reimpressos |
| 6.6 | Evento `events.k8s.io/v1` criado com `series` (o kubelet só emite o formato legado); ao avançar `series.lastObservedTime` com a aplicação rodando, o mesmo UID foi reimpresso com `timestamp` igual ao novo `lastObservedTime` (19:48:35 → 19:49:01), com `eventTime` inalterado. Eventos legados também reaparecem com `deprecatedLastTimestamp` avançando |
| 6.7 | Node parado por ~35 s: 4 erros logados, loop continuou, coleta retomou sem reiniciar a aplicação |
| 6.8 | ServiceAccount sem permissão: 3 ciclos com log de 403 indicando `list` em `events` de `events.k8s.io`; aplicação não caiu |
| 6.9 | Duas execuções seguidas reimprimiram os mesmos 86 Warning vivos |

## Desvio do design

O modelo tipado do SDK (`EventsV1Event`, kubernetes 37) exige `eventTime`, mas eventos legados chegam com `eventTime: null` e a desserialização falha. O cliente usa o mesmo `list_event_for_all_namespaces` com `field_selector="type=Warning"`, mas lê o JSON bruto (`_preload_content=False`), e `transform.py` opera sobre dicts com os nomes camelCase da API.
