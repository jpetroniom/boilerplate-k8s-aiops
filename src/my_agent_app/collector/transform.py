import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def event_recency(event: dict) -> datetime | None:
    """Recencia do evento: series.lastObservedTime > eventTime > deprecatedLastTimestamp."""
    series = event.get("series") or {}
    for value in (series.get("lastObservedTime"), event.get("eventTime"), event.get("deprecatedLastTimestamp")):
        parsed = _parse_time(value)
        if parsed is not None:
            return parsed
    return None


def select_events(events: list[dict], watermark: datetime | None) -> list[tuple[dict, datetime]]:
    """Mantem eventos Warning mais recentes que a marca d'agua (None = sem filtro)."""
    selected = []
    for event in events:
        if event.get("type") != "Warning":
            continue
        recency = event_recency(event)
        if recency is None:
            logger.warning(
                "Evento %s descartado: sem series.lastObservedTime, eventTime ou deprecatedLastTimestamp",
                (event.get("metadata") or {}).get("uid"),
            )
            continue
        if watermark is not None and recency <= watermark:
            continue
        selected.append((event, recency))
    return selected


def to_contract(event: dict, recency: datetime) -> dict:
    metadata = event.get("metadata") or {}
    regarding = event.get("regarding") or {}
    return {
        "uid": metadata.get("uid"),
        "type": event.get("type"),
        "reason": event.get("reason"),
        "message": event.get("note"),
        "namespace": metadata.get("namespace") or "",
        "involved_object": {
            "kind": regarding.get("kind") or "",
            "name": regarding.get("name") or "",
            "namespace": regarding.get("namespace") or "",
        },
        "timestamp": recency.isoformat(),
    }


def transform_events(events: list[dict], watermark: datetime | None) -> list[dict]:
    return [to_contract(event, recency) for event, recency in select_events(events, watermark)]
