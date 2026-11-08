"""Approvals inbox + events: read, decide (atomic), badge, no-network guard."""
import json, os, re, threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import server

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


def _live(tmp_path, approvals=None, events=None):
    data = tmp_path / "data"
    data.mkdir()
    state = data / "state.json"
    ap = data / "approvals.json"
    ev = data / "events.json"
    if approvals is not None:
        ap.write_text(json.dumps(approvals, indent=2) + "\n")
    if events is not None:
        ev.write_text(json.dumps(events, indent=2) + "\n")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, approvals_path=ap, events_path=ev))
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    tok = (data / "hub-token").read_text().strip()
    return httpd, base, tok, ap, ev


def _get(base, path):
    from urllib.request import urlopen, Request
    with urlopen(Request(base + path), timeout=3) as r:
        return r.status, json.loads(r.read().decode())


def _post(base, path, body, tok, origin=None):
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "X-Hub-Token": tok, "Content-Length": str(len(data))}
    if origin:
        headers["Origin"] = origin
    req = Request(base + path, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        return e.code, json.loads(e.read().decode())


SAMPLE = {
    "version": 1,
    "items": [
        {"id": "a1", "video": "/samples/sample-a.mp4", "caption": "One", "platforms": ["Clipped Motions YouTube"],
         "scheduled_at": "2026-11-07T18:00:00-05:00", "status": "pending", "note": "", "decided_at": None,
         "ai_disclosure": False},
        {"id": "a2", "video": "/samples/sample-b.mp4", "caption": "Two", "platforms": ["TikTok Business", "IG Business"],
         "scheduled_at": "2026-11-08T12:00:00-05:00", "status": "pending", "note": "", "decided_at": None,
         "ai_disclosure": False},
    ],
}


def test_load_approvals_empty_when_missing(tmp_path):
    ap = tmp_path / "approvals.json"
    d = server.load_approvals(ap)
    assert d == {"version": 1, "items": []}


def test_approvals_get_returns_pending_count(tmp_path):
    httpd, base, tok, ap, ev = _live(tmp_path, SAMPLE)
    try:
        code, body = _get(base, "/api/approvals")
        assert code == 200 and body["pending"] == 2 and len(body["items"]) == 2
    finally:
        httpd.shutdown()


def test_decide_approve_atomic_write(tmp_path):
    httpd, base, tok, ap, ev = _live(tmp_path, SAMPLE)
    try:
        before = ap.read_text()
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "approved"}, tok)
        assert code == 200 and body["ok"] is True and body["changed"] is True
        assert body["item"]["status"] == "approved" and body["item"]["decided_at"]
        assert body["pending"] == 1
        after = json.loads(ap.read_text())
        assert after["items"][0]["status"] == "approved"
        assert before != ap.read_text()
        # no leftover temp
        assert not list(ap.parent.glob(".approvals-*.tmp"))
    finally:
        httpd.shutdown()


def test_decide_reject_and_change_requested(tmp_path):
    httpd, base, tok, ap, ev = _live(tmp_path, SAMPLE)
    try:
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "rejected"}, tok)
        assert code == 200 and body["item"]["status"] == "rejected"
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a2", "status": "change_requested"}, tok)
        assert code == 400 and "note" in body["error"]
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a2", "status": "change_requested", "note": "fix caption"}, tok)
        assert code == 200 and body["item"]["status"] == "change_requested" and body["item"]["note"] == "fix caption"
        assert body["pending"] == 0
    finally:
        httpd.shutdown()


def test_unknown_id_is_404(tmp_path):
    httpd, base, tok, ap, ev = _live(tmp_path, SAMPLE)
    try:
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "nope", "status": "approved"}, tok)
        assert code == 404 and body["ok"] is False
    finally:
        httpd.shutdown()


def test_already_decided_is_idempotent(tmp_path):
    httpd, base, tok, ap, ev = _live(tmp_path, SAMPLE)
    try:
        _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "approved"}, tok)
        snap = ap.read_text()
        code, body = _post(base, "/api/approvals", {"op": "decide", "id": "a1", "status": "rejected"}, tok)
        assert code == 200 and body["changed"] is False and body["item"]["status"] == "approved"
        assert ap.read_text() == snap
    finally:
        httpd.shutdown()


def test_events_parsing(tmp_path):
    evdata = {"version": 1, "events": [
        {"id": "e1", "type": "approval_waiting", "at": "t", "title": "Wait", "body": "b", "ref": "a1"},
        {"id": "e2", "type": "payout", "at": "t", "title": "Paid", "body": "$0", "ref": ""},
        {"id": "bad", "type": "not-a-type", "at": "t", "title": "x", "body": "", "ref": ""},
    ]}
    httpd, base, tok, ap, ev = _live(tmp_path, SAMPLE, evdata)
    try:
        code, body = _get(base, "/api/events")
        assert code == 200
        types = [e["type"] for e in body["events"]]
        assert types == ["approval_waiting", "payout"]
    finally:
        httpd.shutdown()


def test_badge_count_in_markup():
    html = (STATIC / "index.html").read_text()
    assert 'id="nav-appr-badge"' in html and 'data-go="approvals"' in html
    assert "Approve records your go." in html
    assert "Nothing waiting" in html


def test_no_network_no_post_guard():
    """Hub must not call platforms; decisions only hit same-origin /api/approvals."""
    js = (STATIC / "app.js").read_text()
    # only same-origin API fetches
    fetches = re.findall(r'fetch\(\s*["\']([^"\']+)["\']', js)
    assert set(fetches) <= {"/api/state", "/api/approvals", "/api/events", "/api/shorts", "/api/credits", "/api/campaigns", "/api/script-queue", "/api/channels", "/api/revenue", "/api/youtube-oauth/start"}
    for banned in ("youtube.com", "tiktok.com", "instagram.com", "facebook.com", "graph.facebook", "whop.com", "googleapis"):
        assert banned not in js.lower()
    py = (ROOT / "server.py").read_text()
    for banned in ("urllib.request", "http.client", "requests.", "aiohttp", "socket.create_connection"):
        assert banned not in py
    assert "nothing posts by itself" in (STATIC / "index.html").read_text().lower() or "approve to post" in (STATIC / "index.html").read_text().lower()


def test_payout_does_not_alter_revenue_card():
    html = (STATIC / "index.html").read_text()
    pane = re.search(r'data-pane="revenue".*?</section>', html, re.S).group(0)
    assert "Not connected" in pane and "$0" in pane
    assert "payout" not in pane.lower()


def test_sw_has_local_notify_no_push_keys():
    sw = (STATIC / "sw.js").read_text()
    assert "showNotification" in sw and 'd.type !== "notify"' in sw
    assert "pushManager" not in sw and "applicationServerKey" not in sw and "vapid" not in sw.lower()
    assert 'clipping-hub-shell-v35' in sw
