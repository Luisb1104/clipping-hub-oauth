"""create_error terminal state + approvals flock + strict tick force."""
from __future__ import annotations

import json
import threading
import time

import post_idempotency as idem
import schedule_hook as Sched
import server as Srv
import youtube_label_step as Y

TARGETS = {
    "version": 1,
    "poster": "opus",
    "targets": {
        "MAIN": {
            "name": "M", "handle": "@m", "yt": Sched.MAIN_YOUTUBE_CHANNEL_ID,
            "opus_post_account_id": "opus-main-acct", "opus_sub_account_id": "sub",
            "whop": "w",
        },
        "PAID": {
            "name": "P", "handle": "@p", "yt": "UC8TrAT8V-HacqYlqqqzIQKg",
            "opus_post_account_id": "opus-paid-acct", "whop": "w2",
        },
    },
}


def test_non_timeout_create_error_is_terminal_zero_posts(tmp_path):
    ledger = tmp_path / "led.jsonl"
    posts = {"n": 0}
    alerts = []

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            raise RuntimeError("opus_500")
        return {"items": []}

    item = {
        "id": "ce1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C",
        "platforms": ["Clipped Motions YouTube"],
    }
    try:
        Y.opus_upload_private(
            item, targets=TARGETS, http_json=http_json, token="t",
            ledger_path=ledger, push_fn=lambda t, b, key=None: alerts.append(t) or True,
        )
        assert False
    except RuntimeError as e:
        assert "create_error" in str(e) or "opus_500" in str(e)
    assert posts["n"] == 1
    row = idem.lookup("ce1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert row["status"] == "create_error"
    assert any("unstick" in a.lower() or "failed" in a.lower() for a in alerts)

    try:
        Y.opus_upload_private(
            item, targets=TARGETS, http_json=http_json, token="t",
            ledger_path=ledger, push_fn=lambda *a, **k: True,
        )
        assert False
    except RuntimeError:
        pass
    assert posts["n"] == 1
    ok, row2 = idem.begin("ce1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert ok is False
    assert row2.get("create_error") or row2.get("status") == "create_error"

    uok, _ = idem.unstick("ce1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert uok is True
    ok3, _ = idem.begin("ce1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert ok3 is True


def test_missing_post_id_is_terminal_zero_posts(tmp_path):
    ledger = tmp_path / "led.jsonl"
    posts = {"n": 0}

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            return {"data": {}}
        return {"items": []}

    item = {
        "id": "np1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C",
        "platforms": ["Clipped Motions YouTube"],
    }
    try:
        Y.opus_upload_private(
            item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger,
            push_fn=lambda *a, **k: True,
        )
        assert False
    except RuntimeError as e:
        assert "opus_no_post_id" in str(e)
    assert posts["n"] == 1
    assert idem.lookup("np1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "create_error"

    try:
        Y.opus_upload_private(
            item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger,
            push_fn=lambda *a, **k: True,
        )
        assert False
    except RuntimeError:
        pass
    assert posts["n"] == 1


def test_approvals_lock_concurrency(tmp_path):
    ap = tmp_path / "approvals.json"
    ap.write_text(json.dumps({
        "version": 1,
        "items": [
            {"id": "a", "status": "pending", "video": "v", "caption": "c", "platforms": []},
            {"id": "b", "status": "pending", "video": "v", "caption": "c", "platforms": []},
        ],
    }))
    barrier = threading.Barrier(2)
    errors = []

    def worker(iid):
        try:
            barrier.wait(timeout=5)
            with Srv.approvals_lock(ap):
                data = Srv.load_approvals(ap)
                for item in data["items"]:
                    if item["id"] == iid:
                        item["status"] = "rejected"
                        item["note"] = "n-" + iid
                        item["decided_at"] = "t"
                time.sleep(0.05)
                Srv.save_approvals(data, ap)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not errors, errors
    final = Srv.load_approvals(ap)
    by = {i["id"]: i["status"] for i in final["items"]}
    assert by == {"a": "rejected", "b": "rejected"}


def test_parse_tick_force_strict():
    assert Srv.parse_tick_force(True) is True
    assert Srv.parse_tick_force("true") is True
    assert Srv.parse_tick_force("TRUE") is True
    assert Srv.parse_tick_force("1") is True
    assert Srv.parse_tick_force(1) is True
    assert Srv.parse_tick_force(False) is False
    assert Srv.parse_tick_force("false") is False
    assert Srv.parse_tick_force("0") is False
    assert Srv.parse_tick_force(0) is False
    assert Srv.parse_tick_force("yes") is False
    assert Srv.parse_tick_force(None) is False


def test_force_still_respects_five_min_cap(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(Srv, "_TICK_STATE_PATH", tmp_path / "tick.json")
    monkeypatch.setattr(Srv, "TICK_MIN_GAP_S", 5 * 60)
    monkeypatch.setattr(Y, "maybe_warn_grant_expiry", lambda *a, **k: False)
    monkeypatch.setattr(Y, "check_grant_alive", lambda *a, **k: (True, None))
    r1 = Srv.run_youtube_label_tick(force=False)
    assert r1.get("error") != "label_step_off"
    r2 = Srv.run_youtube_label_tick(force=True)
    assert r2.get("skipped") is True
    assert r2.get("error") == "rate_limited"
