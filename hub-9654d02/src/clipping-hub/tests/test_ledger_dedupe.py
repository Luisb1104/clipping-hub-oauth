"""Ledger dedupe and approvals reconcile for sample-07.

Fixtures mirror the live private-proof and promote lines: the queue still says
pending with an empty youtube_video_id, which is the fail-before state. No
network, no sample media, no live approvals file.
"""
import json
import shutil
from pathlib import Path

import ledger_dedupe as dedupe
import server
import tools.reconcile_approvals as reconcile

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "ledger_sample07"
VID = "LM6jkXooWGc"
SHA = "72af37bef06a6b279449ed3a9db8b4753ee029c7cf088ac8b25640d85638274a"
CHANNEL = "UCgMuVjQmB9WvZtSz4e23THw"
REASON = "already_uploaded:" + VID

DRY_RUN = (
    "sample-07\n"
    "  status: 'pending' -> 'readback_ok'\n"
    "  privacy: 'private' -> 'public'\n"
    "  youtube_video_id: '' -> 'LM6jkXooWGc'\n"
    "  label_api_echo: (missing) -> 'absent'\n"
    "  label_user_confirmed: (missing) -> true\n"
    "  label_confirm_source: (missing) -> 'owner_youtube_studio_check'\n"
    "  label_confirmed_at: (missing) -> '2026-11-07T23:50-05:00'\n"
)


def _install(tmp_path, *, promote=True, proof=True, post=False, echo="absent"):
    """Copy the sample-07 fixtures into an isolated data dir."""
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    if proof:
        shutil.copy(FIX / "private-proof-ledger.jsonl", tmp_path / "private-proof-ledger.jsonl")
    if promote:
        text = (FIX / "promote-ledger.jsonl").read_text()
        if echo != "absent":
            rows = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("phase") == "result":
                    if echo == "missing":
                        row.pop("contains_synthetic_media_echo", None)
                    else:
                        row["contains_synthetic_media_echo"] = echo
                rows.append(row)
            text = "".join(json.dumps(row) + "\n" for row in rows)
        (tmp_path / "promote-ledger.jsonl").write_text(text)
    if post:
        row = {
            "key": "sample-07::pub:youtube",
            "job_id": "sample-07",
            "item_id": "sample-07",
            "platform": "pub:youtube",
            "status": "private_uploaded",
            "video_id": VID,
            "channel_id": CHANNEL,
            "artifact_sha256": SHA,
        }
        (tmp_path / "post_ledger.jsonl").write_text(json.dumps(row) + "\n")
    return tmp_path


def _queue_item():
    return {
        "id": "sample-07",
        "status": "pending",
        "youtube_video_id": "",
        "privacy": "private",
        "ai_disclosure": True,
        "title": "Sample 07",
        "caption": "Sample 07",
        "platforms": ["Clipped Motions YouTube"],
    }


def test_fail_before_pending_row_would_upload_then_ledger_skips(tmp_path, monkeypatch):
    """The queue row is still pending with a blank video id, so Approve would upload."""
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    item = server._clean_item(_queue_item())
    assert item["status"] == "pending"
    assert item["youtube_video_id"] == ""
    assert item["ai_disclosure"] is True
    assert server.approve_action(item) == "private_upload"

    import multi_platform_publish as mpp
    calls = []

    def runner(it, **kwargs):
        calls.append(it["id"])
        return {"ok": True, "youtube_label": True, "video_id": "NEWVIDEO11x"}

    before = mpp.publish_after_approve(
        item, youtube_runner=runner, ledger_path=tmp_path / "idem.jsonl",
        env={"CLIP_YOUTUBE_LABEL_STEP": "true"},
    )
    assert calls == ["sample-07"]
    assert before["ok"] is True

    _install(tmp_path)
    after = mpp.publish_after_approve(
        item, youtube_runner=runner, ledger_path=tmp_path / "idem.jsonl",
        env={"CLIP_YOUTUBE_LABEL_STEP": "true"},
    )
    assert calls == ["sample-07"]
    youtube = next(p for p in after["platforms"] if p["key"] == "youtube")
    assert youtube["status"] == "skipped"
    assert youtube["error"] == REASON
    assert after["ok"] is True or youtube["status"] == "skipped"
    gate = dedupe.check_upload(item, sha256=SHA, channel_id=CHANNEL, data_dir=tmp_path)
    assert gate["action"] == "skip" and gate["reason"] == REASON and gate["video_id"] == VID


def test_sha_or_channel_mismatch_is_not_the_same_upload(tmp_path):
    _install(tmp_path)
    other_sha = dedupe.check_upload(
        {"id": "sample-07"}, sha256="0" * 64, channel_id=CHANNEL, data_dir=tmp_path,
    )
    assert other_sha["action"] == "proceed"
    other_channel = dedupe.check_upload(
        {"id": "sample-07"}, sha256=SHA, channel_id="UC8TrAT8V-HacqYlqqqzIQKg", data_dir=tmp_path,
    )
    assert other_channel["action"] == "proceed"
    post_only = tmp_path / "only-post"
    post_only.mkdir()
    _install(post_only, promote=False, proof=False, post=True)
    hit = dedupe.check_upload(
        {"id": "sample-07"}, sha256=SHA, channel_id=CHANNEL, data_dir=post_only,
    )
    assert hit["reason"] == REASON and hit["source"] == "post"


def test_approve_all_preview_counts_skip_not_success(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "unused-post.jsonl"))
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    _install(tmp_path)
    other = dict(_queue_item(), id="plain-1", ai_disclosure=False, title="Plain")
    ap = tmp_path / "approvals.json"
    ap.write_text(json.dumps({"version": 1, "items": [_queue_item(), other]}))
    loaded = server.load_approvals(ap)
    payload = server.approvals_payload(loaded)
    ready = [i for i in payload["items"] if server.approve_action(i)]
    skipped = [i for i in payload["items"] if i.get("ledger_upload_reason")]
    assert [i["id"] for i in ready] == ["plain-1"]
    assert [i["id"] for i in skipped] == ["sample-07"]
    assert skipped[0]["ledger_upload_reason"] == REASON
    assert server.approve_action(skipped[0]) == ""
    with server.approvals_lock(ap):
        batch = server.approve_batch(ap, {
            "batch_id": "batch-0007",
            "items": [
                {"id": "sample-07", "action": "private_upload"},
                {"id": "plain-1", "action": "manual"},
            ],
        })
    assert batch["skipped"] == 1
    assert batch["success"] == 0
    assert batch["approved"] == 1
    row = next(r for r in batch["results"] if r["id"] == "sample-07")
    assert row["outcome"] == "skipped" and row["ok"] is False and row["reason"] == REASON
    saved = {i["id"]: i for i in json.loads(ap.read_text())["items"]}
    assert saved["sample-07"]["status"] == "pending"
    assert saved["sample-07"]["youtube_video_id"] == ""


def test_reconcile_dry_run_then_idempotent_apply(tmp_path, capsys):
    data = _install(tmp_path)
    approvals = tmp_path / "approvals.json"
    shutil.copy(FIX / "approvals.json", approvals)
    before = approvals.read_bytes()
    rc = reconcile.main(["--approvals", str(approvals), "--data-dir", str(data)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == DRY_RUN
    assert approvals.read_bytes() == before

    rc = reconcile.main(["--approvals", str(approvals), "--data-dir", str(data), "--apply"])
    applied = capsys.readouterr().out
    assert rc == 0 and applied == DRY_RUN
    backups = list((tmp_path / "backups").glob("approvals.json.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before
    body = json.loads(approvals.read_text())
    item = body["items"][0]
    assert item["youtube_video_id"] == VID
    assert item["status"] == "readback_ok"
    assert item["privacy"] == "public"
    assert item["label_api_echo"] == "absent" and isinstance(item["label_api_echo"], str)
    assert item["label_user_confirmed"] is True
    assert item["label_confirm_source"] == "owner_youtube_studio_check"
    assert item["label_confirmed_at"] == "2026-11-07T23:50-05:00"
    assert item["ai_disclosure"] is True
    assert "youtube_label_set" not in item
    text = approvals.read_text()
    assert '"label_api_echo": false' not in text
    assert '"youtube_label_set": false' not in text
    assert '"ai_disclosure": false' not in text
    assert item["label_api_echo"] != item["label_user_confirmed"]

    stamped = approvals.read_bytes()
    rc = reconcile.main(["--approvals", str(approvals), "--data-dir", str(data), "--apply"])
    again = capsys.readouterr().out
    assert rc == 0 and again == "no changes\n"
    assert approvals.read_bytes() == stamped
    assert len(list((tmp_path / "backups").glob("approvals.json.*"))) == 1

    cleaned = server._clean_item(json.loads(approvals.read_text())["items"][0])
    assert cleaned["status"] == "readback_ok"
    assert cleaned["label_api_echo"] == "absent"
    assert cleaned["label_user_confirmed"] is True
    assert cleaned["ai_disclosure"] is True
    assert cleaned["label_api_echo"] != cleaned["youtube_label_set"]


def test_missing_echo_is_not_stored_as_label_off(tmp_path, capsys):
    data = _install(tmp_path, echo="missing")
    approvals = tmp_path / "approvals.json"
    shutil.copy(FIX / "approvals.json", approvals)
    rc = reconcile.main(["--approvals", str(approvals), "--data-dir", str(data), "--apply"])
    assert rc == 0
    capsys.readouterr()
    item = json.loads(approvals.read_text())["items"][0]
    assert "label_api_echo" not in item
    assert item["label_user_confirmed"] is True
    assert item["ai_disclosure"] is True
    assert "youtube_label_set" not in item
    text = approvals.read_text()
    assert '"label_api_echo": false' not in text
    assert '"contains_synthetic_media": false' not in text
    false_echo = _install(tmp_path / "false-echo", echo=False)
    false_approvals = tmp_path / "false-echo" / "approvals.json"
    shutil.copy(FIX / "approvals.json", false_approvals)
    rc = reconcile.main(["--approvals", str(false_approvals), "--data-dir", str(false_echo), "--apply"])
    assert rc == 0
    capsys.readouterr()
    raw = false_approvals.read_text()
    assert '"label_api_echo": false' not in raw
    assert '"youtube_label_set": false' not in raw
    kept = json.loads(raw)["items"][0]
    assert kept["label_user_confirmed"] is True
    assert kept["ai_disclosure"] is True


def test_corrupt_ledger_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    (tmp_path / "private-proof-ledger.jsonl").write_text(
        '{"key":"private-proof:MAIN:%s:%s","status":"uploaded","video_id":"%s","item_id":"sample-07"}\n{"key":\n'
        % (CHANNEL, SHA, VID)
    )
    gate = dedupe.check_upload({"id": "sample-07"}, sha256=SHA, channel_id=CHANNEL, data_dir=tmp_path)
    assert gate["action"] == "fail" and gate["reason"] == "ledger_corrupt"
    import publish_adapters as adapters
    refused = adapters.youtube_upload(
        {"id": "sample-07"}, {"artifact_sha256": SHA, "bound_channel_id": CHANNEL, "disclosures": {}},
        token="tok", http=lambda *a, **k: (_ for _ in ()).throw(AssertionError("http")),
        file_bytes=b"nope", expected_channel_id=CHANNEL,
    )
    assert refused["called"] is False and refused["reason"] == "ledger_corrupt"
    approvals = tmp_path / "approvals.json"
    shutil.copy(FIX / "approvals.json", approvals)
    before = approvals.read_bytes()
    rc = reconcile.main(["--approvals", str(approvals), "--data-dir", str(tmp_path), "--apply"])
    err = capsys.readouterr().err
    assert rc == 2 and "ledger_corrupt" in err
    assert approvals.read_bytes() == before
    assert not (tmp_path / "backups").exists()
