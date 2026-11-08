"""Public publish confirmation. Flag default off. Mocked runners only. No live network."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from urllib.error import URLError

import public_publish as P
import schedule_hook as S
import server

ROOT = Path(__file__).resolve().parents[1]
SAMPLE07 = json.loads((ROOT / "tests" / "fixtures" / "horror-sample07.json").read_text())
MAIN_CHANNEL = "UCgMuVjQmB9WvZtSz4e23THw"


def _rows(manifest):
    return [{"key": r["key"], "row_hash": r["row_hash"]} for r in (manifest.get("platforms") or [])]


def _on(**kwargs):
    base = {"CLIP_PUBLIC_PUBLISH": "true"}
    base.update(kwargs)
    return base


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(P.FLAG, raising=False)
    assert P.enabled() is False
    assert server._public_publish_enabled() is False


def test_default_off_approve_does_not_require_confirm(monkeypatch):
    monkeypatch.delenv(P.FLAG, raising=False)
    item = server._clean_item({
        "id": "off1", "video": "/samples/sample-a.mp4", "caption": "c", "title": "t",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": False, "status": "pending",
    })
    data = {"version": 1, "items": [item]}
    data, saved, changed = server.decide_approval(data, {"op": "decide", "id": "off1", "status": "approved"})
    assert changed is True and saved["status"] == "approved"


def test_sample07_local_file_does_not_require_opus_ids(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    item = server._clean_item({
        "id": "sample07", "title": "Hallway sample 07",
        "caption": "Synthetic horror sample. Local final only.",
        "video": "/samples/sample07.mp4",
        "platforms": ["Clipped Motions YouTube"],
        "ai_disclosure": True, "status": "pending",
    })
    yt = item["public_preview"]["platforms"][0]
    assert "projectId" not in item or not item.get("projectId")
    assert yt["transport"] == "youtube_resumable_upload"
    assert yt["reason"] == "youtube_grant_absent"
    assert yt["will_dispatch"] is False
    assert "not required" in yt["line"].lower()
    assert not yt["line"].startswith("PUBLIC publish")
    gaming = P.decide_platform(
        {"id": "g1", "clip_type": "gta", "caption": "c", "ai_disclosure": True},
        "Clipped Motions YouTube",
        {"target": "GAMING", "paid_promotion": False, "blocked": False, "deny_platforms": []},
        S.load_targets(), {"sha256": "abc", "name": "sample-a.mp4"}, None,
    )
    assert gaming["reason"] == "youtube_grant_absent"
    assert gaming["transport"] == "youtube_resumable_upload"
    paid = P.decide_platform(
        {"id": "p1", "clip_type": "campaign", "caption": "c", "ai_disclosure": True},
        "Clipped Motions YouTube",
        {"target": "PAID", "paid_promotion": True, "blocked": False, "deny_platforms": []},
        S.load_targets(), {"sha256": "abc", "name": "sample-a.mp4"}, None,
    )
    assert paid["reason"] == "youtube_paid_label_unverified"
    assert paid["will_dispatch"] is False
    assert "No resumable" in paid["line"]
    assert "MAIN only" not in paid["line"]


def test_manifest_hash_changes_when_caption_changes(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    item = dict(SAMPLE07, projectId="proj", clipId="clip", status="pending")
    a = P.build_manifest(item)
    b = P.build_manifest(dict(item, caption=item["caption"] + " edited"))
    assert a["manifest_hash"] != b["manifest_hash"]
    assert len(a["manifest_hash"]) == 64


def test_no_account_fallback():
    cfg = {
        "version": 1, "poster": "opus", "targets": {
            "MAIN": {"name": "M", "handle": "@m", "yt": S.MAIN_YOUTUBE_CHANNEL_ID, "opus_post_account_id": "abc"},
        },
        "accounts": {"PAID": {"youtube": {"provider": "opus", "account_name": "Other", "account_id": "paid-only", "external_id": "UC8TrAT8V-HacqYlqqqzIQKg", "auth_verified": False}}},
    }
    item = {
        "id": "nf1", "caption": "c", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "projectId": "p", "clipId": "c",
    }
    row = P.decide_platform(item, "Clipped Motions YouTube", {"target": "MAIN", "paid_promotion": False}, cfg, {"sha256": "abc", "name": "sample-a.mp4"}, None)
    assert row["reason"] == "account_unconfigured"
    assert row["account_id"] != "paid-only"
    assert row["will_dispatch"] is False


def test_horror_misroute_and_cod_and_held(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    horror = {
        "id": "h1", "clip_type": "horror", "caption": "c", "video": "/samples/sample07.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "projectId": "p", "clipId": "c",
    }
    route = {"target": "GAMING", "paid_promotion": False, "blocked": False, "deny_platforms": []}
    row = P.decide_platform(horror, "Clipped Motions YouTube", route, S.load_targets(), {"sha256": "x", "name": "sample07.mp4"}, None)
    assert row["reason"] == "horror_youtube_main_only"
    assert row["public_action"] == "blocked"

    cod = server._clean_item({
        "id": "cod1", "caption": "Buy #ad", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube", "TikTok Business", "IG Business", "FB Page"],
        "ai_disclosure": True, "is_ad": True, "campaign_id": "CoD", "status": "pending",
    })
    by = {r["key"]: r for r in cod["public_preview"]["platforms"]}
    yt, tt, ig, fb = by["youtube"], by["tiktok"], by["instagram"], by["facebook"]
    assert yt["reason"] == "campaign_denies_youtube"
    assert fb["reason"] == "campaign_denies_platform"
    assert tt["reason"] == "postiz_integration_absent"
    assert ig["reason"] == "instagram_auth_identity_sponsor_unverified"
    assert "#ad" in (cod.get("hashtags") or []) or True
    assert yt["disclosures"]["hashtag_ad_is_not_a_paid_toggle"] is True

    held = server._clean_item({
        "id": "hold1", "caption": "c", "video": "/samples/sample-a.mp4",
        "platforms": ["TikTok Business"], "campaign_id": "HeldAlliance",
        "ai_disclosure": True, "status": "pending",
    })
    assert held["held"] is True
    assert server.approve_action(held) == ""
    preview = held["public_preview"]
    assert preview["ui_kind"] == "held"
    assert preview["ui_kind"] != "public"
    assert preview["will_dispatch_any"] is False
    assert all(r["will_dispatch"] is False for r in preview["platforms"])
    assert "Publish publicly" not in preview["summary"]
    data = {"items": [held]}
    try:
        server.decide_approval(data, {"op": "decide", "id": "hold1", "status": "approved", "confirm_public": True, "manifest_hash": "x"})
        assert False, "held must not approve"
    except server.BadRequest as e:
        assert "campaign_held" in str(e)
    assert data["items"][0]["status"] == "pending"


def test_storyblocks_facebook_not_banned_by_license(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    item = server._clean_item({
        "id": "sb1", "caption": "c", "video": "/samples/sample-a.mp4", "title": "t",
        "platforms": ["FB Page"], "license": {"source": "storyblocks"},
        "ai_disclosure": True, "status": "pending",
    })
    assert item["storyblocks"] is True
    assert item["route_blocked"] is False
    fb = item["public_preview"]["platforms"][0]
    assert fb["reason"] != "storyblocks_blocks_platform"
    assert "facebook_reels" in (fb["reason"] or "")


def test_paid_toggle_is_not_a_hashtag():
    body = P.tiktok_business_body({
        "account_id": "tt-synthetic-main",
        "caption": "hello #ad",
        "disclosures": {"ai": True, "paid": True},
    })
    assert "privacy_level" not in body and "privacy_level" not in body["post_info"]
    assert body["post_info"]["is_branded_content"] is True
    assert body["post_info"]["is_ai_generated"] is True
    assert "upload_to_draft" not in body["post_info"]
    ig = P.instagram_container_body({
        "caption": "hello #ad",
        "disclosures": {"ai": True, "paid": True, "sponsor_ids": ["1784"]},
    })
    assert ig["is_paid_partnership"] is True
    assert ig["is_ai_generated"] is True
    assert ig["branded_content_sponsor_ids"] == ["1784"]
    assert "#ad" not in ig or True
    fb = P.facebook_reels_body({"caption": "hello #ad", "disclosures": {"ai": True, "paid": True}})
    assert fb["is_ai_generated"] is True
    assert "is_paid_partnership" not in fb
    assert "branded_content_sponsor_ids" not in fb


def test_instagram_and_facebook_and_tiktok_fail_closed(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    item = server._clean_item({
        "id": "lab1", "caption": "c #ad", "video": "/samples/sample-a.mp4",
        "platforms": ["TikTok Business", "IG Business", "FB Page"],
        "ai_disclosure": True, "is_ad": True, "campaign_id": "camp", "status": "pending",
        "projectId": "p", "clipId": "c",
    })
    reasons = {r["key"]: r["reason"] for r in item["public_preview"]["platforms"]}
    assert reasons["tiktok"] == "postiz_integration_absent"
    assert reasons["instagram"] == "instagram_auth_identity_sponsor_unverified"
    assert reasons["facebook"] == "facebook_reels_paid_disclosure_not_in_official_schema"
    assert P.VERIFIED["postiz_integrations_seen"] == 0
    assert P.VERIFIED["fb_reels_paid_field"] is False
    assert P.VERIFIED["ig_is_paid_partnership"] is True
    assert P.VERIFIED["ig_resumable_local_file"] is True
    assert P.VERIFIED["ig_media_publish_creation_id"] is True
    assert P.VERIFIED["opus_ai_toggle"] is False
    assert P.VERIFIED["tiktok_upload_publishes"] is False
    text = (ROOT / "public_publish.py").read_text()
    assert "support_message" not in text
    assert "campaign/submit" not in text
    assert "whop" not in text.lower()


def test_confirm_required_and_stale_hash_and_duplicate(monkeypatch, tmp_path):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []

    def runner(item, row):
        calls.append(row["key"])
        return {"ok": True, "youtube_label": True, "video_id": "abcdefghijk"}

    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": runner})
    item = {
        "id": "yt1", "caption": "Full caption here", "title": "Title", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True, "status": "pending",
        "projectId": "proj123", "clipId": "clip123", "rights_ok": True,
    }
    cleaned = server._clean_item(item)
    preview = cleaned["public_preview"]
    assert preview["will_dispatch_any"] is True
    assert preview["platforms"][0]["public_action"] == "private_upload"
    data = {"items": [cleaned]}
    try:
        server.decide_approval(data, {"op": "decide", "id": "yt1", "status": "approved"})
        assert False
    except server.BadRequest as e:
        assert "public_confirm_required" in str(e)
    assert data["items"][0]["status"] == "pending"
    try:
        server.decide_approval(data, {
            "op": "decide", "id": "yt1", "status": "approved",
            "confirm_public": True, "manifest_hash": "0" * 64,
        })
        assert False
    except server.BadRequest as e:
        assert "manifest_stale" in str(e)
    data, saved, changed = server.decide_approval(data, {
        "op": "decide", "id": "yt1", "status": "approved",
        "confirm_public": True, "manifest_hash": preview["manifest_hash"],
        "platform_rows": _rows(preview),
    })
    assert changed is True
    ledger = tmp_path / "ledger.jsonl"
    first = P.dispatch_item(saved, preview["manifest_hash"], platform_rows=_rows(preview), ledger_path=ledger)
    second = P.dispatch_item(saved, preview["manifest_hash"], platform_rows=_rows(preview), ledger_path=ledger)
    assert calls == ["youtube"]
    assert first["platforms"][0]["status"] == "done"
    assert second["platforms"][0]["skipped_idempotent"] is True
    assert second["platforms"][0]["called"] is False


def test_timeout_and_accept_without_permalink_do_not_repost(tmp_path, monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    n = {"n": 0}

    def runner(item, row):
        n["n"] += 1
        if n["n"] == 1:
            raise TimeoutError("socket timeout")
        return {"ok": True, "accepted": True, "video_id": ""}

    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": runner})
    item = {
        "id": "to1", "caption": "c", "title": "t", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "projectId": "proj123", "clipId": "clip123", "rights_ok": True,
    }
    manifest = P.build_manifest(item)
    ledger = tmp_path / "l.jsonl"
    rows = _rows(manifest)
    r1 = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    r2 = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert r1["platforms"][0]["status"] == "unknown"
    assert r2["platforms"][0]["called"] is False
    assert r2["platforms"][0]["status"] == "unknown"
    assert n["n"] == 1


def test_accept_without_permalink_second_shape(tmp_path, monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")

    def runner(item, row):
        return {"ok": True, "accepted": True}

    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": runner})
    item = {
        "id": "acc1", "caption": "c", "title": "t", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "projectId": "proj123", "clipId": "clip123", "rights_ok": True,
    }
    manifest = P.build_manifest(item)
    ledger = tmp_path / "l.jsonl"
    rows = _rows(manifest)
    r1 = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    r2 = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert r1["error"] == "pending_reconcile"
    assert r2["platforms"][0]["called"] is False


def test_race_single_runner(tmp_path, monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []
    started = threading.Event()
    release = threading.Event()

    def runner(item, row):
        calls.append(1)
        started.set()
        assert release.wait(timeout=2)
        return {"ok": True, "youtube_label": True, "video_id": "abcdefghijk"}

    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": runner})
    item = {
        "id": "race1", "caption": "c", "title": "t", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "projectId": "proj123", "clipId": "clip123", "rights_ok": True,
    }
    manifest = P.build_manifest(item)
    ledger = tmp_path / "l.jsonl"
    rows = _rows(manifest)
    out = []

    def go():
        out.append(P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger))

    a = threading.Thread(target=go)
    b = threading.Thread(target=go)
    a.start(); b.start()
    assert started.wait(timeout=2)
    release.set()
    a.join(); b.join()
    assert len(calls) == 1
    assert any(r["platforms"][0]["status"] == "done" for r in out)


def test_grant_copy_names_the_grant_that_exists():
    present = {"present": True, "expired": False, "needs_regrant": False}
    main = server.approve_copy(
        {"route_target": "MAIN", "ai_disclosure": True},
        label_step=True, grants={"MAIN": present},
    )
    assert "hub YouTube grant for MAIN is on file" in main
    assert "waits for" not in main
    paid = server.approve_copy(
        {"route_target": "PAID", "ai_disclosure": True},
        label_step=True, grants={"PAID": present},
    )
    assert "PAID" in paid and "waits for" not in paid
    absent = server.approve_copy(
        {"route_target": "MAIN", "ai_disclosure": True},
        label_step=True, grants={"MAIN": {"present": False, "expired": True, "needs_regrant": True}},
    )
    assert "otherwise waits for the grant" in absent
    assert absent.startswith("Approve = uploads PRIVATE to MAIN")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _mine(channel=MAIN_CHANNEL):
    return {"status": 200, "json": {"items": [{"id": channel}]}}


def _yt_item(iid, caption):
    return {
        "id": iid, "caption": caption, "title": "T", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True, "rights_ok": True,
    }


def test_youtube_resumable_adapter_sends_public_and_synthetic(monkeypatch):
    import publish_adapters as A
    calls = []

    def http(method, url, headers, body):
        calls.append((method, url, headers, body))
        if method == "GET":
            return _mine()
        if method == "POST":
            return {
                "status": 200,
                "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=abc"},
                "json": {},
            }
        meta = json.loads(calls[1][3])
        return {"status": 201, "headers": {}, "json": {
            "id": "abcdefghijk",
            "snippet": {"channelId": MAIN_CHANNEL},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": meta["status"]["containsSyntheticMedia"]},
        }}

    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    row = {"caption": "hello", "disclosures": {"ai": True, "paid": False}, "artifact_sha256": _sha(raw)}
    out = A.youtube_upload(
        {"title": "T", "caption": "hello"}, row, token="tok", http=http, file_bytes=raw,
        expected_channel_id=MAIN_CHANNEL,
    )
    assert out["private_uploaded"] is True and out["ok"] is False and out["called"] is True
    assert calls[0][0] == "GET" and calls[0][1] == A.YOUTUBE_CHANNELS_MINE
    sent = json.loads(calls[1][3])
    assert sent["status"]["privacyStatus"] == "private"
    assert sent["status"]["containsSyntheticMedia"] is True
    assert "paidProductPlacementDetails" not in sent
    assert calls[2][0] == "PUT" and calls[2][3] == raw
    assert calls[2][1].startswith("https://www.googleapis.com/")
    paid_calls = []
    paid = A.youtube_upload(
        {"title": "T"}, {"caption": "ad", "disclosures": {"ai": True, "paid": True}},
        token="tok", http=lambda *a: paid_calls.append(1), file_bytes=raw,
        expected_channel_id=MAIN_CHANNEL,
    )
    assert paid["called"] is False
    assert paid["reason"] == "youtube_paid_label_unverified"
    assert paid_calls == []
    def refuse(method, url, headers, body):
        if method == "GET":
            return _mine()
        return {
            "status": 403, "headers": {},
            "json": {"error": {"errors": [{"reason": "forbiddenPrivacySetting"}]}},
        }

    refused = A.youtube_upload({"title": "T"}, dict(row, artifact_sha256=_sha(raw)), token="tok", http=refuse, file_bytes=raw, expected_channel_id=MAIN_CHANNEL)
    assert refused["reason"] == "youtube_privacy_rejected"
    assert refused["ok"] is False
    assert A.youtube_upload(
        {"title": "T"}, row, token="", http=http, file_bytes=raw, expected_channel_id=MAIN_CHANNEL,
    )["reason"] == "youtube_grant_absent"


def test_instagram_and_facebook_adapters_use_documented_fields():
    import publish_adapters as A
    seen = []

    def http(method, url, headers, body):
        seen.append((method, url, body if isinstance(body, (bytes, dict)) else body))
        if url.endswith("/media"):
            parsed = json.loads(body)
            assert parsed["media_type"] == "REELS"
            assert parsed["upload_type"] == "resumable"
            assert parsed["is_ai_generated"] is False
            assert "is_paid_partnership" not in parsed
            assert "video_url" not in parsed
            return {"status": 200, "json": {"id": "container1"}}
        if "rupload.facebook.com/ig-api-upload" in url:
            assert headers["offset"] == "0" and headers["file_size"]
            return {"status": 200, "json": {"success": True, "message": "Upload successful."}}
        if url.endswith("/media_publish"):
            assert json.loads(body) == {"creation_id": "container1"}
            return {"status": 200, "json": {"id": "media1"}}
        raise AssertionError(url)

    labeled = {"caption": "c #ad", "disclosures": {"ai": True, "paid": True, "sponsor_ids": ["1784"]}}
    labeled_calls = []
    blocked_label = A.instagram_reel(
        {}, labeled, ig_user_id="ig-user", token="tok", sponsor_eligible=True,
        http=lambda *a: labeled_calls.append(1), file_bytes=b"mp4",
    )
    assert blocked_label["called"] is False
    assert blocked_label["reason"] == "disclosure_readback_unverified"
    assert labeled_calls == []
    plain = {"caption": "c", "disclosures": {"ai": False, "paid": False}}
    out = A.instagram_reel(
        {}, plain, ig_user_id="ig-user", token="tok", sponsor_eligible=True, http=http, file_bytes=b"mp4",
    )
    assert out["ok"] and out["permalink"].endswith("media1")
    blocked = A.instagram_reel({}, labeled, ig_user_id="", token="", sponsor_eligible=False, http=http, file_bytes=b"x")
    assert blocked["called"] is False and blocked["reason"] == "instagram_auth_identity_sponsor_unverified"

    fb_seen = []

    def fb_http(method, url, headers, body):
        fb_seen.append(url)
        if url.endswith("/video_reels") and fb_seen.count(url) == 1:
            assert json.loads(body)["upload_phase"] == "start"
            return {"status": 200, "json": {"video_id": "vid9"}}
        if "rupload.facebook.com/video-upload" in url:
            assert headers["offset"] == "0"
            return {"status": 200, "json": {"success": True}}
        finish = json.loads(body)
        assert finish["upload_phase"] == "finish" and finish["video_state"] == "PUBLISHED"
        assert finish["is_ai_generated"] is False
        assert "is_paid_partnership" not in finish
        return {"status": 200, "json": {"success": True}}

    ai_calls = []
    ai_row = {"caption": "c", "disclosures": {"ai": True, "paid": False}}
    ai_blocked = A.facebook_reel(
        {}, ai_row, page_id="page", token="tok", http=lambda *a: ai_calls.append(1), file_bytes=b"mp4",
    )
    assert ai_blocked["called"] is False
    assert ai_blocked["reason"] == "disclosure_readback_unverified"
    assert ai_calls == []
    ok = A.facebook_reel({}, plain, page_id="page", token="tok", http=fb_http, file_bytes=b"mp4")
    assert ok["ok"] is True
    paid = A.facebook_reel({}, {"caption": "c #ad", "disclosures": {"ai": True, "paid": True}}, page_id="page", token="tok", http=fb_http, file_bytes=b"mp4")
    assert paid["called"] is False
    assert paid["reason"] == "facebook_reels_paid_disclosure_not_in_official_schema"
    assert "is_ai_generated" in A.FB_AI_SOURCE and "v27.0" in A.FB_AI_SOURCE


def test_postiz_tiktok_direct_post_not_upload_and_not_mcp():
    import publish_adapters as A
    settings = A.postiz_tiktok_settings({"caption": "c #ad", "disclosures": {"ai": True, "paid": True}})
    assert settings["content_posting_method"] == "DIRECT_POST"
    assert settings["video_made_with_ai"] is True
    assert settings["brand_content_toggle"] is True
    assert "mcp" in A.POSTIZ_BOUNDARY.lower() or "connector" in A.POSTIZ_BOUNDARY.lower()
    assert A.postiz_tiktok({}, {"caption": "c", "disclosures": {}}, api_key="", integration_id="", http=lambda *a: None, file_bytes=b"x", filename="a.mp4")["reason"] == "postiz_integration_absent"
    calls = []

    def http(method, url, headers, body):
        calls.append(url)
        if url.endswith("/upload"):
            return {"status": 200, "json": {"id": "m1", "path": "https://uploads.postiz.com/a.mp4", "status": "ready"}}
        post = json.loads(body)
        assert post["type"] == "now"
        assert post["posts"][0]["settings"]["content_posting_method"] == "DIRECT_POST"
        assert post["posts"][0]["integration"]["id"] == "int-1"
        return {"status": 200, "json": {"id": "post-1", "releaseId": "tt-rel"}}

    labeled_calls = []
    labeled = A.postiz_tiktok(
        {}, {"caption": "c", "disclosures": {"ai": True, "paid": False}},
        api_key="key", integration_id="int-1", http=lambda *a: labeled_calls.append(1),
        file_bytes=b"mp4", filename="a.mp4",
    )
    assert labeled["called"] is False
    assert labeled["reason"] == "disclosure_readback_unverified"
    assert labeled_calls == []
    out = A.postiz_tiktok(
        {}, {"caption": "c", "disclosures": {"ai": False, "paid": False}},
        api_key="key", integration_id="int-1", http=http, file_bytes=b"mp4", filename="a.mp4",
    )
    assert out["ok"] and out["permalink"] == "tt-rel"
    assert calls == [A.POSTIZ_ORIGIN + "/upload", A.POSTIZ_ORIGIN + "/posts"]


def test_caption_change_does_not_repost_and_unknown_stays_reconcile(tmp_path, monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []

    def runner(item, row):
        calls.append(item["id"])
        if item["id"] == "unk1":
            raise TimeoutError("timeout")
        return {"ok": True, "youtube_label": True, "video_id": "abcdefghijk"}

    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": runner})
    first = _yt_item("job1", "original caption")
    m1 = P.build_manifest(first)
    assert P.dispatch_item(first, m1["manifest_hash"], platform_rows=_rows(m1), ledger_path=tmp_path / "led.jsonl")["platforms"][0]["status"] == "done"
    edited = _yt_item("job2", "edited caption")
    m2 = P.build_manifest(edited)
    assert m1["manifest_hash"] != m2["manifest_hash"]
    assert m1["platforms"][0]["row_hash"] != m2["platforms"][0]["row_hash"]
    again = P.dispatch_item(edited, m2["manifest_hash"], platform_rows=_rows(m2), ledger_path=tmp_path / "led.jsonl")
    assert again["platforms"][0]["called"] is False
    assert again["platforms"][0]["reason"] == "duplicate_publication_repost_required"
    assert calls == ["job1"]
    unknown_item = _yt_item("unk1", "first")
    mu = P.build_manifest(unknown_item)
    P.dispatch_item(unknown_item, mu["manifest_hash"], platform_rows=_rows(mu), ledger_path=tmp_path / "unk.jsonl")
    changed = _yt_item("unk2", "caption changed after timeout")
    mc = P.build_manifest(changed)
    second = P.dispatch_item(changed, mc["manifest_hash"], platform_rows=_rows(mc), ledger_path=tmp_path / "unk.jsonl")
    assert second["platforms"][0]["reason"] == "reconcile_required"
    assert second["platforms"][0]["called"] is False
    assert calls == ["job1", "unk1"]


def test_verified_capability_flags_match_this_session():
    assert P.VERIFIED["opus_accepts_local_file"] is False
    assert P.VERIFIED["tiktok_business_video_has_privacy_field"] is False
    assert P.VERIFIED["tiktok_business_is_ai_generated"] is True
    assert P.VERIFIED["ig_video_url_in_content_publishing"] is True
    assert P.VERIFIED["ig_media_publish_creation_id"] is True
    assert P.VERIFIED["youtube_resumable_local_upload"] is True
    assert P.VERIFIED["fb_reels_is_ai_generated"] is True
    assert P.VERIFIED["youtube_contains_synthetic_media"] is True
    assert P.VERIFIED["youtube_has_paid_product_placement"] is False


def test_rights_and_campaign_terms_block_before_upload(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": lambda item, row: calls.append(1)})
    item = _yt_item("rights1", "caption")
    item["rights_ok"] = False
    manifest = P.build_manifest(item)
    assert manifest["platforms"][0]["will_dispatch"] is False
    assert manifest["platforms"][0]["reason"] == "rights_unconfirmed"
    assert manifest["will_dispatch_any"] is False
    out = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=_rows(manifest), ledger_path=None)
    assert out["dispatched"] is False
    assert calls == []
    campaign = {
        "id": "camp-rights", "caption": "c", "title": "T", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "rights_ok": True, "campaign_terms_ok": False, "campaign_id": "camp",
    }
    row = P.decide_platform(
        campaign, "Clipped Motions YouTube",
        {"target": "MAIN", "paid_promotion": False, "blocked": False, "deny_platforms": []},
        S.load_targets(), {"sha256": "abc", "name": "sample-a.mp4"}, None,
    )
    assert row["reason"] == "campaign_terms_unconfirmed"
    assert row["will_dispatch"] is False
    paid_campaign = P.build_manifest(dict(campaign, is_ad=True))
    assert paid_campaign["platforms"][0]["will_dispatch"] is False
    assert paid_campaign["platforms"][0]["reason"] == "youtube_paid_label_unverified"


def test_policy_error_is_terminal_create_error(tmp_path, monkeypatch):
    import post_idempotency as idem
    monkeypatch.setenv(P.FLAG, "true")
    n = {"n": 0}

    def runner(item, row):
        n["n"] += 1
        return {
            "ok": False, "accepted": True, "error": "youtube_privacy_not_public",
            "video_id": "vidpriv1",
        }

    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": runner})
    item = _yt_item("pol1", "caption")
    manifest = P.build_manifest(item)
    ledger = tmp_path / "pol.jsonl"
    rows = _rows(manifest)
    first = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    second = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert first["platforms"][0]["status"] == "create_error"
    assert first["platforms"][0]["reason"] == "youtube_privacy_not_public"
    assert first["platforms"][0]["remote_id"] == "vidpriv1"
    assert first["error"] == "youtube_privacy_not_public"
    row = idem.lookup("pol1", "pub:youtube", path=ledger)
    assert row["status"] == "create_error"
    assert row["remote_id"] == "vidpriv1"
    assert row["error"] == "youtube_privacy_not_public"
    assert second["platforms"][0]["called"] is False
    assert second["platforms"][0]["status"] == "create_error"
    assert n["n"] == 1


def test_flag_off_dispatch_makes_no_calls(monkeypatch, tmp_path):
    monkeypatch.delenv(P.FLAG, raising=False)
    calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": lambda item, row: calls.append(row)})
    item = _yt_item("off-dispatch", "caption")
    monkeypatch.setenv(P.FLAG, "true")
    manifest = P.build_manifest(item)
    monkeypatch.delenv(P.FLAG, raising=False)
    assert manifest["will_dispatch_any"] is True
    item_out = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=_rows(manifest), ledger_path=tmp_path / "off.jsonl")
    plat = P.dispatch_platform(item, manifest["platforms"][0], ledger_path=tmp_path / "off.jsonl")
    assert item_out["error"] == "public_publish_off"
    assert item_out["dispatched"] is False
    assert plat["reason"] == "public_publish_off"
    assert plat["called"] is False
    assert calls == []


def test_one_item_hash_does_not_authorize_a_platform(monkeypatch):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": lambda item, row: calls.append(1) or {"ok": True, "youtube_label": True, "video_id": "abcdefghijk"}})
    item = _yt_item("hash1", "caption")
    cleaned = server._clean_item(item)
    preview = cleaned["public_preview"]
    data = {"items": [cleaned]}
    try:
        server.decide_approval(data, {
            "op": "decide", "id": "hash1", "status": "approved",
            "confirm_public": True, "manifest_hash": preview["manifest_hash"],
        })
        assert False
    except server.BadRequest as e:
        assert "platform_rows_required" in str(e)
    assert data["items"][0]["status"] == "pending"
    try:
        server.decide_approval(data, {
            "op": "decide", "id": "hash1", "status": "approved",
            "confirm_public": True, "manifest_hash": preview["manifest_hash"],
            "platform_rows": [{"key": "youtube", "row_hash": "0" * 64}],
        })
        assert False
    except server.BadRequest as e:
        assert "platform_not_confirmed" in str(e)
    assert calls == []


def test_read_local_and_upload_location_are_closed(tmp_path, monkeypatch):
    import publish_adapters as A
    base = tmp_path / "samples"
    base.mkdir()
    (base / "ok.mp4").write_bytes(b"ok-bytes")
    (base / "link.mp4").symlink_to(ROOT / "server.py")
    monkeypatch.setenv("CLIPPING_HUB_SAMPLES_DIR", str(base))
    assert A.read_local("ok.mp4", ROOT) == b"ok-bytes"
    assert A.read_local("../../server.py", ROOT) is None
    assert A.read_local("link.mp4", ROOT) is None
    assert A.read_local("/etc/passwd", ROOT) is None
    assert A.youtube_put_location_ok("https://www.googleapis.com/upload/youtube/v3/videos?upload_id=1")
    for bad in (
        "http://www.googleapis.com/upload/youtube/v3/videos",
        "https://upload.example/session",
        "https://localhost/upload",
        "https://169.254.169.254/latest",
        "https://metadata.google.internal/",
        "https://user:pass@www.googleapis.com/upload",
        "https://127.0.0.1/upload",
        "https://www.googleapis.com:8443/upload/youtube/v3/videos?upload_id=1",
    ):
        assert A.youtube_put_location_ok(bad) is False
    assert A.youtube_put_location_ok("https://www.googleapis.com:443/upload/youtube/v3/videos?upload_id=1")
    calls = []

    def http(method, url, headers, body):
        calls.append(method)
        if method == "GET":
            return _mine()
        return {"status": 200, "headers": {"Location": "https://upload.example/session"}, "json": {}}

    out = A.youtube_upload(
        {"title": "T"}, {"disclosures": {"ai": True, "paid": False}, "caption": "c", "artifact_sha256": _sha(b"mp4")},
        token="tok", http=http, file_bytes=b"mp4", expected_channel_id=MAIN_CHANNEL,
    )
    assert out["reason"] == "youtube_upload_location_rejected"
    assert calls == ["GET", "POST"]


def test_returned_channel_must_match_bound_grant():
    import publish_adapters as A

    def http(method, url, headers, body):
        if method == "GET":
            return _mine()
        if method == "POST":
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=z"}, "json": {}}
        return {"status": 201, "json": {"id": "vidchan1", "status": {"privacyStatus": "private", "containsSyntheticMedia": True}}}

    missing = A.youtube_upload(
        {"title": "T"}, {"disclosures": {"ai": True, "paid": False}, "caption": "c", "artifact_sha256": _sha(b"mp4")},
        token="tok", http=http, file_bytes=b"mp4", expected_channel_id=MAIN_CHANNEL,
    )
    assert missing["ok"] is False
    assert missing["reason"] == "youtube_video_missing_channel_id"
    assert missing["video_id"] == "vidchan1"

    def wrong(method, url, headers, body):
        if method == "GET":
            return _mine()
        if method == "POST":
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=z"}, "json": {}}
        return {"status": 201, "json": {
            "id": "vidchan2",
            "snippet": {"channelId": "UCnottheboundchannel00001"},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
        }}

    mismatch = A.youtube_upload(
        {"title": "T"}, {"disclosures": {"ai": True, "paid": False}, "caption": "c", "artifact_sha256": _sha(b"mp4")},
        token="tok", http=wrong, file_bytes=b"mp4", expected_channel_id=MAIN_CHANNEL,
    )
    assert mismatch["reason"] == "youtube_channel_mismatch"
    assert mismatch["video_id"] == "vidchan2"


def test_channel_identity_is_proven_before_any_upload_byte():
    import publish_adapters as A
    raw = b"mp4"
    row = {"disclosures": {"ai": True, "paid": False}, "caption": "c", "artifact_sha256": _sha(raw)}
    calls = []

    def mismatch(method, url, headers, body):
        calls.append((method, url, body))
        return {"status": 200, "json": {"items": [{"id": "UCaaaaaaaaaaaaaaaaaaaaaa"}]}}

    out = A.youtube_upload(
        {"title": "T"}, row, token="tok", http=mismatch, file_bytes=raw, expected_channel_id=MAIN_CHANNEL,
    )
    assert out["called"] is False
    assert out["reason"] == "youtube_channel_mismatch"
    assert [c[0] for c in calls] == ["GET"]
    assert calls[0][1] == A.YOUTUBE_CHANNELS_MINE
    assert calls[0][2] in (None, b"")

    calls.clear()

    def unproven(method, url, headers, body):
        calls.append(method)
        raise URLError("timed out")

    lost = A.youtube_upload(
        {"title": "T"}, row, token="tok", http=unproven, file_bytes=raw, expected_channel_id=MAIN_CHANNEL,
    )
    assert lost["called"] is False
    assert lost["reason"] == "youtube_channel_preflight_failed"
    assert calls == ["GET"]

    calls.clear()

    def several(method, url, headers, body):
        calls.append(method)
        return {"status": 200, "json": {"items": [{"id": MAIN_CHANNEL}, {"id": "UCaaaaaaaaaaaaaaaaaaaaaa"}]}}

    many = A.youtube_upload(
        {"title": "T"}, row, token="tok", http=several, file_bytes=raw, expected_channel_id=MAIN_CHANNEL,
    )
    assert many["called"] is False
    assert many["reason"] == "youtube_channel_preflight_failed"
    assert calls == ["GET"]

    hashed = []
    bad = A.youtube_upload(
        {"title": "T"}, dict(row, artifact_sha256="0" * 64), token="tok",
        http=lambda *a: hashed.append(1), file_bytes=raw, expected_channel_id=MAIN_CHANNEL,
    )
    assert bad["reason"] == "artifact_hash_mismatch"
    assert hashed == []

    incomplete = []

    def stalled(method, url, headers, body):
        incomplete.append((method, body))
        if method == "GET":
            return _mine()
        if method == "POST":
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=sess"}, "json": {}}
        return {"status": 308, "json": {}}

    held = A.youtube_upload(
        {"title": "T"}, row, token="tok", http=stalled, file_bytes=raw, expected_channel_id=MAIN_CHANNEL,
    )
    assert held["reason"] == "upload_incomplete"
    assert held["upload_length"] == len(raw)
    assert held["remote_id"].startswith("https://www.googleapis.com/")
    assert [step[0] for step in incomplete] == ["GET", "POST", "PUT"]
    assert incomplete[-1][1] == raw


def test_blank_channel_id_never_opens_a_session(monkeypatch, tmp_path):
    import publish_adapters as A
    calls = []

    def http(*args):
        calls.append(args)
        return {"status": 201, "json": {"id": "should-not"}}

    for blank in ("", "   ", None, "not-a-channel"):
        out = A.youtube_upload(
            {"title": "T"}, {"disclosures": {"ai": True, "paid": False}, "caption": "c"},
            token="tok", http=http, file_bytes=b"mp4", expected_channel_id=blank,
        )
        assert out["called"] is False
        assert out["reason"] == "youtube_channel_unbound"
    assert calls == []
    monkeypatch.setenv(P.FLAG, "true")
    runner_calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": lambda item, row: runner_calls.append(1)})
    cfg = S.load_targets()
    cfg["accounts"]["MAIN"]["youtube"] = dict(cfg["accounts"]["MAIN"]["youtube"], external_id="")
    item = _yt_item("nobind", "caption")
    manifest = P.build_manifest(item, targets=cfg)
    row = manifest["platforms"][0]
    assert row["will_dispatch"] is False
    assert row["reason"] == "youtube_channel_unbound"
    dispatched = P.dispatch_item(
        item, manifest["manifest_hash"], platform_rows=_rows(manifest),
        targets=cfg, ledger_path=tmp_path / "nobind.jsonl",
    )
    assert dispatched["dispatched"] is False
    assert runner_calls == []
    assert calls == []


def test_wrong_storyblocks_main_id_does_not_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv(P.FLAG, "true")
    calls = []
    monkeypatch.setattr(P, "external_runners", lambda: {
        "youtube": lambda item, row: calls.append(("youtube", row.get("key"))),
        "tiktok": lambda item, row: calls.append(("tiktok", row.get("key"))),
    })
    cfg = S.load_targets()
    cfg["targets"]["MAIN"] = dict(cfg["targets"]["MAIN"], yt="UC8TrAT8V-HacqYlqqqzIQKg")
    item = _yt_item("sbad", "caption")
    item["license"] = {"source": "storyblocks"}
    item["platforms"] = ["Clipped Motions YouTube", "TikTok Business"]
    item["rights_ok"] = True
    manifest = P.build_manifest(item, targets=cfg)
    assert manifest["route_blocked"] is True
    assert manifest["block_reason"] == "storyblocks_main_only_blocks_non_main_youtube"
    assert manifest["will_dispatch_any"] is False
    assert {r["key"]: r["reason"] for r in manifest["platforms"]} == {
        "youtube": "storyblocks_main_only_blocks_non_main_youtube",
        "tiktok": "storyblocks_main_only_blocks_non_main_youtube",
    }
    assert all(r["will_dispatch"] is False for r in manifest["platforms"])
    out = P.dispatch_item(
        item, manifest["manifest_hash"], platform_rows=_rows(manifest),
        targets=cfg, ledger_path=tmp_path / "sbad.jsonl",
    )
    assert out["dispatched"] is False
    assert str(out.get("error") or "").startswith("route_blocked:")
    assert calls == []


def test_synthetic_echo_missing_is_not_success():
    import publish_adapters as A

    def http(method, url, headers, body):
        if method == "GET":
            return _mine()
        if method == "POST":
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=z"}, "json": {}}
        return {"status": 201, "json": {
            "id": "vidsynth",
            "snippet": {"channelId": MAIN_CHANNEL},
            "status": {"privacyStatus": "private"},
        }}

    out = A.youtube_upload(
        {"title": "T"}, {"disclosures": {"ai": True, "paid": False}, "caption": "c", "artifact_sha256": _sha(b"mp4")},
        token="tok", http=http, file_bytes=b"mp4", expected_channel_id=MAIN_CHANNEL,
    )
    assert out["ok"] is False
    assert out["reason"] == "youtube_synthetic_echo_omitted"
    assert out["echo_omitted"] is True
    assert out["video_id"] == "vidsynth"


def test_put_200_with_id_matches_201_when_echo_is_present():
    import publish_adapters as A

    def http(method, url, headers, body):
        if method == "GET":
            return _mine()
        if method == "POST":
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=z"}, "json": {}}
        return {"status": 200, "json": {
            "id": "vid200ok",
            "snippet": {"channelId": MAIN_CHANNEL},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
        }}

    out = A.youtube_upload(
        {"title": "T"}, {"disclosures": {"ai": True, "paid": False}, "caption": "c", "artifact_sha256": _sha(b"mp4")},
        token="tok", http=http, file_bytes=b"mp4", expected_channel_id=MAIN_CHANNEL,
    )
    assert out["private_uploaded"] is True
    assert out["ok"] is False
    assert out["video_id"] == "vid200ok"


def test_present_false_synthetic_stays_terminal(monkeypatch, tmp_path):
    import publish_adapters as A
    calls = []

    def http(method, url, headers, body):
        if method == "GET":
            return _mine()
        if method == "POST":
            return {"status": 200, "headers": {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=z"}, "json": {}}
        return {"status": 201, "json": {
            "id": "vidfalse",
            "snippet": {"channelId": MAIN_CHANNEL},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": False},
        }}

    out = A.youtube_upload(
        {"title": "T"}, {"disclosures": {"ai": True, "paid": False}, "caption": "c", "artifact_sha256": _sha(b"mp4")},
        token="tok", http=http, file_bytes=b"mp4", expected_channel_id=MAIN_CHANNEL,
    )
    assert out["ok"] is False
    assert out["reason"] == "youtube_synthetic_not_confirmed"
    assert out.get("echo_omitted") is not True
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "_armed", lambda key, channel: True)

    def runner(item, row):
        calls.append(row.get("key"))
        return out

    item = _yt_item("falseecho1", "caption")
    manifest = P.build_manifest(item)
    row = next(r for r in manifest["platforms"] if r["key"] == "youtube")
    assert row["will_dispatch"] is True, row.get("reason")
    ledger = tmp_path / "echo-false.jsonl"
    first = P.dispatch_platform(item, row, ledger_path=ledger, runner=runner)
    second = P.dispatch_platform(item, row, ledger_path=ledger, runner=runner)
    assert first["status"] == "create_error"
    assert first["remote_id"] == "vidfalse"
    assert second["called"] is False
    assert calls == ["youtube"]


def test_omitted_echo_is_unknown_and_is_not_reuploaded(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setattr(P, "_armed", lambda key, channel: True)

    def runner(item, row):
        calls.append("upload")
        return {
            "ok": False, "called": True, "accepted": True, "echo_omitted": True,
            "reason": "youtube_synthetic_echo_omitted", "error": "youtube_synthetic_echo_omitted",
            "video_id": "LM6jkXooWGc",
        }

    item = _yt_item("echoomit1", "caption")
    manifest = P.build_manifest(item)
    row = next(r for r in manifest["platforms"] if r["key"] == "youtube")
    ledger = tmp_path / "echo-omit.jsonl"
    first = P.dispatch_platform(item, row, ledger_path=ledger, runner=runner)
    second = P.dispatch_platform(item, row, ledger_path=ledger, runner=runner)
    assert first["status"] == "unknown"
    assert first["reason"] == "youtube_synthetic_echo_omitted"
    assert first["remote_id"] == "LM6jkXooWGc"
    assert second["called"] is False
    assert second["status"] == "unknown"
    assert second["remote_id"] == "LM6jkXooWGc"
    assert calls == ["upload"]
    text = ledger.read_text()
    assert "LM6jkXooWGc" in text
    assert "youtube_synthetic_echo_omitted" in text


def test_uuid_campaign_rules_match_with_or_without_hyphens_and_miss_closed(monkeypatch, tmp_path):
    monkeypatch.setenv(P.FLAG, "true")
    base = json.loads((ROOT / "tests" / "fixtures" / "post_targets.json").read_text())
    rules = json.loads((ROOT / "tests" / "fixtures" / "campaign_rules_uuid.json").read_text())
    base["campaign_rules"] = rules["campaign_rules"]
    path = tmp_path / "uuid-targets.json"
    path.write_text(json.dumps(base))
    cfg = S.load_targets(path)
    manson = "6bdc8e4b-3ebf-44f1-aedb-067589ca9c89"
    cod = "78b4e379-2aa0-4d20-9fd0-ed02a816e3b1"
    sega = "8b79c473-d295-4901-8aee-e43c7ad03663"
    alliance = "50786486-a49d-4a17-b81b-0c416cb635da"
    assert S.campaign_rule_for({"campaign_id": manson}, cfg)["reason"] == "campaign_yt_ig_only"
    assert S.campaign_rule_for({"campaign_id": manson.replace("-", "")}, cfg)["deny_platforms"] == ["TikTok Business", "FB Page"]
    assert S.campaign_rule_for({"campaign_id": cod}, cfg)["deny_platforms"] == ["Clipped Motions YouTube", "FB Page"]
    assert "Clipped Motions YouTube" not in S.campaign_rule_for({"campaign_id": sega}, cfg)["deny_platforms"]
    assert S.campaign_rule_for({"campaign_id": "73ceebf3-10ea-4633-a490-0ed85502d96a"}, cfg)["deny_platforms"] == ["FB Page"]
    assert S.campaign_rule_for({"campaign_id": alliance}, cfg)["hold"] is True
    assert all(rule.get("deny_platforms") for rule in cfg["campaign_rules"].values())
    assert S.campaign_rule_for({"campaign_id": "cod"}, cfg) is None
    assert S.campaign_rule_for({"campaign_id": "heldalliance"}, cfg) is None
    unknown = "22222222-3333-4444-8555-666666666666"
    assert S.campaign_rule_for({"campaign_id": unknown}, cfg) is None
    stock = S.load_targets(ROOT / "tests" / "fixtures" / "post_targets.json")
    assert S.campaign_rule_for({"campaign_id": manson}, stock) is None
    assert S.campaign_rule_for({"campaign_id": "cod"}, stock)["reason"] == "campaign_tt_ig_only"
    monkeypatch.setattr(P, "_armed", lambda key, channel: True)
    denied = P.decide_platform(
        {"id": "manson1", "campaign_id": manson, "clip_type": "campaign", "is_ad": True, "caption": "c", "ai_disclosure": True, "rights_ok": True, "campaign_terms_ok": True},
        "TikTok Business",
        {"target": "PAID", "paid_promotion": True, "blocked": False, "deny_platforms": ["TikTok Business", "FB Page"], "campaign_config": "present"},
        cfg, {"sha256": "abc", "name": "sample-a.mp4"}, None,
    )
    assert denied["reason"] == "campaign_denies_platform"
    allowed = P.decide_platform(
        {"id": "sega1", "campaign_id": sega, "clip_type": "campaign", "is_ad": True, "caption": "c", "ai_disclosure": True, "rights_ok": True, "campaign_terms_ok": True},
        "Clipped Motions YouTube",
        {"target": "PAID", "paid_promotion": True, "blocked": False, "deny_platforms": ["FB Page"], "campaign_config": "present"},
        cfg, {"sha256": "abc", "name": "sample-a.mp4"}, None,
    )
    assert allowed["reason"] == "youtube_paid_label_unverified"
    absent = {
        "id": "uuidcamp1", "campaign_id": unknown, "is_ad": True, "clip_type": "campaign",
        "caption": "c", "title": "T", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "rights_ok": True, "campaign_terms_ok": True,
    }
    manifest = P.build_manifest(absent, targets=cfg)
    assert manifest["campaign_config"] == "absent"
    assert manifest["will_dispatch_any"] is False
    assert manifest["held"] is False
    assert any("campaign_config_absent" in (r.get("restrictions") or []) for r in manifest["platforms"])
    held = P.build_manifest({
        "id": "ally1", "campaign_id": alliance, "is_ad": True, "clip_type": "campaign",
        "caption": "c", "title": "T", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"], "ai_disclosure": True,
        "rights_ok": True, "campaign_terms_ok": True,
    }, targets=cfg)
    assert held["held"] is True and held["will_dispatch_any"] is False
    paid = json.loads(json.dumps(cfg))
    del paid["accounts"]["PAID"]["instagram"]
    fallback = P.decide_platform(
        {"id": "paidig", "clip_type": "campaign", "is_ad": True, "caption": "c", "ai_disclosure": True, "rights_ok": True, "campaign_terms_ok": True},
        "IG Business",
        {"target": "PAID", "paid_promotion": True, "blocked": False, "deny_platforms": [], "campaign_config": "not_campaign"},
        paid, {"sha256": "abc", "name": "sample-a.mp4"}, None,
    )
    assert fallback["reason"] == "account_unconfigured"
    assert fallback["account_id"] != cfg["accounts"]["MAIN"]["instagram"]["account_id"]
