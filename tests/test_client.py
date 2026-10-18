import asyncio
import json
import logging
import time
from types import SimpleNamespace

from kubernetes.client.exceptions import ApiException

from my_agent_app.collector.client import list_warning_events


class FakeApi:
    def __init__(self, exc=None, delay=0.0):
        self.exc, self.delay, self.kwargs = exc, delay, None

    def list_event_for_all_namespaces(self, **kwargs):
        self.kwargs = kwargs
        time.sleep(self.delay)
        if self.exc:
            raise self.exc
        return SimpleNamespace(data=json.dumps({"items": ["e"]}))


async def test_lists_with_field_selector():
    api = FakeApi()
    assert await list_warning_events(api) == ["e"]
    assert api.kwargs == {"field_selector": "type=Warning", "_preload_content": False}


async def test_does_not_block_event_loop():
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    t = asyncio.create_task(ticker())
    await list_warning_events(FakeApi(delay=0.2))
    t.cancel()
    assert ticks >= 5


async def test_403_logs_required_permission(caplog):
    with caplog.at_level(logging.ERROR):
        assert await list_warning_events(FakeApi(exc=ApiException(status=403))) is None
    assert "events.k8s.io" in caplog.text and "list" in caplog.text


async def test_connection_error_returns_none(caplog):
    with caplog.at_level(logging.ERROR):
        assert await list_warning_events(FakeApi(exc=ConnectionError("down"))) is None
    assert "Falha ao coletar" in caplog.text
