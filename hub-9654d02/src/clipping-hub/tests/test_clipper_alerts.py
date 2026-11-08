"""Clipper alert types + empty data contract."""
import json
from pathlib import Path

import clipper_alerts as A
import clipper_data as C


def test_alert_types_list():
    assert set(A.ALERT_TYPES) >= {"short_ready", "credits_low", "campaign_status", "render_fail", "sent", "paid"}


def test_empty_loaders_are_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "SHORTS_DIR", tmp_path / "shorts")
    monkeypatch.setattr(C, "LEDGER_DIR", tmp_path / "ledger")
    assert C.load_shorts()["empty"] is True
    assert C.load_credits()["empty"] is True
    assert "not written" in C.load_credits()["reason"] or "missing" in C.load_credits()["reason"]
    assert C.load_campaigns()["empty"] is True
    assert C.load_script_queue()["empty"] is True


def test_load_short_meta_from_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "SHORTS_DIR", tmp_path / "shorts")
    d = tmp_path / "shorts" / "s1"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({
        "id": "s1", "title": "Hallway", "status": "queued", "lane": "horror",
        "channel": "clippedmotions", "niche": "horror", "caption": "x", "hashtags": ["#ad"],
        "is_ad": True, "duration_s": 40, "created_at": "2026-11-06",
        "compliance": {"a": "pass", "b": "pass", "c": "needs_check", "d": "pass", "e": "pass", "f": "pass"},
        "licenses": [], "credits": {"opus": 1, "elevenlabs": 100}, "campaign_id": "nemoris",
    }))
    (d / "final.mp4").write_bytes(b"x")
    out = C.load_shorts()
    assert out["empty"] is False and out["items"][0]["id"] == "s1"
    assert out["items"][0]["has_final"] is True


def test_typed_alerts_call_send(monkeypatch):
    calls = []
    monkeypatch.setattr(A.P, "send_ntfy", lambda *a, **k: calls.append((a, k)) or True)
    assert A.alert_short_ready({"id": "1", "title": "T"})
    assert A.alert_credits_low("Opus", 10, 30)
    assert A.alert_campaign_status("Nemoris", "applied")
    assert A.alert_render_fail({"id": "1", "title": "T"})
    assert A.alert_sent({"id": "1", "title": "T"})
    assert A.alert_paid("Nemoris")
    titles = [c[0][0] for c in calls]
    assert titles == [
        "Short ready to approve", "Credits below reserve", "Campaign status",
        "Render failed", "Post sent", "Paid",
    ]


def test_scan_noop_when_empty(monkeypatch):
    monkeypatch.setattr(A.CD, "load_shorts", lambda: {"empty": True, "items": []})
    monkeypatch.setattr(A.CD, "load_credits", lambda: {"empty": True})
    monkeypatch.setattr(A.CD, "load_campaigns", lambda: {"empty": True, "campaigns": []})
    assert A.scan(state={}, send=True) == []
