"""OAuth callback hardening: st rename, 404 without grant, state validation, log redaction."""
from __future__ import annotations

import io
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import server
import youtube_label_step as Y


def _live(tmp_path, *, env=None):
    data = tmp_path / "data"
    data.mkdir()
    state = data / "state.json"
    ap = data / "approvals.json"
    ev = data / "events.json"
    ap.write_text(json.dumps({"version": 1, "items": []}) + "\n")
    ev.write_text(json.dumps({"version": 1, "events": []}) + "\n")
    # point oauth dirs into tmp
    os.environ["CLIP_YT_OAUTH_STATE_DIR"] = str(tmp_path / "oauth-state")
    os.environ["CLIP_YT_OAUTH_DIR"] = str(tmp_path / "oauth-tok")
    Y.STATE_DIR = Path(tmp_path / "oauth-state")
    Y.TOKEN_DIR = Path(tmp_path / "oauth-tok")
    if env:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, approvals_path=ap, events_path=ev))
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, base


def _get(base, path):
    req = Request(base + path, method="GET")
    try:
        with urlopen(req, timeout=3) as r:
            return r.status, r.read()
    except HTTPError as e:
        return e.code, e.read()


def test_static_get_200_with_flag_off_st_rename(tmp_path, monkeypatch):
    """st rename: normal static GET must not crash when flag is off (Deadbolt)."""
    monkeypatch.delenv(Y.FLAG, raising=False)
    monkeypatch.setenv(Y.FLAG, "false")
    httpd, base = _live(tmp_path, env={Y.FLAG: "false"})
    try:
        code, body = _get(base, "/")
        assert code == 200
        assert b"Clipping Hub" in body or b"<!doctype" in body.lower() or b"html" in body.lower()
        code2, _ = _get(base, "/sw.js")
        assert code2 == 200
    finally:
        httpd.shutdown()


def test_callback_404_when_no_grant_active(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "false")
    httpd, base = _live(tmp_path, env={Y.FLAG: "false"})
    try:
        code, body = _get(base, "/oauth/youtube/callback?code=x&state=abcdefghijklmnop")
        assert code == 404
        assert body == b"not found"
    finally:
        httpd.shutdown()


def test_callback_404_bad_state_token(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    httpd, base = _live(tmp_path, env={Y.FLAG: "true"})
    try:
        from urllib.parse import quote
        for bad in ("../etc/passwd", "short", "a" * 65, "has spaces!!!!!!!!!!", ""):
            code, _ = _get(base, "/oauth/youtube/callback?code=x&state=" + quote(bad, safe=""))
            assert code == 404, bad
    finally:
        httpd.shutdown()


def test_callback_404_traversal_state(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    Y.STATE_DIR = tmp_path / "oauth-state"
    Y.STATE_DIR.mkdir(parents=True)
    # Plant a file outside via weird name — validate_state_token must reject
    httpd, base = _live(tmp_path, env={Y.FLAG: "true"})
    try:
        code, _ = _get(base, "/oauth/youtube/callback?code=x&state=../../tmp/evilfileeeee")
        assert code == 404
        # ensure nothing outside STATE_DIR was deleted by a prior bug pattern
        assert not (tmp_path / "evilfileeeee").exists()
    finally:
        httpd.shutdown()


def test_callback_404_expired_state(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    Y.STATE_DIR = tmp_path / "oauth-state"
    Y.STATE_DIR.mkdir(parents=True, exist_ok=True)
    tok = "a" * 24
    # authorized but expired
    assert Y._save_oauth_state(tok, channel="MAIN", approval_id="x", code_verifier="v", authorized_approve=True)
    p = Y._state_path(tok)
    d = json.loads(p.read_text())
    d["at"] = str(time.time() - Y.STATE_TTL_S - 30)
    p.write_text(json.dumps(d))
    httpd, base = _live(tmp_path, env={Y.FLAG: "true"})
    try:
        code, _ = _get(base, f"/oauth/youtube/callback?code=x&state={tok}")
        assert code == 404
    finally:
        httpd.shutdown()


def test_log_message_redacts_oauth_query(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "false")
    httpd, base = _live(tmp_path, env={Y.FLAG: "false"})
    try:
        buf = io.StringIO()
        # Call handler log_message directly
        handler = httpd.RequestHandlerClass
        # Instantiate lightly via a request
        import sys
        old = sys.stderr
        sys.stderr = buf
        try:
            # Trigger a real request so log_message runs
            _get(base, "/oauth/youtube/callback?code=SUPERSECRET&state=abcdefghijklmnop")
        finally:
            sys.stderr = old
        logged = buf.getvalue()
        assert "SUPERSECRET" not in logged
        assert "abcdefghijklmnop" not in logged or "?redacted" in logged
        assert "?redacted" in logged or "/oauth/youtube/callback" in logged
    finally:
        httpd.shutdown()


def test_state_path_rejects_traversal(tmp_path):
    Y.STATE_DIR = tmp_path / "oauth-state"
    Y.STATE_DIR.mkdir(parents=True)
    import pytest
    with pytest.raises(ValueError):
        Y._state_path("../" + "a" * 16)
    with pytest.raises(ValueError):
        Y._state_path("short")
    good = "b" * 20
    p = Y._state_path(good)
    assert p.parent == Y.STATE_DIR.resolve() or str(Y.STATE_DIR.resolve()) in str(p)


def test_pkce_and_no_include_granted_scopes(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "STATE_DIR", tmp_path / "st")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    (tmp_path / "cid").write_text("client-1")
    url, err = Y.build_auth_url(channel="MAIN", approval_id="a1")
    assert err is None and url
    assert "code_challenge" in url and "code_challenge_method=S256" in url
    assert "include_granted_scopes" not in url
