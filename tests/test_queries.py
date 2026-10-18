from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from my_agent_app.models import Report, ReportStatus
from my_agent_app.models import queries as q


def ev(uid):
    return {"uid": uid}


async def add(sm, status, uids, age_minutes=0, updated_minutes_ago=0):
    async with sm() as s:
        r = Report(markdown="m", status=status, event_uids=uids)
        s.add(r)
        await s.commit()
        if age_minutes:
            await s.execute(
                update(Report).where(Report.id == r.id).values(created_at=datetime.now(UTC) - timedelta(minutes=age_minutes))
            )
            await s.commit()
        if updated_minutes_ago:
            await s.execute(
                update(Report)
                .where(Report.id == r.id)
                .values(updated_at=datetime.now(UTC) - timedelta(minutes=updated_minutes_ago))
            )
            await s.commit()
        return r.id


async def status_of(sm, rid):
    async with sm() as s:
        return await s.scalar(select(Report.status).where(Report.id == rid))


async def test_new_event_is_kept(sessionmaker):
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("a")], 30) == [ev("a")]


async def test_events_in_active_reports_are_ignored(sessionmaker):
    for status, uid in [("EM_ANALISE", "1"), ("COMPLETO", "2"), ("CORRIGINDO", "3"), ("FALHA_CORRECAO", "4")]:
        await add(sessionmaker, status, [uid])
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev(u) for u in "1234"], 30) == []


async def test_corrigido_and_incompleto_are_reanalyzed(sessionmaker):
    await add(sessionmaker, "CORRIGIDO", ["c"])
    await add(sessionmaker, "INCOMPLETO", ["i"])
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("c"), ev("i")], 30) == [ev("c"), ev("i")]


async def test_recently_fixed_is_ignored_within_grace(sessionmaker):
    await add(sessionmaker, "CORRIGIDO", ["f"], updated_minutes_ago=5)
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("f")], 30, grace_minutes=15) == []


async def test_fixed_after_grace_is_reanalyzed(sessionmaker):
    await add(sessionmaker, "CORRIGIDO", ["f"], updated_minutes_ago=20)
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("f")], 30, grace_minutes=15) == [ev("f")]


async def test_grace_does_not_apply_to_incompleto(sessionmaker):
    await add(sessionmaker, "INCOMPLETO", ["i"], updated_minutes_ago=1)
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("i")], 30, grace_minutes=15) == [ev("i")]


async def test_finish_correction_starts_grace(sessionmaker):
    rid = await add(sessionmaker, "CORRIGINDO", ["g"], updated_minutes_ago=60)
    async with sessionmaker() as s:
        await q.finish_correction(s, rid, ReportStatus.CORRIGIDO, "CORRIGIDO: ok")
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("g")], 30, grace_minutes=15) == []


async def test_old_corrigido_plus_active_report_is_ignored(sessionmaker):
    await add(sessionmaker, "CORRIGIDO", ["x"])
    await add(sessionmaker, "EM_ANALISE", ["x"])
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("x")], 30) == []


async def test_partial_batch(sessionmaker):
    await add(sessionmaker, "COMPLETO", ["old"])
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("old"), ev("new")], 30) == [ev("new")]


async def test_stale_em_analise_becomes_incompleto_and_event_is_released(sessionmaker):
    rid = await add(sessionmaker, "EM_ANALISE", ["s"], age_minutes=45)
    async with sessionmaker() as s:
        assert await q.filter_new_events(s, [ev("s")], 30) == [ev("s")]
    assert await status_of(sessionmaker, rid) == "INCOMPLETO"


async def test_fresh_em_analise_is_not_stale(sessionmaker):
    rid = await add(sessionmaker, "EM_ANALISE", ["s"], age_minutes=5)
    async with sessionmaker() as s:
        await q.mark_stale_reports(s, 30)
    assert await status_of(sessionmaker, rid) == "EM_ANALISE"


async def test_create_batch_report(sessionmaker):
    async with sessionmaker() as s:
        rid = await q.create_batch_report(s, ["a", "b"])
    assert await status_of(sessionmaker, rid) == "EM_ANALISE"


async def test_replace_creates_report_per_problem(sessionmaker):
    batch = await add(sessionmaker, "EM_ANALISE", ["a", "b"])
    problems = [{"markdown": "p1", "event_uids": ["a"]}, {"markdown": "p2", "event_uids": ["b"]}]
    async with sessionmaker() as s:
        assert await q.replace_batch_report(s, batch, problems) is True
    async with sessionmaker() as s:
        rows = (await s.execute(select(Report))).scalars().all()
    assert sorted((r.status, r.event_uids[0]) for r in rows) == [("COMPLETO", "a"), ("COMPLETO", "b")]
    assert all(r.id != batch for r in rows)


async def test_replace_aborted_when_batch_no_longer_em_analise(sessionmaker):
    batch = await add(sessionmaker, "INCOMPLETO", ["a"])
    async with sessionmaker() as s:
        assert await q.replace_batch_report(s, batch, [{"markdown": "p", "event_uids": ["a"]}]) is False
    async with sessionmaker() as s:
        rows = (await s.execute(select(Report))).scalars().all()
    assert [(r.id, r.status) for r in rows] == [(batch, "INCOMPLETO")]


async def test_mark_incomplete_is_conditional(sessionmaker):
    done = await add(sessionmaker, "COMPLETO", ["a"])
    running = await add(sessionmaker, "EM_ANALISE", ["b"])
    async with sessionmaker() as s:
        assert await q.mark_incomplete(s, done) is False
        assert await q.mark_incomplete(s, running) is True
    assert await status_of(sessionmaker, done) == "COMPLETO"
    assert await status_of(sessionmaker, running) == "INCOMPLETO"


async def test_recover_orphans(sessionmaker):
    orphan = await add(sessionmaker, "EM_ANALISE", ["a"])
    ok = await add(sessionmaker, "COMPLETO", ["b"])
    async with sessionmaker() as s:
        assert await q.recover_orphans(s) == 1
    assert await status_of(sessionmaker, orphan) == "INCOMPLETO"
    assert await status_of(sessionmaker, ok) == "COMPLETO"


async def test_list_reports_newest_first_and_empty(sessionmaker):
    async with sessionmaker() as s:
        assert await q.list_reports(s) == []
    old = await add(sessionmaker, "COMPLETO", ["a"], age_minutes=60)
    new = await add(sessionmaker, "INCOMPLETO", ["b"])
    mid = await add(sessionmaker, "CORRIGIDO", ["c"], age_minutes=30)
    async with sessionmaker() as s:
        assert [r.id for r in await q.list_reports(s)] == [new, mid, old]


async def test_get_report(sessionmaker):
    import uuid

    rid = await add(sessionmaker, "COMPLETO", ["a"])
    async with sessionmaker() as s:
        assert (await q.get_report(s, rid)).id == rid
        assert await q.get_report(s, uuid.uuid4()) is None


async def test_begin_correction_accepts_only_completo_and_falha(sessionmaker):
    ok = [await add(sessionmaker, "COMPLETO", ["a"]), await add(sessionmaker, "FALHA_CORRECAO", ["b"])]
    bad = [await add(sessionmaker, st, ["c"]) for st in ("EM_ANALISE", "INCOMPLETO", "CORRIGINDO", "CORRIGIDO")]
    async with sessionmaker() as s:
        assert [await q.begin_correction(s, r) for r in ok] == [True, True]
    async with sessionmaker() as s:
        assert [await q.begin_correction(s, r) for r in bad] == [False] * 4
    assert [await status_of(sessionmaker, r) for r in ok] == ["CORRIGINDO", "CORRIGINDO"]


async def test_begin_correction_concurrent_only_one_wins(sessionmaker):
    import asyncio

    rid = await add(sessionmaker, "COMPLETO", ["a"])

    async def attempt():
        async with sessionmaker() as s:
            return await q.begin_correction(s, rid)

    results = await asyncio.gather(*[attempt() for _ in range(8)])
    assert results.count(True) == 1


async def test_finish_correction_sets_result_only_while_corrigindo(sessionmaker):
    running = await add(sessionmaker, "CORRIGINDO", ["a"])
    recovered = await add(sessionmaker, "FALHA_CORRECAO", ["b"])
    async with sessionmaker() as s:
        assert await q.finish_correction(s, running, ReportStatus.CORRIGIDO, "CORRIGIDO: ok") is True
        assert await q.finish_correction(s, recovered, ReportStatus.CORRIGIDO, "x") is False
    async with sessionmaker() as s:
        r = await q.get_report(s, running)
        assert (r.status, r.correction_result) == ("CORRIGIDO", "CORRIGIDO: ok")
        assert (await q.get_report(s, recovered)).correction_result is None


async def test_recover_corrections(sessionmaker):
    orphan = await add(sessionmaker, "CORRIGINDO", ["a"])
    other = await add(sessionmaker, "CORRIGIDO", ["b"])
    async with sessionmaker() as s:
        assert await q.recover_corrections(s) == 1
    assert await status_of(sessionmaker, orphan) == "FALHA_CORRECAO"
    assert await status_of(sessionmaker, other) == "CORRIGIDO"
