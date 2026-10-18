from datetime import UTC, datetime


def make_event(
    uid="u1",
    type="Warning",
    reason="BackOff",
    note="msg",
    namespace="default",
    series_last=None,
    event_time=None,
    deprecated_last=None,
    regarding=None,
):
    return {
        "metadata": {"uid": uid, "namespace": namespace},
        "type": type,
        "reason": reason,
        "note": note,
        "regarding": regarding or {"kind": "Pod", "name": "p", "namespace": namespace},
        "series": {"lastObservedTime": series_last} if series_last else None,
        "eventTime": event_time,
        "deprecatedLastTimestamp": deprecated_last,
    }


def ts(minute, second=0):
    return datetime(2026, 1, 1, 12, minute, second, tzinfo=UTC)


def iso(minute, second=0):
    return ts(minute, second).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
