"""OAuth grant must bind the expected YouTube channel; mismatch is fail-closed (no token file)."""
from __future__ import annotations

import json
from pathlib import Path

import youtube_label_step as Y


TARGETS = {
    "version": 1,
    "poster": "opus",
    "targets": {
        "MAIN": {
            "name": "Clipped Motions",
            "handle": "@clippedmotions",
            "yt": "UCgMuVjQmB9WvZtSz4e23THw",
            "opus_post_account_id": "opus-main",
        },
        "PAID": {
            "name": "Clipped Motions Clips",
            "handle": "@clippedmotionsclips",
            "yt": "UC8TrAT8V-HacqYlqqqzIQKg",
            "opus_post_account_id": "opus-paid",
        },
    },
}


def _targets(monkeypatch):
    monkeypatch.setattr("schedule_hook.load_targets", lambda path=None: TARGETS)


def test_verify_grant_ok_when_expected_present(monkeypatch):
    _targets(monkeypatch)
    def http_json(method, url, headers, body):
        assert "channels" in url and "mine=true" in url
        return {"items": [
            {"id": "UC8TrAT8V-HacqYlqqqzIQKg", "snippet": {"title": "Clipped Motions Clips"}},
            {"id": "UCother", "snippet": {"title": "Other"}},
        ]}
    out = Y.verify_grant_matches_channel("PAID", "atok", http_json=http_json)
    assert out["ok"] is True
    assert out["mismatch"] is False
    assert out["expected_id"] == "UC8TrAT8V-HacqYlqqqzIQKg"


def test_verify_grant_mismatch(monkeypatch):
    _targets(monkeypatch)
    def http_json(method, url, headers, body):
        return {"items": [{"id": "UCwrong", "snippet": {"title": "Wrong"}}]}
    out = Y.verify_grant_matches_channel("MAIN", "atok", http_json=http_json)
    assert out["ok"] is False
    assert out["mismatch"] is True
    assert out["error"] == "channel_mismatch"


def test_assert_video_owned_requires_bind_and_targets(monkeypatch):
    _targets(monkeypatch)
    try:
        Y.assert_video_owned_by_grant(
            {"privacyStatus": "private", "channelId": "UC8TrAT8V-HacqYlqqqzIQKg"},
            "PAID",
            bound_channel_id=None,
        )
        assert False
    except RuntimeError as e:
        assert "youtube_missing_bound_channel_id" in str(e)


def test_assert_video_owned_fail_closed_wrong_video(monkeypatch):
    _targets(monkeypatch)
    try:
        Y.assert_video_owned_by_grant(
            {"privacyStatus": "private", "channelId": "UCwrong"},
            "PAID",
            bound_channel_id="UC8TrAT8V-HacqYlqqqzIQKg",
        )
        assert False
    except RuntimeError as e:
        assert "youtube_channel_mismatch" in str(e)


def test_assert_video_owned_ok(monkeypatch):
    _targets(monkeypatch)
    assert Y.assert_video_owned_by_grant(
        {"privacyStatus": "private", "channelId": "UC8TrAT8V-HacqYlqqqzIQKg"},
        "PAID",
        bound_channel_id="UC8TrAT8V-HacqYlqqqzIQKg",
    ) is True


def test_save_token_keeps_bound_fields_drops_mismatch(tmp_path, monkeypatch):
    _targets(monkeypatch)
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(Y, "token_path", lambda ch: tmp_path / ("PAID.json" if str(ch).upper() == "PAID" else "MAIN.json"))
    ok = Y.save_token("PAID", {
        "refresh_token": "rt",
        "access_token": "at",
        "bound_channel_id": "UC8TrAT8V-HacqYlqqqzIQKg",
        "bound_channel_title": "Clipped Motions Clips",
        "granted_channel_ids": ["UC8TrAT8V-HacqYlqqqzIQKg", "UCother"],
        "channel_mismatch": True,
    })
    assert ok is True
    data = json.loads((tmp_path / "PAID.json").read_text())
    assert data["bound_channel_id"] == "UC8TrAT8V-HacqYlqqqzIQKg"
    assert data["bound_channel_title"] == "Clipped Motions Clips"
    assert data["granted_channel_ids"] == ["UC8TrAT8V-HacqYlqqqzIQKg", "UCother"]
    assert "channel_mismatch" not in data


def test_needs_oauth_and_refresh_refuse_bad_bind(tmp_path, monkeypatch):
    _targets(monkeypatch)
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(Y, "token_path", lambda ch: tmp_path / "MAIN.json")
    # Token present but wrong/missing bind → needs_oauth
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "at"})
    assert Y.needs_oauth("MAIN") is True
    access, err = Y.refresh_access("MAIN", http_post=lambda *a, **k: {"access_token": "new"})
    assert access is None
    assert err == "channel_bind_mismatch"
    # Correct bind → needs_oauth false (non-testing)
    Y.save_token("MAIN", {
        "refresh_token": "rt",
        "access_token": "at",
        "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw",
        "bound_channel_title": "Clipped Motions",
    })
    assert Y.token_bind_ok("MAIN") is True
    assert Y.needs_oauth("MAIN") is False


def test_discard_leaves_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(Y, "token_path", lambda ch: tmp_path / "PAID.json")
    p = tmp_path / "PAID.json"
    p.write_text(json.dumps({"refresh_token": "rt"}))
    revoked = []
    Y.discard_grant_tokens(
        {"access_token": "atok", "refresh_token": "rtok"},
        "PAID",
        http_post=lambda url, body: revoked.append(url) or {},
    )
    assert not p.exists()
    assert any("revoke" in u for u in revoked)


def test_put_status_body_excludes_channel_id(monkeypatch):
    """LOW: videos.update part=status must not carry channelId in the status object."""
    puts = []

    def http_json(method, url, headers, body):
        if method == "GET":
            return {"items": [{"status": {
                "privacyStatus": "private",
                "containsSyntheticMedia": False,
                "embeddable": True,
            }, "snippet": {"channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        puts.append(body)
        return {"id": "vid"}

    Y.update_video_status(
        "vid12345678901", "atok",
        {"containsSyntheticMedia": True, "privacyStatus": "private"},
        http_json=http_json,
    )
    assert len(puts) == 1
    body = puts[0]
    assert set(body.keys()) == {"id", "status"}
    assert "channelId" not in body["status"]
    assert set(body["status"].keys()) <= {
        "privacyStatus", "containsSyntheticMedia", "embeddable",
        "license", "publicStatsViewable", "selfDeclaredMadeForKids",
        "madeForKids", "publishAt",
    }
    assert body["status"]["containsSyntheticMedia"] is True
    assert body["status"]["privacyStatus"] == "private"
