"""oauth_url e2e: /api/youtube-oauth/start + first-grant / re-grant redirect (Google mocked)."""
from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest

import pytest

import server as S
import youtube_label_step as Y


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path / "tok")
    monkeypatch.setattr(Y, "STATE_DIR", tmp_path / "state")
    (tmp_path / "tok").mkdir()
    (tmp_path / "state").mkdir()
    cid = tmp_path / "cid"; cid.write_text("client-id-xyz")
    sec = tmp_path / "sec"; sec.write_text("client-secret-xyz")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", cid)
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", sec)
    # Hub paths
    sp = tmp_path / "state.json"; sp.write_text(json.dumps(S.default_state()))
    ap = tmp_path / "approvals.json"
    ap.write_text(json.dumps({"version": 1, "items": []}))
    ep = tmp_path / "events.json"; ep.write_text(json.dumps(S.default_events()))
    token_path = tmp_path / "hub-token"; token_path.write_text("test-hub-token")
    st_dir = Path(S.__file__).resolve().parent / "static"
    handler = S.make_handler(
        state_path=sp, approvals_path=ap, events_path=ep,
        token_path=token_path, static_dir=st_dir,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, "test-hub-token", tmp_path
    httpd.shutdown()


def _post(base, path, body, token, origin=None):
    data = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(data)),
        "X-Hub-Token": token,
        "Sec-Fetch-Site": "same-origin",
    }
    if origin:
        headers["Origin"] = origin
    req = urlrequest.Request(base + path, data=data, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except Exception as e:
        if hasattr(e, "code"):
            body = e.read().decode() if hasattr(e, "read") else ""
            try:
                return e.code, json.loads(body or "{}")
            except Exception:
                return e.code, {"raw": body}
        raise


def _get(base, path):
    with urlrequest.urlopen(base + path, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode() or "{}")


def test_oauth_start_requires_flag_and_auth(hub, monkeypatch):
    base, token, _ = hub
    monkeypatch.setenv(Y.FLAG, "false")
    code, body = _post(base, "/api/youtube-oauth/start", {"channel": "MAIN"}, token)
    assert code == 404
    monkeypatch.setenv(Y.FLAG, "true")
    code2, body2 = _post(base, "/api/youtube-oauth/start", {"channel": "MAIN"}, "wrong-token")
    assert code2 == 403


def test_oauth_start_returns_oauth_url_with_pkce_state(hub):
    base, token, tmp = hub
    code, body = _post(base, "/api/youtube-oauth/start", {"channel": "MAIN", "approval_id": "appr1"}, token)
    assert code == 200
    assert body.get("ok") is True
    url = body.get("oauth_url") or ""
    assert "accounts.google.com" in url
    assert "code_challenge" in url
    assert "state=" in url
    assert "auth_url" not in body  # oauth_url end to end
    # state file landed
    states = list((tmp / "state").glob("*.json"))
    assert states


def test_regrant_start_paid_channel(hub):
    base, token, _ = hub
    code, body = _post(base, "/api/youtube-oauth/start", {"channel": "PAID"}, token)
    assert code == 200
    assert body["channel"] == "PAID"
    assert "yt_regrant=PAID" in body.get("regrant_url", "")


def test_first_grant_run_after_approve_returns_oauth_url(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(Y, "STATE_DIR", tmp_path / "state")
    (tmp_path / "cid").write_text("c"); (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    out = Y.run_after_approve(
        {"id": "fg1", "title": "T", "route_target": "MAIN"},
        env={Y.FLAG: "true"},
        opus_fn=lambda i: (_ for _ in ()).throw(RuntimeError("no")),
        push_fn=lambda *a, **k: True,
    )
    assert out["need_oauth"] is True
    assert out.get("oauth_url") and "accounts.google.com" in out["oauth_url"]
    assert "auth_url" not in out or out.get("auth_url") is None


def test_expiry_warn_not_on_unauthenticated_get(hub, monkeypatch):
    """LOW: GET /api/state must not fire expiry push; authorized tick may (Testing mode)."""
    base, token, tmp = hub
    import time
    monkeypatch.setenv(Y.TESTING_MODE_FLAG, "true")
    granted = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 6.5 * 86400))
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "granted_at": granted, "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    code, body = _get(base, "/api/state")
    assert code == 200
    tok = Y.load_token("MAIN")
    assert not tok.get("expiry_warn_for_granted_at")
    # Gap=0 so authorized tick is not rate-limited in this unit test.
    import server as _Srv
    monkeypatch.setattr(_Srv, "TICK_MIN_GAP_S", 0)
    monkeypatch.setattr(Y, "maybe_warn_grant_expiry", lambda ch, push_fn=None, now=None, env=None: True if ch == "MAIN" else False)
    monkeypatch.setattr(Y, "check_grant_alive", lambda *a, **k: (True, None))
    code2, body2 = _post(base, "/api/youtube-label/tick", {"force": True}, token)
    assert code2 == 200
    assert body2.get("ok") is True
    assert "MAIN" in (body2.get("warns") or [])


def test_label_pending_reapprove_reconcile_only(tmp_path, monkeypatch):
    """Approve on label_pending is re-entrant for reconcile; never a second create POST."""
    data = {
        "version": 1,
        "items": [{
            "id": "lp1", "status": "label_pending", "ai_disclosure": True,
            "video": "v.mp4", "caption": "c", "title": "t",
            "platforms": ["Clipped Motions YouTube"],
            "projectId": "P", "clipId": "C",
        }],
    }
    # decide_approval should return changed=True for label_pending + approved
    d2, item, changed = S.decide_approval(data, {"op": "decide", "id": "lp1", "status": "approved"})
    assert changed is True
    assert item["status"] == "label_pending"
