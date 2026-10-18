import json
import logging

logger = logging.getLogger(__name__)


class EventHandler:
    """Ponto de extensao para a analise (PRD 002). Por ora, imprime os eventos no stdout."""

    async def handle(self, events: list[dict]) -> None:
        try:
            for event in events:
                print(json.dumps(event, ensure_ascii=False), flush=True)
        except Exception:
            logger.exception("Falha ao processar lote de eventos")
