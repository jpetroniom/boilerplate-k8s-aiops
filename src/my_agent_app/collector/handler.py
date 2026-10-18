import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from my_agent_app.agents import analysis
from my_agent_app.agents.report_parser import parse_problems
from my_agent_app.models import queries

logger = logging.getLogger(__name__)

PERSIST_ATTEMPTS = 3


class EventHandler:
    """Pipeline de analise: dedup -> relatorio EM_ANALISE -> agente -> relatorios por problema."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        analyze=analysis.analyze,
        persist_backoff_seconds: float = 1.0,
    ):
        self._sessionmaker = sessionmaker
        self._analyze = analyze
        self._backoff = persist_backoff_seconds

    async def handle(self, events: list[dict]) -> None:
        """Nunca propaga excecoes: o coletor despacha em fire-and-forget."""
        try:
            await self._process(events)
        except Exception:
            logger.exception("Falha inesperada ao processar lote de eventos")

    async def _process(self, events: list[dict]) -> None:
        try:
            async with self._sessionmaker() as session:
                new_events = await queries.filter_new_events(
                    session,
                    events,
                    analysis.get_stale_timeout_minutes(),
                    analysis.get_correction_grace_minutes(),
                )
            if not new_events:
                logger.info("Lote de %d eventos ignorado: todos ja estao em tratamento", len(events))
                return
            uids = [e["uid"] for e in new_events]
            async with self._sessionmaker() as session:
                batch_id = await queries.create_batch_report(session, uids)
        except Exception:
            logger.exception("Banco indisponivel na deduplicacao; lote descartado")
            return

        try:
            response = await self._analyze(new_events)
        except Exception as exc:
            logger.error("Analise abortada (%s: %s); relatorio do lote ficara INCOMPLETO", type(exc).__name__, exc)
            await self._mark_incomplete(batch_id)
            return

        problems = parse_problems(response, uids)
        if not problems:
            logger.warning("Resposta do agente sem problemas identificaveis; relatorio do lote INCOMPLETO")
            await self._mark_incomplete(batch_id)
            return
        await self._persist(batch_id, [{"markdown": p.markdown, "event_uids": p.event_uids} for p in problems])

    async def _mark_incomplete(self, batch_id: uuid.UUID) -> None:
        try:
            async with self._sessionmaker() as session:
                await queries.mark_incomplete(session, batch_id)
        except Exception:
            logger.exception("Falha ao marcar o relatorio %s como INCOMPLETO", batch_id)

    async def _persist(self, batch_id: uuid.UUID, problems: list[dict]) -> None:
        for attempt in range(1, PERSIST_ATTEMPTS + 1):
            try:
                async with self._sessionmaker() as session:
                    swapped = await queries.replace_batch_report(session, batch_id, problems)
            except Exception:
                logger.warning("Falha ao persistir relatorios (tentativa %d/%d)", attempt, PERSIST_ATTEMPTS, exc_info=True)
                if attempt < PERSIST_ATTEMPTS:
                    await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
                continue
            if not swapped:
                logger.warning("Relatorio do lote %s nao esta mais EM_ANALISE; resultado do agente descartado", batch_id)
            return
        markdown = "\n\n".join(p["markdown"] for p in problems)
        logger.error("Nao foi possivel persistir os relatorios do lote %s. Markdown gerado:\n%s", batch_id, markdown)
