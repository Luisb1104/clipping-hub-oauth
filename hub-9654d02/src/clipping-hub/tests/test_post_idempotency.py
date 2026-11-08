"""Ledger begin() exclusive flock + stale in_flight + operator unstick."""
from __future__ import annotations

import json
import stat
import threading
import time
from pathlib import Path

import post_idempotency as idem
import platform_capabilities as caps
import schedule_hook as S


def test_begin_flock_only_one_of_four_threads_acquires(tmp_path):
    ledger = tmp_path / "led.jsonl"
    barrier = threading.Barrier(4)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait(timeout=5)
        ok, row = idem.begin("jobX", "youtube:create", path=ledger)
        with lock:
            results.append((ok, row.get("status")))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(results) == 4
    acquired = [r for r in results if r[0] is True]
    blocked = [r for r in results if r[0] is False]
    assert len(acquired) == 1, results
    assert len(blocked) == 3, results
    assert acquired[0][1] == "in_flight"


def test_stale_in_flight_flagged_not_reacquired(tmp_path):
    ledger = tmp_path / "led.jsonl"
    # Seed an old in_flight
    old_ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 20 * 60))
    idem.append_row({
        "key": idem.make_key("jobS", "youtube:create"),
        "job_id": "jobS",
        "platform": "youtube:create",
        "status": "in_flight",
        "opus_post_id": None,
        "at": old_ts,
    }, path=ledger)
    ok, row = idem.begin("jobS", "youtube:create", path=ledger, ttl_s=15 * 60)
    assert ok is False
    assert row.get("stale_in_flight") is True


def test_unstick_marks_failed(tmp_path):
    ledger = tmp_path / "led.jsonl"
    # Fresh in_flight refused
    idem.begin("jobU", "youtube:create", path=ledger)
    ok, err = idem.unstick("jobU", "youtube:create", path=ledger, reason="operator_unstick")
    assert ok is False
    assert err.get("error") == "refuse_fresh_in_flight"
    # Stale in_flight allowed
    import time
    old = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 20 * 60))
    idem.append_row({
        "key": idem.make_key("jobU2", "youtube:create"),
        "job_id": "jobU2", "platform": "youtube:create",
        "status": "in_flight", "opus_post_id": None, "at": old,
    }, path=ledger)
    ok, row = idem.unstick("jobU2", "youtube:create", path=ledger, reason="operator_unstick")
    assert ok is True
    assert row["status"] == "failed"
    assert "operator_unstick" in (row.get("error") or "")
    ok2, _ = idem.begin("jobU2", "youtube:create", path=ledger)
    assert ok2 is True


def test_session_url_cap_is_2048_and_an_open_session_cannot_be_unstuck(tmp_path):
    prefix = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id="
    fit = prefix + ("a" * (2048 - len(prefix)))
    assert len(fit) == 2048
    assert idem.stored_remote(fit) == fit
    assert idem.stored_remote(fit + "b") is None
    ledger = tmp_path / "led.jsonl"
    idem.mark_unknown(
        "jobSess", "pub:youtube", path=ledger, remote_id=fit, upload_length=4,
        session_observation="upload_incomplete",
    )
    row = idem.lookup("jobSess", "pub:youtube", path=ledger)
    assert row["status"] == "unknown"
    assert row["remote_id"] == fit
    assert row["session_observation"] == "upload_incomplete"
    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600
    ok, err = idem.unstick("jobSess", "pub:youtube", path=ledger)
    assert ok is False
    assert err["error"] == "refuse_upload_evidence"
    assert "row" not in err
    assert "remote_id" not in err
    assert "upload_id" not in json.dumps(err)
    acquired, existing = idem.begin("jobSess", "pub:youtube", path=ledger)
    assert acquired is False
    assert existing.get("status") == "unknown"


def test_unstick_refuses_done_and_unknown(tmp_path):
    ledger = tmp_path / "led.jsonl"
    idem.begin("jobD", "youtube:create", path=ledger)
    idem.mark_done("jobD", "youtube:create", opus_post_id="p1", path=ledger)
    ok, err = idem.unstick("jobD", "youtube:create", path=ledger)
    assert ok is False and err.get("error") == "refuse_done"
    ok2, err2 = idem.unstick("no-such-job", "youtube:create", path=ledger)
    assert ok2 is False and err2.get("error") == "unknown_job"
    ok3, err3 = idem.unstick("../evil", "youtube:create", path=ledger)
    assert ok3 is False and err3.get("error") == "bad_job_id"


def test_opus_accounts_from_post_targets_not_hardcoded():
    assert not hasattr(caps, "DEFAULT_OPUS_ACCOUNTS")
    targets = {
        "version": 1,
        "targets": {
            "MAIN": {"opus_post_account_id": "acct-main", "opus_sub_account_id": "sub-m", "yt": S.MAIN_YOUTUBE_CHANNEL_ID},
            "PAID": {"opus_post_account_id": "acct-paid", "yt": "UCpaidxxxxxxx"},
        },
    }
    out = caps.opus_accounts_from_post_targets(targets)
    assert out["MAIN"]["post_account_id"] == "acct-main"
    assert out["PAID"]["post_account_id"] == "acct-paid"
    # No hard-coded live Opus ids in the module source
    src = Path(caps.__file__).read_text()
    assert "6aedeb42386c37c006241619" not in src


def _failed_no_id(job="diag1"):
    return {
        "key": job + "::pub:youtube",
        "job_id": job,
        "platform": "pub:youtube",
        "status": "failed",
        "opus_post_id": None,
        "remote_id": None,
        "error": "oauth_required",
    }


def test_legacy_failed_row_without_id_still_retries(tmp_path):
    ledger = tmp_path / "led.jsonl"
    ledger.write_text(json.dumps(_failed_no_id()) + "\n")
    ok, row = idem.begin("diag1", "pub:youtube", path=ledger)
    assert ok is True
    assert row["status"] == "in_flight"
    assert idem.lookup("diag1", "pub:youtube", path=ledger)["status"] == "in_flight"


def test_malformed_public_ledger_line_refuses_begin(tmp_path):
    ledger = tmp_path / "led.jsonl"
    original = json.dumps(_failed_no_id()) + "\n" + '{"key": "torn", "status":\n'
    ledger.write_text(original)
    ok, row = idem.begin("diag1", "pub:youtube", path=ledger)
    assert ok is False
    assert row["ledger_corrupt"] is True
    assert row["status"] == "ledger_corrupt"
    assert ledger.read_text() == original
    try:
        idem.parse_ledger_text('{"status": "failed"}\n')
        assert False
    except idem.LedgerCorrupt:
        pass
