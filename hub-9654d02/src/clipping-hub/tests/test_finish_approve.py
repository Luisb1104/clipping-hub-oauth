"""Finish-Approve gaps: runtime identity, blocked bulk, legacy targets, campaign policy."""
from __future__ import annotations

import json
from pathlib import Path

import public_publish as P
import publish_readiness as R
import publish_runtime as RT
import schedule_hook as S
import server

ROOT = Path(__file__).resolve().parents[1]
LEGACY = json.loads((ROOT / "tests" / "fixtures" / "post_targets_legacy.json").read_text())
QUEUE = json.loads((ROOT / "tests" / "fixtures" / "queue_legacy_shape.json").read_text())["items"]
CHANNELS = {"channels": [
    {"platform": "YOUTUBE", "post_account_id": "6aedeb42386c37c006241619",
     "profile_url": "https://www.youtube.com/channel/UCgMuVjQmB9WvZtSz4e23THw"},
    {"platform": "YOUTUBE", "post_account_id": "6aedf5ffb09f11b7595325ed",
     "profile_url": "https://www.youtube.com/channel/UC8TrAT8V-HacqYlqqqzIQKg"},
    {"platform": "YOUTUBE", "post_account_id": "6aee516c386c37c006246b12",
     "profile_url": "https://www.youtube.com/channel/UC7fAgyeOwAKZYFAbcyc2Zig"},
]}


def _rows(manifest):
    return [{"key": r["key"], "row_hash": r["row_hash"]} for r in manifest["platforms"]]


def test_legacy_targets_keep_grant_diagnostic_without_inventing_accounts(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "youtube_grant_status", lambda channel: {"present": True, "bound": True})
    item = next(i for i in QUEUE if i["id"] == "sample07")
    manifest = P.build_manifest(item, targets=LEGACY, channels=CHANNELS)
    yt = next(r for r in manifest["platforms"] if r["key"] == "youtube")
    assert yt["reason"] == "accounts_map_absent"
    assert yt["will_dispatch"] is False
    assert yt["account_id"] == ""
    assert "UCgMuVjQmB9WvZtSz4e23THw" in yt["line"]
    assert "not copied" in yt["line"].lower() or "was not copied" in yt["line"]
    assert "on file" in yt["line"]
    assert manifest["ui_kind"] != "public"
    assert manifest["record_kind"] != "manual"
    assert "accounts" not in LEGACY


def test_blocked_rows_are_not_manual_and_bulk_keeps_them_pending(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": lambda *a, **k: calls.append(1)})
    campaigns = [i for i in QUEUE if str(i["id"]).startswith("camp-")]
    assert len(campaigns) == 12
    data = {"version": 1, "items": [server._clean_item(dict(i)) for i in campaigns]}
    for item in data["items"]:
        preview = item["public_preview"]
        assert item.get("rights_ok") is not True
        assert preview["record_kind"] == "blocked"
        assert preview["ui_kind"] != "public"
        assert preview["will_dispatch_any"] is False
        assert server.approve_action(item) == ""
        assert any(r["reason"] == "rights_unconfirmed" or "rights_unconfirmed" in (r.get("restrictions") or []) for r in preview["platforms"])
    try:
        server.decide_approval(data, {
            "op": "decide", "id": "camp-01", "status": "approved",
            "confirm_public": True, "manifest_hash": data["items"][0]["public_preview"]["manifest_hash"],
            "platform_rows": _rows(data["items"][0]["public_preview"]),
        })
        assert False, "blocked campaign must stay pending"
    except server.BadRequest as exc:
        assert "nothing_to_publish" in str(exc)
    assert data["items"][0]["status"] == "pending"
    assert calls == []


def test_legitimate_manual_is_not_called_public(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": lambda *a, **k: calls.append(1)})
    item = server._clean_item({
        "id": "manual-ok", "video": "/samples/sample-a.mp4", "caption": "ready by hand",
        "title": "Manual", "platforms": ["Clipped Motions YouTube"],
        "ai_disclosure": False, "rights_ok": True, "status": "pending",
    })
    preview = item["public_preview"]
    assert preview["record_kind"] == "manual"
    assert preview["ui_kind"] == "manual"
    assert preview["ui_kind"] != "public"
    assert server.approve_action(item) == "manual"
    data = {"items": [item]}
    data, saved, changed = server.decide_approval(data, {
        "op": "decide", "id": "manual-ok", "status": "approved", "confirm_public": True,
        "manifest_hash": preview["manifest_hash"], "platform_rows": _rows(preview),
    })
    assert changed and saved["status"] == "approved"
    out = P.dispatch_item(saved, preview["manifest_hash"], platform_rows=_rows(preview))
    assert out["kind"] == "manual"
    assert out["dispatched"] is False
    assert calls == []


def test_publish_config_arms_identity_but_not_public_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    secret = "tok_test_secret_value"
    cfg = {
        "instagram": {
            "available": True,
            "ig_user_id": "17841400000000001",
            "access_token": secret,
            "sponsor_eligible": True,
            "scopes": ["instagram_content_publish", "instagram_basic"],
        },
        "facebook": {
            "available": True,
            "page_id": "100000000000001",
            "access_token": secret,
            "scopes": ["pages_show_list", "pages_read_engagement", "pages_manage_posts"],
            "tasks": ["CREATE_CONTENT"],
        },
        "tiktok": {"available": True, "api_key": secret, "integration_id": "int_postiz_1"},
    }
    path = tmp_path / "publish-config.json"
    path.write_text(json.dumps(cfg))
    path.chmod(0o600)
    monkeypatch.setenv("CLIPPING_HUB_PUBLISH_CONFIG", str(path))
    creds = P.credentials()
    assert creds["instagram"]["ig_user_id"] == "17841400000000001"
    assert creds["facebook"]["page_id"] == "100000000000001"
    assert creds["tiktok"]["integration_id"] == "int_postiz_1"
    blob = json.dumps(RT.config_problems())
    assert secret not in blob
    calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {})
    import publish_adapters as A
    monkeypatch.setattr(A, "HTTP", lambda *a, **k: calls.append(1))
    item = server._clean_item({
        "id": "ig1", "video": "/samples/sample-a.mp4", "caption": "c", "title": "t",
        "platforms": ["IG Business", "FB Page", "TikTok Business"],
        "ai_disclosure": True, "rights_ok": True, "status": "pending",
    })
    reasons = {r["key"]: r["reason"] for r in item["public_preview"]["platforms"]}
    assert reasons["instagram"] == "disclosure_readback_unverified"
    assert reasons["facebook"] == "disclosure_readback_unverified"
    assert reasons["tiktok"] == "disclosure_readback_unverified"
    assert item["public_preview"]["will_dispatch_any"] is False
    assert item["public_preview"]["ui_kind"] != "public"
    assert calls == []
    bad = dict(cfg)
    bad["instagram"] = dict(cfg["instagram"], scopes=["instagram_basic"])
    path.write_text(json.dumps(bad))
    path.chmod(0o600)
    creds = P.credentials()
    assert "instagram" not in creds
    assert any(p["problem"] == "scopes_missing" for p in RT.config_problems())


def test_change_requested_alliance_surfaces_missing_policy_and_preserves_hold(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    alliance = next(i for i in QUEUE if i["id"] == "alliance-edit")
    assert alliance["status"] == "change_requested"
    absent = R.campaign_policy_view(alliance, LEGACY)
    assert absent["state"] == "absent"
    held_cfg = S.load_targets()
    held = R.campaign_policy_view(alliance, held_cfg)
    assert held["state"] == "held"
    cleaned = server._clean_item(dict(alliance))
    assert cleaned["status"] == "change_requested"
    assert cleaned["held"] is True
    assert server.approve_action(cleaned) == ""
    report = R.report(QUEUE, targets=LEGACY, channels=CHANNELS, public_enabled=True)
    assert report["publishes"] is False
    assert report["counts"]["would_dispatch"] == 0
    assert report["counts"]["manual_ready"] == 0
    assert "alliance-edit" in report["change_requested"]
    assert "alliance-edit" in report["campaign_config_absent"]
    assert report["counts"]["items"] == 14
    assert all(not step.lower().startswith("posted") for step in report["next_steps"])
    text = json.dumps(report["platforms"])
    assert "automatic_public" in text
    assert '"automatic_public": true' not in text


def test_private_proof_plan_does_not_use_the_public_ledger(tmp_path, monkeypatch):
    import tools.private_proof as proof
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    public = tmp_path / "post_ledger.jsonl"
    public.write_text("")
    assert proof.ledger_is_public(public) is True
    other = tmp_path / "operator-chosen-ledger.jsonl"
    body = proof.plan_private_proof(item_id="sample07", channel="MAIN", ledger=str(other))
    assert body["executes_network"] is False
    assert body["public_success"] is False
    assert body["marks_public_posted"] is False
    assert body["ledger_key_prefix"] == "private-proof:"
    assert proof.main(["--execute"]) == 2
    assert proof.main(["--item", "sample07", "--channel", "MAIN", "--ledger", str(public)]) == 2
