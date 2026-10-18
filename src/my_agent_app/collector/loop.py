import asyncio
import logging
import os
from datetime import UTC, datetime

from my_agent_app.collector import client
from my_agent_app.collector.handler import EventHandler
from my_agent_app.collector.transform import transform_events

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 3.0


def get_interval_minutes() -> float:
    raw = os.getenv("EVENT_COLLECTION_INTERVAL_MINUTES")
    if raw is None:
        return DEFAULT_INTERVAL_MINUTES
    try:
        value = float(raw)
    except ValueError:
        value = 0
    if not value > 0 or value == float("inf"):
        logger.warning(
            "EVENT_COLLECTION_INTERVAL_MINUTES invalido (%r); usando %s minutos",
            raw,
            DEFAULT_INTERVAL_MINUTES,
        )
        return DEFAULT_INTERVAL_MINUTES
    return value


class EventCollector:
    def __init__(self, handler: EventHandler | None = None, list_events=None, interval_minutes: float | None = None):
        self.handler = handler or EventHandler()
        self._list_events = list_events or client.list_warning_events
        self.interval_seconds = (interval_minutes if interval_minutes is not None else get_interval_minutes()) * 60
        self.watermark: datetime | None = None
        self._tasks: set[asyncio.Task] = set()

    async def collect_once(self) -> None:
        started_at = datetime.now(UTC)
        events = await self._list_events()
        if events is None:
            return
        batch = transform_events(events, self.watermark)
        self.watermark = started_at
        if batch:
            self._dispatch(batch)

    def _dispatch(self, batch: list[dict]) -> None:
        task = asyncio.create_task(self.handler.handle(batch))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run(self) -> None:
        try:
            while True:
                try:
                    await self.collect_once()
                except Exception:
                    logger.exception("Erro inesperado no ciclo de coleta")
                await asyncio.sleep(self.interval_seconds)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
