"""YouTube label step: mocked HTTP only. Flag default OFF. Fail closed."""
from pathlib import Path
import json
import os
import youtube_label_step as Y


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(Y.FLAG, raising=False)
    assert Y.enabled() is False
    out = Y.run_after_approve({"id": "x", "title": "t", "route_target": "MAIN"})
    assert out["skipped"] is True
    assert out["ok"] is True


def test_scope_is_youtube_not_force_ssl():
    assert Y.SCOPE == "https://www.googleapis.com/auth/youtube"
    assert "force-ssl" not in Y.SCOPE
    assert "partner" not in Y.SCOPE


def test_token_save_chmod_600(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    ok = Y.save_token("MAIN", {"refresh_token": "rt-test", "access_token": "at", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    assert ok is True
    p = tmp_path / "MAIN.json"
    assert p.exists()
    assert (p.stat().st_mode & 0o777) == 0o600
    # never claim we print — just ensure file has token and load works
    loaded = Y.load_token("MAIN")
    assert loaded["refresh_token"] == "rt-test"


def test_happy_path_mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "old", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    # fake client files
    cid = tmp_path / "cid"; cid.write_text("cid-1")
    sec = tmp_path / "sec"; sec.write_text("sec-1")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", cid)
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", sec)

    calls = []

    def http_post(url, body):
        calls.append(("POST", url, {k: body[k] for k in body if k != "client_secret" and k != "refresh_token"}))
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        calls.append((method, url, body))
        assert "Bearer access-new" in headers.get("Authorization", "")
        if method == "GET":
            # after synthetic set → private+true; after public → public+true
            public_calls = [c for c in calls if c[0] == "PUT" and c[2] and c[2].get("status", {}).get("privacyStatus") == "public"]
            if public_calls:
                return {"items": [{"status": {"privacyStatus": "public", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        return {"id": (body or {}).get("id")}

    def opus(item):
        return {"video_id": "vid12345678", "privacy": "private"}

    pushes = []

    def push(title, body, key=None):
        pushes.append((title, body, key))
        return True

    item = {"id": "a1", "title": "Tip", "route_target": "MAIN", "ai_disclosure": True}
    out = Y.run_after_approve(
        item, env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json, opus_fn=opus, push_fn=push,
    )
    assert out["ok"] is True
    assert out["youtube_label"] is True
    assert out["video_id"] == "vid12345678"
    assert any("containsSyntheticMedia" in json.dumps(c[2] or {}) for c in calls if c[0] == "PUT")
    assert any(p[0].startswith("Set TikTok") for p in pushes)


def test_fail_closed_leaves_private_and_pushes(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    cid = tmp_path / "cid"; cid.write_text("c")
    sec = tmp_path / "sec"; sec.write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", cid)
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", sec)

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        if method == "GET":
            # synthetic never confirms
            return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": False, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        return {}

    pushes = []

    out = Y.run_after_approve(
        {"id": "b1", "title": "X", "route_target": "MAIN"},
        env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        opus_fn=lambda i: {"video_id": "v9xxxxxxxxx", "privacy": "private"},
        push_fn=lambda t, b, key=None: pushes.append(t) or True,
    )
    assert out["ok"] is False
    assert out["youtube_label"] is False
    assert "synthetic" in (out["error"] or "")
    assert any("failed" in t.lower() or "private" in t.lower() for t in pushes)


def test_needs_oauth_when_no_token(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(Y, "STATE_DIR", tmp_path / "state")
    cid = tmp_path / "cid"; cid.write_text("client-xyz")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", cid)
    monkeypatch.setenv(Y.FLAG, "true")
    out = Y.run_after_approve(
        {"id": "c1", "route_target": "MAIN"},
        env={Y.FLAG: "true"},
        opus_fn=lambda i: (_ for _ in ()).throw(RuntimeError("should not upload")),
    )
    assert out["need_oauth"] is True
    assert out["oauth_url"] and "accounts.google.com" in out["oauth_url"]
    from urllib.parse import unquote
    assert "googleapis.com/auth/youtube" in unquote(out["oauth_url"])
    assert "force-ssl" not in unquote(out["oauth_url"])


def test_per_channel_token_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    Y.save_token("MAIN", {"refresh_token": "m", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    Y.save_token("PAID", {"refresh_token": "p", "bound_channel_id": "UC8TrAT8V-HacqYlqqqzIQKg", "bound_channel_title": "Clips"})
    assert (tmp_path / "MAIN.json").exists()
    assert (tmp_path / "PAID.json").exists()
    assert Y.load_token("MAIN")["refresh_token"] == "m"
    assert Y.load_token("PAID")["refresh_token"] == "p"


def test_apply_tt_ig_after_push_success_and_fail():
    item = {"id": "d1", "status": "label_pending", "youtube_label_set": True, "ai_disclosure": True}
    Y.apply_tt_ig_after_push(item, True, yt_step_on=True)
    assert item["tiktok_label_set"] is True
    assert item["instagram_label_set"] is True
    assert item["status"] == "scheduled"
    item2 = {"id": "d2", "status": "label_pending", "youtube_label_set": True, "ai_disclosure": True}
    Y.apply_tt_ig_after_push(item2, False, yt_step_on=True)
    assert item2["status"] == "label_pending"
    assert not item2.get("tiktok_label_set")


def test_happy_path_push_fail_keeps_pending_and_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "old", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    cid = tmp_path / "cid"; cid.write_text("cid-1")
    sec = tmp_path / "sec"; sec.write_text("sec-1")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", cid)
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", sec)
    calls = []

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        calls.append(method)
        if method == "GET":
            public_done = calls.count("PUT") >= 2
            if public_done:
                return {"items": [{"status": {"privacyStatus": "public", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        return {"id": (body or {}).get("id")}

    pushes = []

    def push(title, body, key=None):
        pushes.append(title)
        # First call is TT/IG notify → fail; failure alert may follow
        if title.startswith("Set TikTok"):
            return False
        return True

    item = {"id": "pf1", "title": "Tip", "route_target": "MAIN", "ai_disclosure": True, "status": "label_pending"}
    out = Y.run_after_approve(
        item, env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        opus_fn=lambda i: {"video_id": "vid12345678", "privacy": "private"},
        push_fn=push,
    )
    assert out["youtube_label"] is True
    assert out["tt_ig_push"] is False
    assert item["status"] == "label_pending"
    assert any("failed" in t.lower() or "private" in t.lower() for t in pushes)
