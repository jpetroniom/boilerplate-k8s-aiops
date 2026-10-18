import asyncio
import logging

import pytest
from conftest import iso, make_event

from my_agent_app.collector.loop import EventCollector, get_interval_minutes


@pytest.mark.parametrize("raw,expected", [("5", 5.0), ("0.5", 0.5), ("abc", 3.0), ("0", 3.0), ("-2", 3.0), ("nan", 3.0)])
def test_interval(monkeypatch, raw, expected):
    monkeypatch.setenv("EVENT_COLLECTION_INTERVAL_MINUTES", raw)
    assert get_interval_minutes() == expected


def test_interval_default(monkeypatch):
    monkeypatch.delenv("EVENT_COLLECTION_INTERVAL_MINUTES", raising=False)
    assert get_interval_minutes() == 3.0


def test_invalid_interval_warns(monkeypatch, caplog):
    monkeypatch.setenv("EVENT_COLLECTION_INTERVAL_MINUTES", "abc")
    with caplog.at_level(logging.WARNING):
        get_interval_minutes()
    assert "invalido" in caplog.text


class Recorder:
    def __init__(self, delay=0.0):
        self.batches, self.delay = [], delay

    async def handle(self, events):
        await asyncio.sleep(self.delay)
        self.batches.append(events)


def collector(events_seq, handler, interval=1):
    seq = iter(events_seq)

    async def list_events():
        return next(seq)

    return EventCollector(handler=handler, list_events=list_events, interval_minutes=interval)


async def drain(c):
    await asyncio.gather(*list(c._tasks))


async def test_first_collection_has_no_watermark_and_then_advances():
    old = make_event(event_time=iso(1))
    h = Recorder()
    c = collector([[old], [old]], h)
    assert c.watermark is None
    await c.collect_once()
    await drain(c)
    assert len(h.batches) == 1 and c.watermark is not None
    await c.collect_once()  # mesmo evento antigo: filtrado pela marca d'agua
    await drain(c)
    assert len(h.batches) == 1


async def test_watermark_preserved_after_failure():
    h = Recorder()
    c = collector([[make_event(event_time=iso(1))], None], h)
    await c.collect_once()
    mark = c.watermark
    await c.collect_once()
    assert c.watermark == mark


async def test_empty_batch_not_dispatched():
    h = Recorder()
    c = collector([[]], h)
    await c.collect_once()
    assert not c._tasks and h.batches == []


async def test_slow_handler_does_not_block_cycle():
    h = Recorder(delay=10)
    c = collector([[make_event(event_time=iso(1))]], h)
    await asyncio.wait_for(c.collect_once(), timeout=1)
    assert len(c._tasks) == 1
    await c.shutdown()
    assert not c._tasks


async def test_finished_tasks_are_discarded():
    h = Recorder()
    c = collector([[make_event(event_time=iso(1))]], h)
    await c.collect_once()
    await asyncio.sleep(0.05)
    assert not c._tasks


async def test_run_cancel_cancels_pending_tasks():
    h = Recorder(delay=10)
    c = collector([[make_event(event_time=iso(1))]] + [[]] * 5, h)
    run = asyncio.create_task(c.run())
    await asyncio.sleep(0.05)
    assert len(c._tasks) == 1
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert not c._tasks
