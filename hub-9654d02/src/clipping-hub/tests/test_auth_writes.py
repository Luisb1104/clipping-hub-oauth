"""Write endpoints require the existing hub-token + same-origin gate (_authorized)."""
import json, threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import server

SAMPLE = {
    "version": 1,
    "items": [
        {"id": "a1", "video": "/samples/sample-a.mp4", "caption": "One",
         "platforms": ["Clipped Motions YouTube"], "scheduled_at": "2026-11-07T18:00:00-05:00",
         "status": "pending", "note": "", "decided_at": None, "ai_disclosure": False},
    ],
}


def _live(tmp_path):
    data = tmp_path / "data"; data.mkdir()
    state = data / "state.json"
    ap = data / "approvals.json"
    ev = data / "events.json"
    ap.write_text(json.dumps(SAMPLE) + "\n")
    ev.write_text(json.dumps({"version": 1, "events": []}) + "\n")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, approvals_path=ap, events_path=ev))
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    tok = (data / "hub-token").read_text().strip()
    return httpd, base, tok


def _post(base, path, body, headers):
    raw = json.dumps(body).encode()
    h = {"Content-Type": "application/json", "Content-Length": str(len(raw))}
    h.update(headers or {})
    req = Request(base + path, data=raw, headers=h, method="POST")
    try:
        with urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_unauthed_state_post_is_403(tmp_path):
    httpd, base, tok = _live(tmp_path)
    try:
        code, body = _post(base, "/api/state", {"op": "theme", "value": "dark"}, {})
        assert code == 403 and body.get("ok") is False
        code, body = _post(base, "/api/state", {"op": "theme", "value": "dark"}, {"X-Hub-Token": "nope"})
        assert code == 403
    finally:
        httpd.shutdown()


def test_authed_state_post_is_200(tmp_path):
    httpd, base, tok = _live(tmp_path)
    try:
        code, body = _post(base, "/api/state", {"op": "theme", "value": "dark"}, {"X-Hub-Token": tok})
        assert code == 200 and body.get("theme") == "dark"
    finally:
        httpd.shutdown()


def test_unauthed_approvals_post_is_403(tmp_path):
    httpd, base, tok = _live(tmp_path)
    try:
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "approved"}, {})
        assert code == 403 and body.get("ok") is False
        code, _ = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "approved"}, {"X-Hub-Token": "wrong"})
        assert code == 403
    finally:
        httpd.shutdown()


def test_authed_approvals_post_is_200(tmp_path):
    httpd, base, tok = _live(tmp_path)
    try:
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "approved"}, {"X-Hub-Token": tok})
        assert code == 200 and body.get("ok") is True and body["item"]["status"] == "approved"
    finally:
        httpd.shutdown()


def test_unauthed_events_post_is_403(tmp_path):
    httpd, base, tok = _live(tmp_path)
    try:
        ev = {"op": "append", "event": {"id": "e1", "type": "approval_waiting", "title": "Wait", "body": "x"}}
        code, body = _post(base, "/api/events", ev, {})
        assert code == 403 and body.get("ok") is False
    finally:
        httpd.shutdown()


def test_authed_events_post_appends(tmp_path):
    httpd, base, tok = _live(tmp_path)
    try:
        ev = {"op": "append", "event": {"id": "e1", "type": "payout", "title": "Payout", "body": "Recorded"}}
        code, body = _post(base, "/api/events", ev, {"X-Hub-Token": tok})
        assert code == 200 and body.get("changed") is True and body["item"]["id"] == "e1"
        # idempotent
        code, body = _post(base, "/api/events", ev, {"X-Hub-Token": tok})
        assert code == 200 and body.get("changed") is False
    finally:
        httpd.shutdown()


def test_proxy_origin_host_match_still_works_on_approvals(tmp_path):
    """Phone via :8445: Origin host must equal Host (existing hub rule)."""
    httpd, base, tok = _live(tmp_path)
    try:
        host = "hub.tailnet.ts.net:8445"
        good = {"Host": host, "Origin": "https://%s" % host, "X-Hub-Token": tok}
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "approved"}, good)
        assert code == 200 and body.get("ok") is True
        bad = {"Host": host, "Origin": "https://evil.example", "X-Hub-Token": tok}
        code, _ = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "rejected"}, bad)
        assert code == 403
    finally:
        httpd.shutdown()
