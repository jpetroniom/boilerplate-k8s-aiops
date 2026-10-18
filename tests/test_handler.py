import logging

import pytest
from sqlalchemy import select, update

from my_agent_app.agents.analysis import AnalysisAborted
from my_agent_app.collector.handler import EventHandler
from my_agent_app.models import Report, ReportStatus

RESPONSE = """# Relatorio de Diagnostico Kubernetes

## Problema 1: A
- **Severidade:** ALTO
- **Namespace:** default
- **Recursos Afetados:** pod/a
- **Eventos:** u1

### Causa Raiz
x

## Problema 2: B
- **Severidade:** MEDIO
- **Namespace:** default
- **Recursos Afetados:** pod/b
- **Eventos:** u2

### Causa Raiz
y
"""


def events(*uids):
    return [{"uid": u, "type": "Warning", "reason": "R", "message": "m"} for u in uids]


class Analyzer:
    def __init__(self, response=RESPONSE, exc=None):
        self.response, self.exc, self.calls = response, exc, []

    async def __call__(self, evs):
        self.calls.append(evs)
        if self.exc:
            raise self.exc
        return self.response


async def reports(sm):
    async with sm() as s:
        return (await s.execute(select(Report).order_by(Report.created_at))).scalars().all()


def handler(sm, analyzer):
    return EventHandler(sm, analyze=analyzer, persist_backoff_seconds=0)


async def test_happy_path_creates_one_report_per_problem(sessionmaker):
    an = Analyzer()
    await handler(sessionmaker, an).handle(events("u1", "u2"))
    rows = await reports(sessionmaker)
    assert sorted((r.status, tuple(r.event_uids)) for r in rows) == [("COMPLETO", ("u1",)), ("COMPLETO", ("u2",))]
    assert len(an.calls) == 1


async def test_next_cycle_does_not_reanalyze(sessionmaker):
    an = Analyzer()
    h = handler(sessionmaker, an)
    await h.handle(events("u1", "u2"))
    await h.handle(events("u1", "u2"))
    assert len(an.calls) == 1


async def test_report_is_em_analise_before_agent_runs(sessionmaker):
    seen = {}

    async def an(evs):
        seen["rows"] = [(r.status, r.event_uids) for r in await reports(sessionmaker)]
        return RESPONSE

    await handler(sessionmaker, an).handle(events("u1", "u2"))
    assert seen["rows"] == [("EM_ANALISE", ["u1", "u2"])]


async def test_concurrent_batch_ignored_while_analyzing(sessionmaker):
    inner = Analyzer()

    async def an(evs):
        await handler(sessionmaker, inner).handle(events("u1", "u2"))
        return RESPONSE

    await handler(sessionmaker, an).handle(events("u1", "u2"))
    assert inner.calls == []


async def test_only_new_events_are_analyzed(sessionmaker):
    await handler(sessionmaker, Analyzer()).handle(events("u1", "u2"))
    an = Analyzer(response=RESPONSE.replace("u1", "u3"))
    await handler(sessionmaker, an).handle(events("u1", "u3"))
    assert [e["uid"] for e in an.calls[0]] == ["u3"]


@pytest.mark.parametrize("exc", [AnalysisAborted("mcp down"), RuntimeError("claude api")])
async def test_agent_failure_leaves_batch_incomplete(sessionmaker, exc):
    await handler(sessionmaker, Analyzer(exc=exc)).handle(events("u1"))
    rows = await reports(sessionmaker)
    assert [(r.status, r.event_uids) for r in rows] == [("INCOMPLETO", ["u1"])]


@pytest.mark.parametrize("response", ["", "so texto sem problemas"])
async def test_response_without_problems_is_incomplete(sessionmaker, response):
    await handler(sessionmaker, Analyzer(response=response)).handle(events("u1"))
    assert [r.status for r in await reports(sessionmaker)] == ["INCOMPLETO"]


async def test_incomplete_events_are_reanalyzed_on_recurrence(sessionmaker):
    await handler(sessionmaker, Analyzer(response="")).handle(events("u1", "u2"))
    an = Analyzer()
    await handler(sessionmaker, an).handle(events("u1", "u2"))
    assert len(an.calls) == 1
    assert sorted(r.status for r in await reports(sessionmaker)) == ["COMPLETO", "COMPLETO", "INCOMPLETO"]


async def test_result_discarded_if_batch_became_incomplete_meanwhile(sessionmaker, caplog):
    async def an(evs):
        async with sessionmaker() as s:
            await s.execute(update(Report).values(status=ReportStatus.INCOMPLETO))
            await s.commit()
        return RESPONSE

    with caplog.at_level(logging.WARNING):
        await handler(sessionmaker, an).handle(events("u1", "u2"))
    rows = await reports(sessionmaker)
    assert [(r.status, r.event_uids) for r in rows] == [("INCOMPLETO", ["u1", "u2"])]
    assert "descartado" in caplog.text


async def test_database_down_on_dedup_discards_batch(caplog):
    class Broken:
        def __call__(self):
            raise ConnectionError("db down")

    an = Analyzer()
    with caplog.at_level(logging.ERROR):
        await EventHandler(Broken(), analyze=an).handle(events("u1"))
    assert an.calls == [] and "descartado" in caplog.text


async def test_persist_retries_then_logs_markdown(sessionmaker, monkeypatch, caplog):
    attempts = []

    async def boom(*a, **k):
        attempts.append(1)
        raise ConnectionError("db down")

    monkeypatch.setattr("my_agent_app.collector.handler.queries.replace_batch_report", boom)
    with caplog.at_level(logging.WARNING):
        await handler(sessionmaker, Analyzer()).handle(events("u1", "u2"))
    assert len(attempts) == 3
    assert "Problema 1: A" in caplog.text and "Nao foi possivel persistir" in caplog.text
    assert [r.status for r in await reports(sessionmaker)] == ["EM_ANALISE"]


async def test_persist_succeeds_after_transient_failure(sessionmaker, monkeypatch):
    from my_agent_app.models import queries

    real, state = queries.replace_batch_report, {"n": 0}

    async def flaky(*a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise ConnectionError("blip")
        return await real(*a, **k)

    monkeypatch.setattr("my_agent_app.collector.handler.queries.replace_batch_report", flaky)
    await handler(sessionmaker, Analyzer()).handle(events("u1", "u2"))
    assert sorted(r.status for r in await reports(sessionmaker)) == ["COMPLETO", "COMPLETO"]
