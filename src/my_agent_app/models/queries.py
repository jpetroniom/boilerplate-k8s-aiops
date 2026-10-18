import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from my_agent_app.models.report import ACTIVE_STATUSES, Report, ReportStatus


async def mark_stale_reports(session: AsyncSession, timeout_minutes: float) -> int:
    """Marca como INCOMPLETO os relatorios EM_ANALISE mais antigos que o timeout."""
    cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
    result = await session.execute(
        update(Report)
        .where(Report.status == ReportStatus.EM_ANALISE, Report.created_at < cutoff)
        .values(status=ReportStatus.INCOMPLETO)
    )
    await session.commit()
    return result.rowcount


async def find_active_uids(session: AsyncSession, uids: list[str]) -> set[str]:
    """Uids que constam em algum relatorio ativo (existencia, nunca o status do mais recente)."""
    if not uids:
        return set()
    rows = await session.execute(
        select(Report.event_uids).where(
            Report.status.in_([s.value for s in ACTIVE_STATUSES]),
            Report.event_uids.overlap(uids),
        )
    )
    found: set[str] = set()
    for (event_uids,) in rows:
        found.update(event_uids)
    return found & set(uids)


async def filter_new_events(session: AsyncSession, events: list[dict], stale_timeout_minutes: float) -> list[dict]:
    """Recupera estagnados e devolve apenas os eventos que ainda nao estao em tratamento."""
    await mark_stale_reports(session, stale_timeout_minutes)
    active = await find_active_uids(session, [e["uid"] for e in events])
    return [e for e in events if e["uid"] not in active]


async def create_batch_report(session: AsyncSession, event_uids: list[str]) -> uuid.UUID:
    report = Report(markdown="", status=ReportStatus.EM_ANALISE, event_uids=event_uids)
    session.add(report)
    await session.commit()
    return report.id


async def mark_incomplete(session: AsyncSession, report_id: uuid.UUID) -> bool:
    """EM_ANALISE -> INCOMPLETO; nao altera relatorio que ja saiu de EM_ANALISE."""
    result = await session.execute(
        update(Report)
        .where(Report.id == report_id, Report.status == ReportStatus.EM_ANALISE)
        .values(status=ReportStatus.INCOMPLETO)
    )
    await session.commit()
    return result.rowcount > 0


async def replace_batch_report(session: AsyncSession, batch_id: uuid.UUID, problems: list[dict]) -> bool:
    """Troca o relatorio do lote pelos relatorios por problema, so se ainda estiver EM_ANALISE."""
    current = await session.scalar(select(Report.status).where(Report.id == batch_id).with_for_update())
    if current != ReportStatus.EM_ANALISE:
        await session.rollback()
        return False
    await session.execute(delete(Report).where(Report.id == batch_id))
    session.add_all(
        Report(markdown=p["markdown"], status=ReportStatus.COMPLETO, event_uids=p["event_uids"]) for p in problems
    )
    await session.commit()
    return True


async def recover_orphans(session: AsyncSession) -> int:
    """No startup, todo EM_ANALISE e orfao de um restart: vira INCOMPLETO."""
    result = await session.execute(
        update(Report).where(Report.status == ReportStatus.EM_ANALISE).values(status=ReportStatus.INCOMPLETO)
    )
    await session.commit()
    return result.rowcount


async def list_reports(session: AsyncSession) -> list[Report]:
    """Todos os relatorios, do mais recente para o mais antigo."""
    result = await session.execute(select(Report).order_by(Report.created_at.desc()))
    return list(result.scalars())


async def get_report(session: AsyncSession, report_id: uuid.UUID) -> Report | None:
    return await session.get(Report, report_id)


async def begin_correction(session: AsyncSession, report_id: uuid.UUID) -> bool:
    """COMPLETO/FALHA_CORRECAO -> CORRIGINDO de forma atomica; so uma chamada concorrente vence."""
    result = await session.execute(
        update(Report)
        .where(
            Report.id == report_id,
            Report.status.in_([ReportStatus.COMPLETO.value, ReportStatus.FALHA_CORRECAO.value]),
        )
        .values(status=ReportStatus.CORRIGINDO)
        .returning(Report.id)
    )
    won = result.first() is not None
    await session.commit()
    return won


async def finish_correction(session: AsyncSession, report_id: uuid.UUID, status: ReportStatus, result: str) -> bool:
    """CORRIGINDO -> CORRIGIDO/FALHA_CORRECAO com o resultado; nao sobrescreve relatorio que saiu de CORRIGINDO."""
    outcome = await session.execute(
        update(Report)
        .where(Report.id == report_id, Report.status == ReportStatus.CORRIGINDO)
        .values(status=status, correction_result=result)
    )
    await session.commit()
    return outcome.rowcount > 0


async def recover_corrections(session: AsyncSession) -> int:
    """No startup, todo CORRIGINDO e orfao de um restart: vira FALHA_CORRECAO (re-acionavel)."""
    result = await session.execute(
        update(Report).where(Report.status == ReportStatus.CORRIGINDO).values(status=ReportStatus.FALHA_CORRECAO)
    )
    await session.commit()
    return result.rowcount
