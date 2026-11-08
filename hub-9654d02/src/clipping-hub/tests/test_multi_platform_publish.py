"""Multi-platform Approve: idempotency, Storyblocks, manual-label blocks."""
from __future__ import annotations

import json
from pathlib import Path

import multi_platform_publish as M
import platform_capabilities as C
import post_idempotency as idem
import schedule_hook as S


def test_capability_table_blocks_tt_ig_fb_when_ai():
    item = {
        "id": "c1",
        "platforms": ["Clipped Motions YouTube", "TikTok Business", "IG Business", "FB Page"],
        "ai_disclosure": True,
    }
    plan = C.plan_platforms(item, ai_disclosure=True)
    by = {p["key"]: p["action"] for p in plan}
    assert by["youtube"] == "youtube_flow"
    assert by["tiktok"] == "needs_manual_label"
    assert by["instagram"] == "needs_manual_label"
    assert by["facebook"] == "needs_manual_label"


def test_double_tap_does_not_repost(tmp_path, monkeypatch):
    monkeypatch.setenv(M.FLAG, "true")
    ledger = tmp_path / "ledger.jsonl"
    calls = []

    def yt_runner(item, **kw):
        calls.append("yt")
        return {"ok": True, "youtube_label": True, "video_id": "vid1"}

    item = {
        "id": "jobA",
        "title": "T",
        "platforms": ["Clipped Motions YouTube", "TikTok Business"],
        "ai_disclosure": True,
    }
    r1 = M.publish_after_approve(item, env={M.FLAG: "true"}, ledger_path=ledger, youtube_runner=yt_runner,
                                 push_fn=lambda *a, **k: True)
    r2 = M.publish_after_approve(item, env={M.FLAG: "true"}, ledger_path=ledger, youtube_runner=yt_runner,
                                 push_fn=lambda *a, **k: True)
    assert calls == ["yt"]  # second tap skipped
    yt_rows = [p for p in r2["platforms"] if p["key"] == "youtube"]
    assert yt_rows and yt_rows[0]["skipped_idempotent"] is True
    assert idem.lookup("jobA", "youtube", path=ledger)["status"] == "done"


def test_retry_after_partial_failure(tmp_path, monkeypatch):
    monkeypatch.setenv(M.FLAG, "true")
    ledger = tmp_path / "ledger.jsonl"
    n = {"yt": 0}

    def yt_runner(item, **kw):
        n["yt"] += 1
        if n["yt"] == 1:
            return {"ok": False, "youtube_label": False, "error": "boom"}
        return {"ok": True, "youtube_label": True, "video_id": "vid2"}

    item = {"id": "jobB", "title": "T", "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True}
    r1 = M.publish_after_approve(item, env={M.FLAG: "true"}, ledger_path=ledger, youtube_runner=yt_runner,
                                 push_fn=lambda *a, **k: True)
    assert r1["ok"] is False
    assert idem.lookup("jobB", "youtube", path=ledger)["status"] == "failed"
    r2 = M.publish_after_approve(item, env={M.FLAG: "true"}, ledger_path=ledger, youtube_runner=yt_runner,
                                 push_fn=lambda *a, **k: True)
    assert n["yt"] == 2
    assert idem.lookup("jobB", "youtube", path=ledger)["status"] == "done"
    assert any(p.get("status") == "done" for p in r2["platforms"] if p["key"] == "youtube")


def test_storyblocks_paid_is_route_blocked_before_upload(tmp_path, monkeypatch):
    monkeypatch.setenv(M.FLAG, "true")
    monkeypatch.setattr(S, "load_targets", lambda path=None: {
        "version": 1, "poster": "opus",
        "targets": {
            "MAIN": {"name": "M", "handle": "@m", "yt": S.MAIN_YOUTUBE_CHANNEL_ID, "opus_post_account_id": "a", "whop": ""},
            "PAID": {"name": "P", "handle": "@p", "yt": "UCpaid", "opus_post_account_id": "b", "whop": ""},
        },
    })
    calls = []
    item = {
        "id": "jobC", "title": "T", "is_ad": True,
        "license": {"source": "storyblocks"},
        "platforms": ["TikTok Business", "Clipped Motions YouTube"],
        "ai_disclosure": True,
    }
    r = M.publish_after_approve(
        item, env={M.FLAG: "true"}, ledger_path=tmp_path / "l.jsonl",
        youtube_runner=lambda *a, **k: calls.append(1) or {"ok": True, "youtube_label": True},
        push_fn=lambda *a, **k: True,
    )
    assert r["ok"] is False
    assert str(r.get("error") or "").startswith("route_blocked:storyblocks_main_only")
    assert calls == []
    assert r["platforms"] == []


def test_storyblocks_facebook_does_not_unlock_legacy_upload(tmp_path, monkeypatch):
    monkeypatch.delenv("CLIP_PUBLIC_PUBLISH", raising=False)
    monkeypatch.setenv(M.FLAG, "true")
    calls = []
    item = {
        "id": "jobFB", "title": "T",
        "license": {"source": "storyblocks"},
        "platforms": ["FB Page", "Clipped Motions YouTube"],
        "ai_disclosure": True,
    }
    r = M.publish_after_approve(
        item, env={M.FLAG: "true"}, ledger_path=tmp_path / "l.jsonl",
        youtube_runner=lambda *a, **k: calls.append(1) or {"ok": True, "youtube_label": True},
        push_fn=lambda *a, **k: True,
    )
    assert calls == []
    assert str(r.get("error") or "").startswith("route_blocked:storyblocks_main_only_blocks_platform")


def test_held_stays_eligible_for_label_step_when_public_off(tmp_path, monkeypatch):
    monkeypatch.delenv("CLIP_PUBLIC_PUBLISH", raising=False)
    monkeypatch.setenv(M.FLAG, "true")
    calls = []

    def runner(*a, **k):
        calls.append(1)
        return {"ok": True, "youtube_label": True, "video_id": "vidhold"}

    item = {
        "id": "jobHold", "title": "T", "campaign_id": "HeldAlliance",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
    }
    off = M.publish_after_approve(
        item, env={M.FLAG: "true"}, ledger_path=tmp_path / "hold.jsonl",
        youtube_runner=runner, push_fn=lambda *a, **k: True,
    )
    assert calls == [1]
    assert off.get("error") in (None, "")
    monkeypatch.setenv("CLIP_PUBLIC_PUBLISH", "true")
    calls.clear()
    on = M.publish_after_approve(
        item, env={M.FLAG: "true", "CLIP_PUBLIC_PUBLISH": "true"}, ledger_path=tmp_path / "hold-on.jsonl",
        youtube_runner=runner, push_fn=lambda *a, **k: True,
    )
    assert calls == []
    assert str(on.get("error") or "").startswith("route_blocked:")


def test_manual_label_push_once(tmp_path, monkeypatch):
    monkeypatch.setenv(M.FLAG, "true")
    pushes = []
    item = {
        "id": "jobD", "title": "Clip",
        "platforms": ["IG Business", "FB Page"],
        "ai_disclosure": True,
    }
    M.publish_after_approve(
        item, env={M.FLAG: "true"}, ledger_path=tmp_path / "l.jsonl",
        youtube_runner=lambda *a, **k: {"ok": True},
        push_fn=lambda t, b, key=None: pushes.append(t) or True,
    )
    assert any("Manual AI label" in p for p in pushes)
    assert len(pushes) == 1


def test_postiz_not_connected_constant():
    assert C.POSTIZ_CONNECTED is False


def test_docs_exist():
    assert (Path(__file__).resolve().parent.parent / "docs" / "PLATFORM_CAPABILITIES.md").is_file()
