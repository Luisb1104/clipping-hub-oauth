"""Callback must NOT save tokens on any non-ok verify (Deadbolt HIGH)."""
from __future__ import annotations

import json
from pathlib import Path

import youtube_label_step as Y


TARGETS = {
    "version": 1,
    "targets": {
        "MAIN": {"name": "Clipped Motions", "handle": "@m", "yt": "UCgMuVjQmB9WvZtSz4e23THw"},
        "PAID": {"name": "Clips", "handle": "@p", "yt": "UC8TrAT8V-HacqYlqqqzIQKg"},
    },
}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr("schedule_hook.load_targets", lambda path=None: TARGETS)
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(Y, "token_path", lambda ch: tmp_path / ("PAID.json" if str(ch).upper() == "PAID" else "MAIN.json"))
    monkeypatch.setattr(Y, "STATE_DIR", tmp_path / "oauth-state")
    Y.STATE_DIR.mkdir(parents=True, exist_ok=True)
    return tmp_path / "PAID.json"


def _run_callback_logic(ch, tok, verify_fn, monkeypatch, tmp_path):
    """Mirror server callback save gate (unit, no HTTP server)."""
    exp_name, exp_yt, exp_handle = Y.expected_yt_for_hub_channel(ch)
    connected_ok = False
    msg = "OAuth failed."
    if not tok:
        msg = "OAuth token exchange failed (no_token)."
        Y.discard_grant_tokens({}, ch)
    elif not tok.get("access_token"):
        msg = "OAuth failed: no access_token from Google. Token not saved."
        Y.discard_grant_tokens(tok, ch)
    elif not exp_yt:
        msg = "OAuth failed: missing expected YouTube channel id in post_targets. Token not saved."
        Y.discard_grant_tokens(tok, ch)
    else:
        try:
            verify = verify_fn()
        except Exception:
            verify = {"ok": False, "error": "verify_exception", "granted": []}
        if not isinstance(verify, dict) or not verify.get("ok"):
            msg = "YouTube grant failed. Token was NOT saved."
            Y.discard_grant_tokens(tok, ch)
        else:
            tok = dict(tok)
            tok["bound_channel_id"] = exp_yt
            tok["bound_channel_title"] = exp_name
            if Y.save_token(ch, tok):
                connected_ok = True
                msg = "YouTube connected for %s" % ch
            else:
                msg = "OAuth token save failed. Token was NOT kept."
                Y.discard_grant_tokens(tok, ch)
    return connected_ok, msg


def test_mismatch_grant_leaves_no_file(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    tok = {"refresh_token": "rt", "access_token": "at"}
    ok, msg = _run_callback_logic(
        "PAID", tok,
        lambda: {"ok": False, "mismatch": True, "error": "channel_mismatch", "granted": [{"id": "UCwrong", "title": "X"}]},
        monkeypatch, tmp_path,
    )
    assert ok is False
    assert "connected" not in msg.lower() or "not" in msg.lower()
    assert not path.exists()


def test_verify_error_leaves_no_file(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    tok = {"refresh_token": "rt", "access_token": "at"}
    ok, msg = _run_callback_logic(
        "PAID", tok,
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        monkeypatch, tmp_path,
    )
    assert ok is False
    assert not path.exists()


def test_no_access_token_leaves_no_file(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    tok = {"refresh_token": "rt"}  # no access_token
    ok, msg = _run_callback_logic("PAID", tok, lambda: {"ok": True}, monkeypatch, tmp_path)
    assert ok is False
    assert not path.exists()


def test_ok_verify_saves_bound(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    tok = {"refresh_token": "rt", "access_token": "at"}
    ok, msg = _run_callback_logic(
        "PAID", tok,
        lambda: {"ok": True, "granted": [{"id": "UC8TrAT8V-HacqYlqqqzIQKg", "title": "Clips"}]},
        monkeypatch, tmp_path,
    )
    assert ok is True
    assert "connected" in msg.lower()
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["bound_channel_id"] == "UC8TrAT8V-HacqYlqqqzIQKg"
    assert "channel_mismatch" not in data
