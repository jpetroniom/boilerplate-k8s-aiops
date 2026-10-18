import logging

from conftest import iso, make_event, ts
from my_agent_app.collector.transform import event_recency, select_events, to_contract, transform_events


def test_recency_prefers_series():
    e = make_event(series_last=iso(30), event_time=iso(10), deprecated_last=iso(5))
    assert event_recency(e) == ts(30)


def test_recency_without_series_uses_event_time():
    assert event_recency(make_event(event_time=iso(10), deprecated_last=iso(5))) == ts(10)


def test_recency_legacy():
    assert event_recency(make_event(deprecated_last=iso(5))) == ts(5)


def test_no_timestamp_discarded_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        assert select_events([make_event()], None) == []
    assert "descartado" in caplog.text


def test_recurring_event_selected_by_series():
    e = make_event(series_last=iso(30), event_time=iso(1))
    assert [r for _, r in select_events([e], ts(20))] == [ts(30)]


def test_watermark_filters_old_and_keeps_recent():
    old = make_event(uid="old", event_time=iso(10))
    new = make_event(uid="new", event_time=iso(40))
    out = select_events([old, new], ts(20))
    assert [e['metadata']['uid'] for e, _ in out] == ["new"]


def test_no_watermark_means_no_recency_filter():
    old = make_event(event_time=iso(1))
    assert len(select_events([old], None)) == 1


def test_normal_events_ignored():
    assert select_events([make_event(type="Normal", event_time=iso(1))], None) == []


def test_contract_payload():
    e = make_event(event_time=iso(10))
    assert transform_events([e], None) == [
        {
            "uid": "u1",
            "type": "Warning",
            "reason": "BackOff",
            "message": "msg",
            "namespace": "default",
            "involved_object": {"kind": "Pod", "name": "p", "namespace": "default"},
            "timestamp": "2026-01-01T12:10:00+00:00",
        }
    ]


def test_cluster_scoped_namespace_empty():
    e = make_event(namespace=None, event_time=iso(1), regarding={"kind": "Node", "name": "n"})
    out = to_contract(e, ts(1))
    assert out["involved_object"]["namespace"] == ""
    assert out["namespace"] == ""


def test_legacy_event_with_null_event_time_from_real_payload():
    e = make_event(event_time=None, deprecated_last="2026-01-01T12:05:00Z")
    out = transform_events([e], None)
    assert out[0]["timestamp"] == "2026-01-01T12:05:00+00:00"
