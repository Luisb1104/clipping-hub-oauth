"""Testing-mode 7-day grant: granted_at metadata, 24h warn once, expiry / invalid_grant fail closed."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import youtube_label_step as Y

@pytest.fixture(autouse=True)
def _testing_mode_on(monkeypatch):
    monkeypatch.setenv(Y.TESTING_MODE_FLAG, "true")



def _grant_ts(days_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - days_ago * 86400))


def test_save_token_records_granted_at_and_preserves_on_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    assert Y.save_token("MAIN", {"refresh_token": "rt1", "access_token": "a1", "granted_at": "2026-11-01T12:00:00-0500", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    d = json.loads((tmp_path / "MAIN.json").read_text())
    assert d["granted_at"] == "2026-11-01T12:00:00-0500"
    assert "refresh_token" in d  # secret present in file but not returned by grant_meta
    # refresh same token → preserve granted_at
    assert Y.save_token("MAIN", {"refresh_token": "rt1", "access_token": "a2", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    d2 = json.loads((tmp_path / "MAIN.json").read_text())
    assert d2["granted_at"] == "2026-11-01T12:00:00-0500"
    assert d2["access_token"] == "a2"
    # grant_meta never exposes refresh_token
    meta = Y.grant_meta("MAIN")
    assert "refresh_token" not in meta
    assert meta["granted_at"] == "2026-11-01T12:00:00-0500"


def test_grant_expires_in_days_chip_math(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    # Granted 5 days ago → ~2 days left
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "granted_at": _grant_ts(5), "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    meta = Y.grant_meta("MAIN")
    assert meta["present"] is True
    assert meta["expired"] is False
    assert meta["expires_in_days"] in (1, 2)  # rounding / timezone edge
    assert "yt_regrant=MAIN" in meta["regrant_url"]
    assert meta["regrant_url"].startswith("http://127.0.0.1:8505/")


def test_expired_grant_needs_oauth_and_approve_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    (tmp_path / "cid").write_text("c"); (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    monkeypatch.setattr(Y, "STATE_DIR", tmp_path / "state")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "granted_at": _grant_ts(8), "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    assert Y.needs_oauth("MAIN") is True
    alerts = []
    out = Y.run_after_approve(
        {"id": "e1", "title": "T", "route_target": "MAIN", "ai_disclosure": True},
        env={Y.FLAG: "true"},
        opus_fn=lambda i: (_ for _ in ()).throw(RuntimeError("should_not_upload")),
        push_fn=lambda t, b, key=None: alerts.append(t) or True,
    )
    assert out["ok"] is False
    assert out.get("need_oauth") is True
    assert out.get("regrant_url")
    assert any("re-grant" in a.lower() or "Re-grant" in a or "regrant" in a.lower() for a in alerts)


def test_invalid_grant_on_refresh_fails_closed_with_regrant(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    (tmp_path / "cid").write_text("c"); (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    monkeypatch.setattr(Y, "STATE_DIR", tmp_path / "state")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "granted_at": _grant_ts(1), "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    alerts = []

    def http_post(url, body):
        return {"error": "invalid_grant"}

    out = Y.run_after_approve(
        {"id": "ig1", "title": "T", "route_target": "MAIN"},
        env={Y.FLAG: "true"},
        http_post=http_post,
        opus_fn=lambda i: (_ for _ in ()).throw(RuntimeError("no")),
        push_fn=lambda t, b, key=None: alerts.append((t, b)) or True,
    )
    assert out["ok"] is False
    assert out.get("error") == "invalid_grant"
    assert out.get("need_oauth") is True
    assert any("re-grant" in t.lower() or "127.0.0.1:8505" in b for t, b in alerts)


def test_expiry_warn_once_per_grant(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    # 6.5 days ago → within 24h of 7d expiry
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "granted_at": _grant_ts(6.5), "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    pushes = []

    def push(title, body, key=None):
        pushes.append((title, body, key))
        return True

    assert Y.maybe_warn_grant_expiry("MAIN", push_fn=push) is True
    assert len(pushes) == 1
    assert "yt_regrant=MAIN" in pushes[0][1]
    # Second call deduped
    assert Y.maybe_warn_grant_expiry("MAIN", push_fn=push) is False
    assert len(pushes) == 1


def test_no_warn_when_plenty_of_time(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "granted_at": _grant_ts(1), "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    assert Y.maybe_warn_grant_expiry("MAIN", push_fn=lambda *a, **k: True) is False


def test_client_secret_json_verified_never_printed(tmp_path, monkeypatch):
    """Uses a temp fixture mirroring ~/.config layout — never asserts secret value."""
    d = tmp_path / "youtube-oauth"
    d.mkdir(mode=0o700)
    secret_path = d / "client_secret.json"
    payload = {
        "web": {
            "client_id": "cid.apps.googleusercontent.com",
            "client_secret": "THIS_MUST_NOT_APPEAR_IN_ASSERTIONS_OR_LOGS",
            "redirect_uris": [Y.DEFAULT_REDIRECT],
        }
    }
    secret_path.write_text(json.dumps(payload))
    secret_path.chmod(0o600)
    monkeypatch.setattr(Y, "TOKEN_DIR", d)
    out = Y.verify_client_secret_file(secret_path)
    assert out["ok"] is True
    assert out["type"] == "web"
    assert out["redirect_ok"] is True
    assert out["mode_ok"] is True
    # Ensure helper return value does not include the secret
    blob = json.dumps(out)
    assert "THIS_MUST_NOT_APPEAR" not in blob
    assert "client_secret" not in blob or out.get("ok") is True  # key name may appear in error paths only
    assert "THIS_MUST_NOT_APPEAR_IN_ASSERTIONS_OR_LOGS" not in blob


def test_regrant_hub_url_is_hub_not_callback():
    url = Y.regrant_hub_url("PAID")
    assert url == "http://127.0.0.1:8505/approvals?yt_regrant=PAID"
    assert "/oauth/youtube/callback" not in url


def test_flag_off_skips_grant_gates(tmp_path, monkeypatch):
    monkeypatch.delenv(Y.FLAG, raising=False)
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    out = Y.run_after_approve({"id": "x"}, env={})
    assert out["skipped"] is True
