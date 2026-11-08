"""Strict reconcile + timeout_pending: never wrong-clip / never blind re-POST."""
from __future__ import annotations

import time
import youtube_label_step as Y
import post_idempotency as idem
import schedule_hook as S

TARGETS = {
    "version": 1,
    "poster": "opus",
    "targets": {
        "MAIN": {
            "name": "M", "handle": "@m", "yt": S.MAIN_YOUTUBE_CHANNEL_ID,
            "opus_post_account_id": "opus-main-acct", "opus_sub_account_id": "sub",
            "whop": "w",
        },
        "PAID": {
            "name": "P", "handle": "@p", "yt": "UC8TrAT8V-HacqYlqqqzIQKg",
            "opus_post_account_id": "opus-paid-acct", "whop": "w2",
        },
    },
}
VID = "reconVid001"  # 11


def test_reconcile_skips_other_clip_and_missing_clipid():
    """HIGH: other-clip row first + row missing clipId → neither picked; fail closed."""
    payload = {
        "items": [
            {
                "postId": "other",
                "projectId": "P",
                "clipId": "OTHERCLIP",
                "postAccountId": "opus-main-acct",
                "post_url": f"https://www.youtube.com/watch?v={VID}",
            },
            {
                "postId": "incomplete",
                "projectId": "P",
                # clipId missing
                "postAccountId": "opus-main-acct",
                "post_url": f"https://www.youtube.com/watch?v={VID}",
            },
        ]
    }
    calls = []

    def http_json(method, url, headers, body):
        calls.append(method)
        return payload

    found = Y.reconcile_opus_post(
        project_id="P", clip_id="C", post_account_id="opus-main-acct",
        http_json=http_json, token="t",
        item={"id": "job", "title": "T"},
    )
    assert found["ok"] is False
    assert found["error"] == "reconcile_none"
    assert found["count"] == 0


def test_reconcile_exact_match_one_row():
    def http_json(method, url, headers, body):
        return {"items": [{
            "postId": "found-post",
            "projectId": "P",
            "clipId": "C",
            "postAccountId": "opus-main-acct",
            "post_url": f"https://www.youtube.com/watch?v={VID}",
        }]}

    found = Y.reconcile_opus_post(
        project_id="P", clip_id="C", post_account_id="opus-main-acct",
        http_json=http_json, token="t",
    )
    assert found["ok"] is True
    assert found["post_id"] == "found-post"
    assert found["video_id"] == VID


def test_reconcile_ambiguous_two_matches_fail_closed():
    def http_json(method, url, headers, body):
        row = {
            "projectId": "P", "clipId": "C", "postAccountId": "opus-main-acct",
            "post_url": f"https://www.youtube.com/watch?v={VID}",
        }
        return {"items": [{**row, "postId": "a"}, {**row, "postId": "b"}]}

    found = Y.reconcile_opus_post(
        project_id="P", clip_id="C", post_account_id="opus-main-acct",
        http_json=http_json, token="t",
        item={"id": "j"},
    )
    assert found["ok"] is False
    assert found["error"] == "reconcile_ambiguous"
    assert found["count"] == 2


def test_stale_in_flight_reconciles_found_post(tmp_path):
    ledger = tmp_path / "led.jsonl"
    old = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 20 * 60))
    idem.append_row({
        "key": idem.make_key("stuck1", Y.CREATE_IDEMPOTENCY_PLATFORM),
        "job_id": "stuck1", "platform": Y.CREATE_IDEMPOTENCY_PLATFORM,
        "status": "in_flight", "opus_post_id": None, "at": old,
    }, path=ledger)
    posts = {"n": 0}

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            raise AssertionError("must not create-post when reconciling stale")
        return {"items": [{
            "postId": "found-post",
            "projectId": "P", "clipId": "C",
            "postAccountId": "opus-main-acct",
            "post_url": f"https://www.youtube.com/watch?v={VID}",
        }]}

    item = {
        "id": "stuck1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C",
        "platforms": ["Clipped Motions YouTube"],
    }
    out = Y.opus_upload_private(
        item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger,
    )
    assert posts["n"] == 0
    assert out["post_id"] == "found-post"
    assert out["video_id"] == VID
    assert idem.lookup("stuck1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "done"


def test_stale_in_flight_no_opus_marks_failed_and_alerts(tmp_path):
    ledger = tmp_path / "led.jsonl"
    old = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 20 * 60))
    idem.append_row({
        "key": idem.make_key("stuck2", Y.CREATE_IDEMPOTENCY_PLATFORM),
        "job_id": "stuck2", "platform": Y.CREATE_IDEMPOTENCY_PLATFORM,
        "status": "in_flight", "opus_post_id": None, "at": old,
    }, path=ledger)
    alerts = []

    def http_json(method, url, headers, body):
        if method == "POST":
            raise AssertionError("no create")
        return {"items": []}

    item = {
        "id": "stuck2", "title": "T", "caption": "C",
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
        assert "reconcile_waiting" in str(e) or "stuck" in str(e)
    row = idem.lookup("stuck2", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert row["status"] == "timeout_pending"
    assert row.get("reconcile_alerted") is True
    assert any("Stuck" in a or "stuck" in a.lower() for a in alerts)
    alerts2 = []
    try:
        Y.opus_upload_private(
            item, targets=TARGETS, http_json=http_json, token="t",
            ledger_path=ledger, push_fn=lambda t, b, key=None: alerts2.append(t) or True,
        )
        assert False
    except RuntimeError:
        pass
    assert idem.lookup("stuck2", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "timeout_pending"
    assert alerts2 == []


def test_create_timeout_alerts_and_marks_timeout_pending(tmp_path):
    ledger = tmp_path / "led.jsonl"
    alerts = []
    posts = {"n": 0}

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            raise TimeoutError("timed out")
        return {"items": []}  # nothing to reconcile yet

    item = {
        "id": "to1", "title": "T", "caption": "C",
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
        assert "timeout_pending" in str(e)
    assert posts["n"] == 1
    row = idem.lookup("to1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert row["status"] == "timeout_pending"
    assert any("stuck" in a.lower() or "Opus" in a for a in alerts)

    # Later Approve / reconcile: still no re-POST; finds the post now
    def http_json2(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            raise AssertionError("no re-POST on reconcile")
        return {"items": [{
            "postId": "late-post",
            "projectId": "P", "clipId": "C",
            "postAccountId": "opus-main-acct",
            "post_url": f"https://www.youtube.com/watch?v={VID}",
        }]}

    out = Y.opus_upload_private(
        item, targets=TARGETS, http_json=http_json2, token="t", ledger_path=ledger,
    )
    assert posts["n"] == 1  # still only the timed-out attempt
    assert out["post_id"] == "late-post"
    assert idem.lookup("to1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "done"


def test_non_timeout_create_error_reconciles_before_fail(tmp_path):
    ledger = tmp_path / "led.jsonl"
    posts = {"n": 0}

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            raise RuntimeError("opus_500_server_error")
        return {"items": [{
            "postId": "recovered",
            "projectId": "P", "clipId": "C",
            "postAccountId": "opus-main-acct",
            "post_url": f"https://www.youtube.com/watch?v={VID}",
        }]}

    item = {
        "id": "rec1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C",
        "platforms": ["Clipped Motions YouTube"],
    }
    out = Y.opus_upload_private(
        item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger,
    )
    assert posts["n"] == 1
    assert out["post_id"] == "recovered"
    assert idem.lookup("rec1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "done"


def test_timeout_then_empty_reconcile_then_approve_zero_posts(tmp_path):
    ledger = tmp_path / "led.jsonl"
    posts = {"n": 0}

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            raise TimeoutError("timed out")
        return {"items": []}

    item = {
        "id": "landed1", "title": "T", "caption": "C",
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
        assert "timeout_pending" in str(e)
    assert posts["n"] == 1
    assert idem.lookup("landed1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "timeout_pending"

    try:
        Y.opus_upload_private(
            item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger,
            push_fn=lambda *a, **k: True,
        )
        assert False
    except RuntimeError as e:
        assert "reconcile_waiting" in str(e)
    assert posts["n"] == 1
    assert idem.lookup("landed1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "timeout_pending"

    ok, row = idem.begin("landed1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert ok is False
    assert row.get("timeout_pending") or row.get("status") == "timeout_pending"
