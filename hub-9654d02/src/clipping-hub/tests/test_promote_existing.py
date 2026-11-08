"""Promote a named private YouTube video. Mocks only. No live update."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.error import URLError

import public_publish as P
import publish_adapters as A
import tools.private_proof as proof

MAIN = "UCgMuVjQmB9WvZtSz4e23THw"
PAID = "UC8TrAT8V-HacqYlqqqzIQKg"
VIDEO = "LM6jkXooWGc"
SHA = "ab" * 32
ROOT = Path(__file__).resolve().parents[1]


def _legacy_proof(path, *, channel=MAIN, video=VIDEO, sha=SHA, channel_field=None, key_channel=None):
    """458d756 later rows omit channel_id and item_id. The key still has both."""
    key_channel = key_channel if key_channel is not None else channel
    row = {
        "key": "private-proof:MAIN:%s:%s" % (key_channel, sha),
        "status": "readback_mismatch",
        "video_id": video,
        "public_success": False,
        "sha256": sha,
        "token_write": False,
        "reason": "private_label_not_confirmed",
    }
    if channel_field:
        row["channel_id"] = channel_field
    path.write_text(json.dumps(row) + "\n")


def _proof(path, *, channel=MAIN, video=VIDEO, sha=SHA):
    row = {
        "key": "private-proof:MAIN:%s:%s" % (channel, sha),
        "status": "readback_mismatch",
        "video_id": video,
        "item_id": "sample-07",
        "sha256": sha,
        "channel_id": channel,
        "public_success": False,
        "sample": "sample-07.mp4",
    }
    path.write_text(json.dumps(row) + "\n")


def _row(**extra):
    row = {
        "key": "youtube",
        "platform": "Clipped Motions YouTube",
        "public_action": "promote_existing",
        "will_dispatch": True,
        "existing_video_id": VIDEO,
        "artifact_sha256": SHA,
        "bound_channel_id": MAIN,
        "grant_channel": "MAIN",
        "account_id": "acct",
        "disclosures": {"ai": True, "paid": False},
    }
    row.update(extra)
    return row


def _http(calls, *, privacy="private", channel=MAIN, echo=True, read_privacy="public", read_echo=None):
    def http(method, url, headers, body):
        parsed = json.loads(body) if isinstance(body, (bytes, str)) and body else None
        calls.append((method, url, parsed))
        if method == "GET" and not any(c[0] == "PUT" for c in calls):
            status = {"privacyStatus": privacy, "embeddable": True, "license": "youtube", "publicStatsViewable": False,
                      "uploadStatus": "processed", "madeForKids": False, "selfDeclaredMadeForKids": False}
            if echo:
                status["containsSyntheticMedia"] = True
            return {"status": 200, "json": {"items": [{
                "id": VIDEO, "snippet": {"channelId": channel}, "status": status,
            }]}}
        if method == "PUT":
            return {"status": 200, "json": {"id": VIDEO, "status": parsed["status"]}}
        status = {"privacyStatus": read_privacy, "embeddable": True, "license": "youtube"}
        if read_echo is True or (read_echo is None and echo):
            status["containsSyntheticMedia"] = True
        return {"status": 200, "json": {"items": [{
            "id": VIDEO, "snippet": {"channelId": channel}, "status": status,
        }]}}
    return http


def test_unlisted_preflight_does_not_mutate(monkeypatch):
    calls = []
    monkeypatch.setattr(A, "HTTP", _http(calls, privacy="unlisted"))
    out = A.youtube_promote_existing(
        {"id": "sample-07"}, _row(), token="tok", http=A.HTTP,
        expected_channel_id=MAIN, video_id=VIDEO,
    )
    assert out["mutation"] is False
    assert out["reason"] == "youtube_privacy_not_private"
    assert [c[0] for c in calls] == ["GET"]


def test_promote_status_body_keeps_writable_fields_and_drops_output_only():
    body = A.youtube_promote_status_body({
        "privacyStatus": "private",
        "embeddable": True,
        "license": "youtube",
        "publicStatsViewable": False,
        "publishAt": "2026-11-08T00:00:00Z",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": False,
        "uploadStatus": "processed",
        "madeForKids": False,
        "failureReason": "none",
    }, ai=True)
    assert body["privacyStatus"] == "public"
    assert body["containsSyntheticMedia"] is True
    assert body["embeddable"] is True
    assert body["license"] == "youtube"
    assert body["publicStatsViewable"] is False
    for banned in ("publishAt", "selfDeclaredMadeForKids", "uploadStatus", "madeForKids", "failureReason"):
        assert banned not in body


def test_named_private_video_is_promoted_without_insert_or_snippet(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "youtube_token", lambda channel: "tok")
    _proof(tmp_path / "sample07-private.jsonl")
    calls = []
    monkeypatch.setattr(A, "HTTP", _http(calls))
    item = {"id": "sample-07", "caption": "c"}
    first = P.dispatch_platform(item, _row(), ledger_path=tmp_path / "promote.jsonl")
    second = P.dispatch_platform(item, _row(), ledger_path=tmp_path / "promote.jsonl")
    assert first["status"] == "done"
    assert first["public_action"] == "promote_existing"
    assert first["remote_id"] == VIDEO
    assert second["called"] is False
    methods = [c[0] for c in calls]
    assert methods == ["GET", "PUT", "GET"]
    put = calls[1][2]
    assert put["id"] == VIDEO
    assert "snippet" not in put
    assert "paidProductPlacementDetails" not in put
    assert "uploadStatus" not in put["status"]
    assert put["status"]["embeddable"] is True
    assert put["status"]["privacyStatus"] == "public"
    assert "youtube/v3/videos?part=status" in calls[1][1]
    text = (tmp_path / "promote.jsonl").read_text()
    assert "promote_existing" in text
    assert "pub:youtube:promote" in text
    assert VIDEO in text


def test_ledger_hit_does_not_insert_or_promote_without_the_named_action(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    _proof(tmp_path / "sample07-private.jsonl")
    calls = []
    monkeypatch.setattr(A, "HTTP", _http(calls))
    blocked = P.dispatch_platform(
        {"id": "sample-07"},
        _row(public_action="public_publish", existing_video_id=""),
        ledger_path=tmp_path / "insert.jsonl",
        runner=lambda item, row: calls.append("insert") or {"ok": True, "called": True},
    )
    assert blocked["called"] is False
    assert blocked["reason"] == "already_uploaded:" + VIDEO
    assert calls == []
    unnamed = P.dispatch_platform(
        {"id": "sample-07"},
        _row(existing_video_id=""),
        ledger_path=tmp_path / "guess.jsonl",
    )
    assert unnamed["called"] is False
    assert unnamed["reason"] == "existing_video_reconcile"


def test_wrong_channel_and_omitted_echo_do_not_insert(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "youtube_token", lambda channel: "tok")
    _proof(tmp_path / "sample07-private.jsonl", channel=PAID)
    calls = []
    monkeypatch.setattr(A, "HTTP", _http(calls, channel=PAID))
    wrong = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "wrong.jsonl")
    assert wrong["called"] is False
    assert wrong["reason"] == "youtube_channel_mismatch"
    assert calls == []
    (tmp_path / "sample07-private.jsonl").unlink()
    _proof(tmp_path / "sample07-main.jsonl", channel=MAIN)
    calls2 = []
    monkeypatch.setattr(A, "HTTP", _http(calls2, echo=False, read_echo=False))
    omitted = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "echo.jsonl")
    again = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "echo.jsonl")
    assert omitted["status"] == "unknown"
    assert omitted["reason"] == "youtube_synthetic_echo_omitted"
    assert omitted["remote_id"] == VIDEO
    assert again["called"] is False
    assert [c[0] for c in calls2].count("PUT") == 1
    evidence = json.loads((ROOT / "tests" / "fixtures" / "disclosure_evidence_sample07.json").read_text())
    recorded = P.record_disclosure_evidence(evidence, path=tmp_path / "disclosure_evidence.jsonl")
    assert recorded["ok"] is True and recorded["confirms_echo"] is False
    assert P.record_disclosure_evidence({"source": "ai_disclosure", "statement": "yes", "video_id": VIDEO, "item_id": "sample-07"}, path=tmp_path / "disclosure_evidence.jsonl")["ok"] is False
    assert omitted["status"] != "done"


def test_legacy_proof_key_supplies_the_missing_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "youtube_token", lambda channel: "tok")
    _legacy_proof(tmp_path / "legacy.jsonl")
    found = proof.find_existing_youtube(item_id="sample-07", sha256=SHA, channel_id=MAIN)
    assert found["channel_id"] == MAIN
    assert found["sha256"] == SHA
    assert found["video_id"] == VIDEO
    assert found["reason"] == "existing_video_reconcile"
    calls = []
    monkeypatch.setattr(A, "HTTP", _http(calls))
    out = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "promote.jsonl")
    assert out["public_action"] == "promote_existing"
    assert out["status"] == "done"
    assert [c[0] for c in calls] == ["GET", "PUT", "GET"]


def test_conflicting_or_malformed_proof_identity_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    calls = []
    monkeypatch.setattr(A, "HTTP", _http(calls))
    _legacy_proof(tmp_path / "conflict.jsonl", channel_field=PAID)
    conflict = proof.find_existing_youtube(item_id="", sha256=SHA, channel_id=MAIN)
    assert conflict["reason"] == "proof_identity_conflict"
    blocked = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "c.jsonl")
    assert blocked["called"] is False
    assert blocked["reason"] == "proof_identity_conflict"
    assert calls == []
    (tmp_path / "conflict.jsonl").unlink()
    _legacy_proof(tmp_path / "bad.jsonl", key_channel="not-a-channel")
    bad = proof.find_existing_youtube(item_id="", sha256=SHA, channel_id=MAIN)
    assert bad["reason"] == "proof_identity_malformed"
    again = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "b.jsonl")
    assert again["called"] is False
    assert again["reason"] == "proof_identity_malformed"
    assert calls == []


def test_incomplete_status_preflight_does_not_reset_writable_fields(monkeypatch):
    assert A.youtube_promote_status_body({
        "privacyStatus": "private", "license": "youtube", "publicStatsViewable": False,
    }, ai=True) is None
    calls = []

    def http(method, url, headers, body):
        calls.append(method)
        status = {"privacyStatus": "private", "license": "youtube", "publicStatsViewable": False, "uploadStatus": "processed"}
        return {"status": 200, "json": {"items": [{"id": VIDEO, "snippet": {"channelId": MAIN}, "status": status}]}}

    out = A.youtube_promote_existing(
        {"id": "sample-07"}, _row(), token="tok", http=http,
        expected_channel_id=MAIN, video_id=VIDEO,
    )
    assert out["reason"] == "youtube_status_preflight_incomplete"
    assert out["mutation"] is False
    assert calls == ["GET"]


def test_update_disconnect_is_reconcile_and_does_not_update_again(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "youtube_token", lambda channel: "tok")
    _proof(tmp_path / "sample07-private.jsonl")
    calls = []

    def http(method, url, headers, body):
        calls.append(method)
        if method == "PUT":
            raise URLError(OSError("connection reset"))
        status = {
            "privacyStatus": "private", "embeddable": True, "license": "youtube",
            "publicStatsViewable": False, "containsSyntheticMedia": True,
        }
        return {"status": 200, "json": {"items": [{"id": VIDEO, "snippet": {"channelId": MAIN}, "status": status}]}}

    monkeypatch.setattr(A, "HTTP", http)
    first = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "promote.jsonl")
    second = P.dispatch_platform({"id": "sample-07"}, _row(), ledger_path=tmp_path / "promote.jsonl")
    assert first["status"] == "unknown"
    assert first["reason"] == "transport_uncertain"
    assert first["public_action"] == "promote_existing"
    assert first["remote_id"] == VIDEO
    assert second["called"] is False
    assert second["public_action"] == "promote_existing"
    assert calls.count("PUT") == 1


def test_held_preview_blocks_promote_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "_armed", lambda key, channel: True)
    sample = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    sha = hashlib.sha256(sample).hexdigest()
    _legacy_proof(tmp_path / "legacy.jsonl", sha=sha)
    import schedule_hook as sched

    def route(item, targets=None, channels=None):
        return {
            "target": "MAIN", "name": "Clipped Motions", "handle": "@clippedmotions",
            "channel_id": MAIN, "paid_promotion": False, "held": True, "blocked": False,
            "block_reason": "alliance_submission_window", "deny_platforms": ["FB Page"],
            "campaign_config": "held", "storyblocks": False, "needs_destination": False,
            "hashtags": [],
        }

    monkeypatch.setattr(sched, "route_for_item", route)
    manifest = P.build_manifest({
        "id": "sample-07", "caption": "c", "title": "T", "ai_disclosure": True, "rights_ok": True,
        "video": "/samples/sample-a.mp4", "platforms": ["Clipped Motions YouTube"], "status": "pending",
    })
    row = manifest["platforms"][0]
    assert manifest["held"] is True
    assert manifest["will_dispatch_any"] is False
    assert row["public_action"] == "blocked"
    assert row["will_dispatch"] is False
    assert "Promote existing" in row["line"]
    assert VIDEO in row["line"]
    assert "held" in row["line"]
