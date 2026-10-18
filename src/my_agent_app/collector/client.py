import asyncio
import json
import logging

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

logger = logging.getLogger(__name__)

_api: client.EventsV1Api | None = None


def _load_config() -> None:
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()


def _get_api() -> client.EventsV1Api:
    global _api
    if _api is None:
        _load_config()
        _api = client.EventsV1Api()
    return _api


def _list_warning_events(api) -> list[dict]:
    # O modelo tipado do SDK exige eventTime, mas eventos legados chegam com eventTime nulo
    # e quebram a desserializacao; por isso le-se o JSON bruto da resposta.
    response = api.list_event_for_all_namespaces(field_selector="type=Warning", _preload_content=False)
    return json.loads(response.data).get("items") or []


async def list_warning_events(api=None) -> list[dict] | None:
    """Lista eventos Warning de todos os namespaces; devolve None se a coleta falhar."""
    try:
        api = api or _get_api()
        return await asyncio.to_thread(_list_warning_events, api)
    except ApiException as exc:
        if exc.status == 403:
            logger.error(
                "Sem permissao para listar eventos (HTTP 403): o ClusterRole precisa de "
                "verbo 'list' no recurso 'events' do grupo 'events.k8s.io'"
            )
        else:
            logger.error("Erro da API do Kubernetes ao listar eventos: %s", exc)
    except Exception:
        logger.exception("Falha ao coletar eventos do cluster")
    return None
