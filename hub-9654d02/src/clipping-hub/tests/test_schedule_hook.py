"""Approve -> schedule stub: flag default OFF, no poster calls, jobs file interface."""
import json
import os
from pathlib import Path

import pytest

import schedule_hook as S
import server as srv

ROOT = Path(__file__).resolve().parents[1]


def _item(**kw):
    base = {
        "id": "a1",
        "video": "/clips/x.mp4",
        "caption": "hi",
        "platforms": ["TikTok Business"],
        "scheduled_at": "2026-11-07T18:00:00-05:00",
        "status": "approved",
        "note": "",
        "decided_at": "2026-11-06T11:00:00-0500",
        "ai_disclosure": False,  # legacy schedule tests; AI path covered in test_label_pending
    }
    base.update(kw)
    return base


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("CLIP_AUTOPOST_ENABLED", raising=False)
    assert S.enabled() is False
    monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", "false")
    assert S.enabled() is False
    monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", "0")
    assert S.enabled() is False


def test_flag_on_values(monkeypatch):
    for v in ("true", "TRUE", "1", "yes", "on"):
        monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", v)
        assert S.enabled() is True, v


def test_on_approved_noop_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", "false")
    jobs = tmp_path / "jobs.jsonl"
    item = _item()
    assert S.on_approved(item, jobs_path=jobs) is False
    assert item["status"] == "approved"
    assert not jobs.exists()


def test_on_approved_marks_scheduled_and_writes_job(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", "true")
    jobs = tmp_path / "jobs.jsonl"
    item = _item()
    assert S.on_approved(item, jobs_path=jobs, now="2026-11-06T12:00:00-0500") is True
    assert item["status"] == "scheduled"
    lines = jobs.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["op"] == "schedule_post"
    assert rec["id"] == "a1"
    assert rec["video"] == "/clips/x.mp4"
    assert rec["caption"] == "hi"
    assert rec["platforms"] == ["TikTok Business"]
    assert rec["scheduled_at"].startswith("2026-11-07")
    assert rec["status"] == "queued"
    assert rec["poster"] == "opus"
    assert rec["remote_ids"] == {}
    assert rec["error"] is None
    assert rec["source"] == "clipping-hub-approvals"


def test_on_approved_ignores_non_approved(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", "true")
    jobs = tmp_path / "jobs.jsonl"
    assert S.on_approved(_item(status="pending"), jobs_path=jobs) is False
    assert S.on_approved(_item(status="rejected"), jobs_path=jobs) is False
    assert not jobs.exists()


def test_schedule_hook_has_no_poster_or_network_imports():
    """Code must not import/network; platform key names in AI map/doc are allowed."""
    import re
    raw = (ROOT / "schedule_hook.py").read_text()
    # Strip docstrings so AI platform field docs don't trip the youtube ban.
    code = re.sub(r'"""[\s\S]*?"""', "", raw)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    low = code.lower()
    for banned in ("urllib", "http.client", "requests", "postiz", "googleapiclient",
                   "aiohttp", "socket.create_connection", "httpx"):
        assert banned not in low, banned
    # No YouTube API client imports — AI map key "youtube" alone is fine.
    for banned in ("youtube.api", "from youtube", "import youtube"):
        assert banned not in low, banned


def test_server_still_bans_urllib_and_has_scheduled_status():
    py = (ROOT / "server.py").read_text()
    assert "urllib.request" not in py
    assert "scheduled" in srv.APPROVAL_STATUSES
    assert "schedule_hook" in py
    assert "CLIP_AUTOPOST" in py or "on_approved" in py


def test_api_approve_stays_approved_when_flag_off(tmp_path, monkeypatch):
    """Existing Approvals behaviour unchanged with default-off flag."""
    monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", "false")
    monkeypatch.delenv("CLIPPING_HUB_AUTOPOST_JOBS", raising=False)
    data = {
        "version": 1,
        "items": [{
            "ai_disclosure": False,
            "id": "a1", "video": "v.mp4", "caption": "c", "platforms": ["TikTok Business"],
            "scheduled_at": "", "status": "pending", "note": "", "decided_at": None,
        }],
    }
    data, item, changed = srv.decide_approval(data, {"op": "decide", "id": "a1", "status": "approved"})
    assert changed and item["status"] == "approved"
    # hook not applied by decide_approval itself — only the HTTP handler calls it
    jobs = tmp_path / "j.jsonl"
    assert S.on_approved(item, jobs_path=jobs, env={"CLIP_AUTOPOST_ENABLED": "false"}) is False
    assert item["status"] == "approved"


def test_api_approve_then_hook_schedules_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_AUTOPOST_ENABLED", "true")
    data = {
        "version": 1,
        "items": [{
            "ai_disclosure": False,
            "id": "a1", "video": "v.mp4", "caption": "c", "platforms": ["IG Business"],
            "scheduled_at": "2026-11-08T12:00:00-05:00", "status": "pending", "note": "", "decided_at": None,
        }],
    }
    data, item, changed = srv.decide_approval(data, {"op": "decide", "id": "a1", "status": "approved"})
    assert changed and item["status"] == "approved"
    jobs = tmp_path / "j.jsonl"
    assert S.on_approved(item, jobs_path=jobs) is True
    assert item["status"] == "scheduled"
    assert json.loads(jobs.read_text().splitlines()[0])["platforms"] == ["IG Business"]


def test_docs_describe_interface():
    doc = (ROOT / "docs" / "AUTOPOST_HOOK.md").read_text()
    assert "CLIP_AUTOPOST_ENABLED" in doc
    assert "data/autopost_jobs.jsonl" in doc
    assert "schedule_post" in doc
    assert "Postiz" in doc and "stub" in doc.lower()
