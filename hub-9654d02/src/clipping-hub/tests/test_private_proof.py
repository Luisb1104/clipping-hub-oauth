"""Private YouTube proof. Mocks only. No live token and no upload."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

import publish_adapters as A
import public_publish as P
import schedule_hook as S
import tools.private_proof as proof

MAIN = S.MAIN_YOUTUBE_CHANNEL_ID
TOKEN = {"access_token": "stale-access", "refresh_token": "refresh-value", "bound_channel_id": MAIN}


def _refresh(channel, token):
    assert token.get("refresh_token") == "refresh-value"
    return "fresh-access", None


@pytest.fixture(autouse=True)
def _app_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    return tmp_path


def _targets():
    cfg = S.load_targets()
    assert cfg["targets"]["MAIN"]["yt"] == MAIN
    return cfg


def _http(calls, *, put=None, read=None):
    def http(method, url, headers, body):
        calls.append((method, url, body))
        if method == "POST":
            assert headers["Authorization"] == "Bearer fresh-access"
            meta = json.loads(body)
            assert meta["status"]["privacyStatus"] == "private"
            assert meta["status"]["containsSyntheticMedia"] is True
            assert "public" not in json.dumps(meta["status"])
            assert "unlisted" not in json.dumps(meta)
            assert "paidProductPlacementDetails" not in meta
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=proof"}, "json": {}}
        if method == "PUT":
            if put:
                return put()
            return {"status": 201, "json": {
                "id": "vidproof1",
                "snippet": {"channelId": MAIN},
                "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
            }}
        if method == "GET":
            if read:
                return read()
            return {"status": 200, "json": {"items": [{
                "id": "vidproof1",
                "snippet": {"channelId": MAIN},
                "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
            }]}}
        raise AssertionError(method)
    return http


def _run(tmp_path, http, **kw):
    return proof.execute_private_proof(
        item_id="sample07",
        channel="MAIN",
        channel_id=MAIN,
        sample="sample07.mp4",
        ledger=str(tmp_path / "operator-ledger.jsonl"),
        token=TOKEN,
        http=http,
        refresh=_refresh,
        targets=_targets(),
        **kw,
    )


def test_dry_run_does_not_call_http(tmp_path, monkeypatch):
    monkeypatch.setattr(proof, "default_http", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    code = proof.main([
        "--item", "sample07", "--channel", "MAIN", "--channel-id", MAIN,
        "--sample", "sample07.mp4", "--ledger", str(tmp_path / "operator-ledger.jsonl"),
    ])
    assert code == 0
    assert proof.main(["--execute"]) == 2


def test_execute_is_private_and_does_not_touch_public_paths(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv(P.FLAG, "false")
    approvals = Path(monkeypatch.setenv("CLIPPING_HUB_APPROVALS", str(tmp_path / "approvals.json")) or tmp_path / "approvals.json")
    # setenv returns the value, not the path. Write the isolated approvals file explicitly.
    approvals = tmp_path / "approvals.json"
    approvals.write_text('{"items":[]}')
    before = approvals.read_bytes()
    targets_path = Path(S.TARGETS_PATH)
    targets_before = targets_path.read_bytes()

    def boom(*a, **k):
        raise AssertionError("public path")

    monkeypatch.setattr(P, "dispatch_item", boom)
    monkeypatch.setattr(A, "youtube_upload", boom)
    out = _run(tmp_path, _http(calls))
    assert out["ok"] is True
    assert out["public_success"] is False
    assert out["marks_public_posted"] is False
    assert out["status"] == "readback_ok"
    assert out["video_id"] == "vidproof1"
    assert out["privacy"] == "private"
    assert [c[0] for c in calls] == ["POST", "PUT", "GET"]
    assert "privacyStatus=public" not in calls[0][1]
    assert os_environ_flag_off()
    assert approvals.read_bytes() == before
    assert targets_path.read_bytes() == targets_before
    ledger = (tmp_path / "operator-ledger.jsonl").read_text()
    assert "test-access-token" not in ledger
    assert '"public_success":false' in ledger.replace(" ", "")
    assert "vidproof1" in ledger


def os_environ_flag_off():
    import os
    return os.environ.get(P.FLAG, "false").strip().lower() not in ("1", "true", "yes", "on")


def test_mismatch_and_readback_failure_keep_video_id_and_do_not_retry(tmp_path):
    calls = []

    def wrong():
        return {"status": 200, "json": {"items": [{
            "id": "vidproof1",
            "snippet": {"channelId": "UC8TrAT8V-HacqYlqqqzIQKg"},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
        }]}}

    first = _run(tmp_path, _http(calls, read=wrong))
    assert first["ok"] is False
    assert first["public_success"] is False
    assert first["status"] == "readback_mismatch"
    assert first["video_id"] == "vidproof1"
    second = _run(tmp_path, _http(calls))
    assert second["status"] == "duplicate"
    assert second["video_id"] == "vidproof1"
    assert second["executes_network"] is False
    assert [c[0] for c in calls] == ["POST", "PUT", "GET"]

    calls2 = []

    def blow():
        raise TimeoutError("readback")

    other = tmp_path / "readback-ledger.jsonl"
    failed = proof.execute_private_proof(
        item_id="sample07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
        ledger=str(other), token=TOKEN, http=_http(calls2, read=blow), refresh=_refresh, targets=_targets(),
    )
    assert failed["status"] == "duplicate"
    assert failed["reason"] == "existing_video_reconcile"
    assert failed["video_id"] == "vidproof1"
    assert failed["public_success"] is False
    assert calls2 == []
    assert not other.exists()


def test_readback_timeout_keeps_the_video_id(tmp_path):
    calls = []

    def blow():
        raise TimeoutError("readback")

    failed = _run(tmp_path, _http(calls, read=blow))
    assert failed["status"] == "readback_failed"
    assert failed["video_id"] == "vidproof1"
    assert failed["public_success"] is False
    again = _run(tmp_path, _http(calls))
    assert again["status"] == "duplicate"
    assert again["video_id"] == "vidproof1"
    assert [c[0] for c in calls] == ["POST", "PUT", "GET"]


def test_interrupted_upload_is_not_repeated(tmp_path):
    calls = []

    def put():
        raise TimeoutError("put")

    out = _run(tmp_path, _http(calls, put=put))
    assert out["status"] == "interrupted"
    assert out["video_id"] is None
    assert out["public_success"] is False
    again = _run(tmp_path, _http(calls))
    assert again["status"] == "duplicate"
    assert again["executes_network"] is False
    assert [c[0] for c in calls] == ["POST", "PUT"]
    assert sum(1 for c in calls if c[0] == "POST") == 1


def test_identity_mismatches_do_not_call_http(tmp_path):
    calls = []
    http = _http(calls)
    base = dict(item_id="sample07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
                ledger=str(tmp_path / "operator-ledger.jsonl"), token=TOKEN, http=http, refresh=_refresh, targets=_targets())
    assert proof.execute_private_proof(**dict(base, channel="PAID"))["reason"] == "channel_not_main"
    assert proof.execute_private_proof(**dict(base, channel_id="UC8TrAT8V-HacqYlqqqzIQKg"))["reason"] == "channel_id_mismatch"
    assert proof.execute_private_proof(**dict(base, token={"refresh_token": "refresh-value", "bound_channel_id": "UC8TrAT8V-HacqYlqqqzIQKg"}))["reason"] == "token_channel_mismatch"
    assert proof.execute_private_proof(**dict(base, token={"access_token": "", "bound_channel_id": MAIN}))["reason"] == "token_missing"
    assert proof.execute_private_proof(**dict(base, sample="../server.py"))["reason"] == "sample_not_basename"
    assert proof.execute_private_proof(**dict(base, ledger=str(tmp_path / "post_ledger.jsonl")))["reason"] == "ledger_is_public"
    assert calls == []


def test_torn_ledger_blocks_a_second_upload(tmp_path):
    calls = []
    ledger = tmp_path / "operator-ledger.jsonl"
    ledger.write_text('{"key":"x","status":"uploading"}\n{"key":')
    out = _run(tmp_path, _http(calls))
    assert out["status"] == "refused"
    assert out["reason"] == "ledger_corrupt"
    assert out["executes_network"] is False
    assert calls == []


def test_short_write_and_fsync_failure_do_not_upload(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(proof, "_io_write", lambda fd, data: len(data) - 1)
    out = _run(tmp_path, _http(calls))
    assert out["reason"] == "ledger_short_write"
    assert calls == []
    monkeypatch.setattr(proof, "_io_write", os.write)

    def fail_fsync(fd):
        raise OSError("fsync")

    monkeypatch.setattr(proof, "_io_fsync", fail_fsync)
    out = _run(tmp_path, _http(calls))
    assert out["reason"] == "ledger_fsync_failed"
    assert calls == []


def test_concurrent_execute_uploads_once(tmp_path):
    calls = []

    def http(method, url, headers, body):
        calls.append(method)
        if method == "POST":
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=c"}, "json": {}}
        if method == "PUT":
            return {"status": 200, "json": {"id": "vidconc", "status": {"privacyStatus": "private", "containsSyntheticMedia": True}, "snippet": {"channelId": MAIN}}}
        return {"status": 200, "json": {"items": [{"id": "vidconc", "snippet": {"channelId": MAIN}, "status": {"privacyStatus": "private", "containsSyntheticMedia": True}}]}}

    results = []

    def go():
        results.append(_run(tmp_path, http))

    threads = [threading.Thread(target=go) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls.count("POST") == 1
    statuses = sorted(row["status"] for row in results)
    assert statuses == ["duplicate", "readback_ok"]
    assert all(row["public_success"] is False for row in results)


def test_put_200_with_id_is_accepted_and_refresh_is_not_persisted(tmp_path, monkeypatch):
    import youtube_label_step as Y
    calls = []

    def put():
        return {"status": 200, "json": {
            "id": "vid200",
            "snippet": {"channelId": MAIN},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
        }}

    def read():
        return {"status": 200, "json": {"items": [{
            "id": "vid200",
            "snippet": {"channelId": MAIN},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
        }]}}

    out = _run(tmp_path, _http(calls, put=put, read=read))
    assert out["status"] == "readback_ok"
    assert out["video_id"] == "vid200"
    assert out["public_success"] is False
    saved = []
    monkeypatch.setattr(Y, "save_token", lambda *a, **k: saved.append(1) or True)
    monkeypatch.setattr(Y, "read_client_id", lambda: "client-id")
    monkeypatch.setattr(Y, "read_client_secret", lambda: "client-secret")
    access, err = proof.nonpersisting_refresh("MAIN", dict(TOKEN), lambda url, body: {"access_token": "fresh-from-refresh"})
    assert err is None and access == "fresh-from-refresh"
    assert saved == []
    assert proof.PROOF_ITEM_ID == "sample-07"
    assert proof.PROOF_SAMPLE == "sample-07.mp4"
    assert out["rights_certified"] is False


def test_ledger_rejects_escape_and_public_alias(tmp_path):
    calls = []
    nested = tmp_path / "nested"
    nested.mkdir()
    outside = proof.execute_private_proof(
        item_id="sample07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
        ledger=str(nested / "proof.jsonl"), token=TOKEN, http=_http(calls), refresh=_refresh, targets=_targets(),
    )
    assert outside["reason"] == "ledger_outside_data_dir"
    link = tmp_path / "proof.jsonl"
    link.symlink_to(tmp_path / "elsewhere.jsonl")
    escaped = proof.execute_private_proof(
        item_id="sample07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
        ledger=str(link), token=TOKEN, http=_http(calls), refresh=_refresh, targets=_targets(),
    )
    assert escaped["reason"] == "ledger_symlink"
    public = tmp_path / "post_ledger.jsonl"
    public.write_text("")
    alias = tmp_path / "alias.jsonl"
    os.link(public, alias)
    aliased = proof.execute_private_proof(
        item_id="sample07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
        ledger=str(alias), token=TOKEN, http=_http(calls), refresh=_refresh, targets=_targets(),
    )
    assert aliased["reason"] == "ledger_is_public"
    assert calls == []


def test_symlink_swap_is_not_followed(tmp_path, monkeypatch):
    import publish_runtime as RT
    secret = "swapped-secret-value"
    real = tmp_path / "real-secret.json"
    real.write_text(json.dumps({"tiktok": {"available": True, "api_key": secret, "integration_id": "int_postiz_1"}}))
    real.chmod(0o600)
    link = tmp_path / "publish-config.json"
    link.symlink_to(real)
    monkeypatch.setenv("CLIPPING_HUB_PUBLISH_CONFIG", str(link))
    assert RT.load_publish_credentials() == {}
    assert any(p["problem"] == "symlink_or_unreadable" for p in RT.config_problems())
    assert secret not in json.dumps(RT.config_problems())
    token_link = tmp_path / "token.json"
    token_link.symlink_to(real)
    assert proof._token_from_file(str(token_link)) is None


def test_publish_config_mode_must_be_0600(tmp_path, monkeypatch):
    import publish_runtime as RT
    secret = "tok_test_secret_value"
    path = tmp_path / "publish-config.json"
    path.write_text(json.dumps({"tiktok": {"available": True, "api_key": secret, "integration_id": "int_postiz_1"}}))
    path.chmod(0o644)
    monkeypatch.setenv("CLIPPING_HUB_PUBLISH_CONFIG", str(path))
    assert RT.load_publish_credentials() == {}
    assert any(p["problem"] == "mode_not_0600" for p in RT.config_problems())
    assert secret not in json.dumps(RT.config_problems())
    path.chmod(0o600)
    assert "tiktok" in RT.configured_platform_names()


def _proof_row(video_id, status="readback_mismatch"):
    return {
        "key": "private-proof:MAIN:%s:abc" % MAIN,
        "status": status,
        "video_id": video_id,
        "item_id": "sample-07",
        "sha256": "abc",
        "channel_id": MAIN,
        "public_success": False,
        "reason": "private_label_not_confirmed",
    }


def test_omitted_private_echo_blocks_a_second_upload(tmp_path):
    calls = []

    def read_omitted():
        return {"status": 200, "json": {"items": [{
            "id": "LM6jkXooWGc",
            "snippet": {"channelId": MAIN},
            "status": {"privacyStatus": "private"},
        }]}}

    first = _run(tmp_path, _http(calls, read=read_omitted))
    assert first["status"] == "echo_unconfirmed"
    assert first["reason"] == "youtube_synthetic_echo_omitted"
    assert first["ok"] is False
    assert first["public_success"] is False
    assert first["video_id"] == "vidproof1"
    again = _run(tmp_path, _http(calls))
    assert again["status"] == "duplicate"
    assert again["video_id"] == "vidproof1"
    assert again["executes_network"] is False
    assert [c[0] for c in calls] == ["POST", "PUT", "GET"]


def test_cross_ledger_reconciles_sample07_without_a_second_object_or_queue_write(tmp_path, monkeypatch):
    import public_publish as P
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    proof_path = tmp_path / "sample07-private.jsonl"
    lines = [
        {"key": _proof_row(None)["key"], "status": "uploading", "video_id": None, "item_id": "sample-07", "sha256": "abc", "channel_id": MAIN, "public_success": False},
        {"key": _proof_row(None)["key"], "status": "uploaded", "video_id": "LM6jkXooWGc", "item_id": "sample-07", "sha256": "abc", "channel_id": MAIN, "public_success": False},
        _proof_row("LM6jkXooWGc"),
    ]
    proof_path.write_text("".join(json.dumps(row) + "\n" for row in lines))
    public = tmp_path / "post_ledger.jsonl"
    public.write_text(json.dumps({
        "key": "sample-07::pub:youtube", "job_id": "sample-07", "platform": "pub:youtube",
        "status": "failed", "remote_id": None, "error": "oauth_required",
    }) + "\n")
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(public))
    queue = tmp_path / "approvals.json"
    queue.write_text(json.dumps({"version": 1, "items": [{"id": "sample-07", "youtube_video_id": ""}]}))
    before = queue.read_bytes()
    calls = []
    out = proof.execute_private_proof(
        item_id="sample-07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
        ledger=str(tmp_path / "second-ledger.jsonl"), token=TOKEN, http=_http(calls),
        refresh=_refresh, targets=_targets(),
    )
    assert out["status"] == "duplicate"
    assert out["reason"] == "existing_video_reconcile"
    assert out["video_id"] == "LM6jkXooWGc"
    assert out["executes_network"] is False
    assert calls == []
    assert not (tmp_path / "second-ledger.jsonl").exists()
    assert queue.read_bytes() == before
    monkeypatch.setenv(P.FLAG, "true")
    hit = P.dispatch_platform(
        {"id": "sample-07"},
        {
            "key": "youtube", "platform": "Clipped Motions YouTube",
            "public_action": "public_publish", "will_dispatch": True,
            "artifact_sha256": "not-the-sample", "bound_channel_id": MAIN, "account_id": "acct",
        },
        ledger_path=tmp_path / "public-try.jsonl",
        runner=lambda item, row: calls.append("public") or {"ok": True, "called": True},
    )
    assert hit["called"] is False
    assert hit["remote_id"] == "LM6jkXooWGc"
    assert hit["reason"] == "existing_video_reconcile"
    assert calls == []
    assert queue.read_bytes() == before
    other = proof.find_existing_youtube(item_id="other-item", sha256="different", channel_id=MAIN)
    assert other is None


def test_proof_rows_keep_item_and_artifact_identity(tmp_path):
    calls = []
    out = _run(tmp_path, _http(calls))
    assert out["status"] == "readback_ok"
    rows = [json.loads(line) for line in (tmp_path / "operator-ledger.jsonl").read_text().splitlines() if line.strip()]
    assert len(rows) >= 3
    assert {row["status"] for row in rows} >= {"uploading", "uploaded", "readback_ok"}
    for row in rows:
        assert row["item_id"] == "sample07"
        assert row["sha256"]
        assert row["sample"] == "sample07.mp4"
        assert row["channel_id"] == MAIN
    uploaded = [row for row in rows if row["status"] == "uploaded"][-1]
    assert uploaded["video_id"] == "vidproof1"
    assert uploaded["item_id"] == "sample07"


def test_malformed_public_ledger_fails_closed_and_legacy_failure_does_not(tmp_path, monkeypatch):
    import public_publish as pub
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    legacy = {
        "key": "sample-07::pub:youtube", "job_id": "sample-07", "platform": "pub:youtube",
        "status": "failed", "opus_post_id": None, "remote_id": None, "error": "oauth_required",
    }
    public = tmp_path / "post_ledger.jsonl"
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(public))
    public.write_text(json.dumps(legacy) + "\n" + '{"key":\n')
    calls = []
    blocked = proof.execute_private_proof(
        item_id="sample-07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
        ledger=str(tmp_path / "blocked-ledger.jsonl"), token=TOKEN, http=_http(calls),
        refresh=_refresh, targets=_targets(),
    )
    assert blocked["status"] == "refused"
    assert blocked["reason"] == "public_ledger_corrupt"
    assert blocked["executes_network"] is False
    assert calls == []
    assert not (tmp_path / "blocked-ledger.jsonl").exists()
    monkeypatch.setenv(pub.FLAG, "true")
    hit = pub.dispatch_platform(
        {"id": "sample-07"},
        {
            "key": "youtube", "platform": "Clipped Motions YouTube",
            "public_action": "public_publish", "will_dispatch": True,
            "artifact_sha256": "abc", "bound_channel_id": MAIN, "account_id": "acct",
        },
        ledger_path=tmp_path / "would-post.jsonl",
        runner=lambda item, row: calls.append("runner"),
    )
    assert hit["called"] is False
    assert hit["status"] == "blocked"
    assert hit["reason"] == "public_ledger_corrupt"
    assert calls == []
    public.write_text(json.dumps(legacy) + "\n")
    assert proof.find_existing_youtube(item_id="sample-07", sha256="abc", channel_id=MAIN) is None
    clean_calls = []
    clean = proof.execute_private_proof(
        item_id="sample-07", channel="MAIN", channel_id=MAIN, sample="sample07.mp4",
        ledger=str(tmp_path / "clean-ledger.jsonl"), token=TOKEN, http=_http(clean_calls),
        refresh=_refresh, targets=_targets(),
    )
    assert clean["status"] == "readback_ok"
    assert [c[0] for c in clean_calls] == ["POST", "PUT", "GET"]


def test_corrupt_private_ledger_refuses_another_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    (tmp_path / "torn.jsonl").write_text('{"key":"private-proof:MAIN:abc","status":"uploaded"}\n{"key":')
    calls = []
    out = _run(tmp_path, _http(calls))
    assert out["reason"] == "private_ledger_corrupt"
    assert out["executes_network"] is False
    assert calls == []
