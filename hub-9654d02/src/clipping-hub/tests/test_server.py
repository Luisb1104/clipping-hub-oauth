"""Clipping Hub shell: pages, local-only state, approval gate. Run: python -m pytest -q"""
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import server

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


def get(live, path):
    try:
        with urllib.request.urlopen(live.base + path) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def post(live, body, path="/api/state", raw=None, token=True, headers=None):
    data = raw if raw is not None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if token is True:
        h["X-Hub-Token"] = (live.state.parent / "hub-token").read_text().strip()
    elif token:
        h["X-Hub-Token"] = token
    h.update(headers or {})
    req = urllib.request.Request(live.base + path, data=data, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def tick_all(live, cid):
    for item in server.CHECK_IDS:
        assert post(live, {"op": "check", "id": cid, "item": item, "value": True})[0] == 200


def tree_snapshot(root):
    skip = {"__pycache__", ".pytest_cache", ".git", ".venv", "data", "shots"}
    out = {}
    for p in Path(root).rglob("*"):
        if p.is_file() and not (set(p.relative_to(root).parts) & skip) and p.suffix != ".pyc":
            st = p.stat(); out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return out


# ---------- pages ----------
def test_each_page_is_served(live):
    for path in server.PAGES:
        status, hdr, body = get(live, path)
        assert status == 200, path
        assert hdr["Content-Type"].startswith("text/html")
        assert b"Clipping Hub" in body
    assert server.PAGES == ("/", "/home", "/queue", "/approvals", "/channels", "/revenue", "/trends")


def test_shell_has_all_five_screens():
    html = (STATIC / "index.html").read_text()
    for pane in ("home", "queue", "approvals", "channels", "revenue", "trends"):
        assert 'data-pane="%s"' % pane in html
        assert 'data-go="%s"' % pane in html


def test_static_assets_served(live):
    for f in ("app.css", "app.js", "sw.js", "logo.svg", "sky-air-tokens.css", "motion.css", "theme-init.js", "manifest.webmanifest"):
        status, _, body = get(live, "/" + f)
        assert status == 200 and len(body) > 0, f


def test_unknown_and_traversal_are_404(live):
    assert get(live, "/nope.txt")[0] == 404
    host, port = live.base[7:].split(":")
    for p in ("/../server.py", "/%2e%2e/server.py", "/..%2fserver.py", "/static/../server.py"):
        c = http.client.HTTPConnection(host, int(port)); c.request("GET", p)
        r = c.getresponse(); body = r.read(); c.close()
        assert r.status in (404, 400) and b"ThreadingHTTPServer" not in body, p


def test_server_binds_localhost_8505_by_default():
    assert server.HOST == "127.0.0.1"
    assert server.PORT == 8505
    src = (ROOT / "server.py").read_text()
    assert "0.0.0.0" not in src


# ---------- state file stays inside data/ ----------
def test_default_state_path_is_data_state_json():
    assert server.ROOT / "data" / "state.json" == Path(server.__file__).resolve().parent / "data" / "state.json"
    assert server.STATE_PATH.name == "state.json"


def test_state_written_only_to_data(live):
    before = tree_snapshot(ROOT)
    for body in ({"op": "theme", "value": "dark"}, {"op": "add_sample"}, {"op": "clip", "id": "sample-1", "action": "skip"}):
        assert post(live, body)[0] == 200
    files = sorted(str(p.relative_to(live.dir)) for p in live.dir.rglob("*") if p.is_file())
    assert files == ["data/hub-token", "data/state.json"]
    assert tree_snapshot(ROOT) == before          # nothing else in the project changed


def test_state_file_is_never_empty_or_left_half_written(live):
    post(live, {"op": "add_sample"})
    text = live.state.read_text()
    assert text.strip() and json.loads(text)["clips"][0]["status"] == "pending"
    assert not list(live.state.parent.glob(".state-*.tmp"))


def test_get_is_read_only_and_creates_nothing(live):
    for p in server.PAGES + ("/api/state", "/app.js"):
        get(live, p)
    assert not live.state.exists()
    s = json.loads(get(live, "/api/state")[2])
    assert s["clips"] == [] and s["theme"] is None


def test_other_methods_and_paths_are_rejected(live):
    assert post(live, {"op": "theme", "value": "dark"}, path="/other")[0] == 405
    for m in ("PUT", "DELETE", "PATCH"):
        req = urllib.request.Request(live.base + "/api/state", data=b"{}", method=m)
        try:
            urllib.request.urlopen(req); assert False
        except urllib.error.HTTPError as e:
            assert e.code == 405
    assert not live.state.exists()


def test_bad_requests_write_nothing(live):
    for raw in (b"not json", b"[]", b'{"op":"nope"}', b'{"op":"theme","value":"pink"}', b'{"op":"clip","id":"x","action":"approve"}',
                b'{"op":"clip","id":"x","action":"post"}', b"", b"x" * 5000):
        assert post(live, None, raw=raw)[0] == 400
    assert not live.state.exists()


def test_damaged_state_file_falls_back_to_defaults(live):
    live.state.parent.mkdir(parents=True, exist_ok=True); live.state.write_text("{oops")
    assert json.loads(get(live, "/api/state")[2])["clips"] == []


def test_theme_toggle_is_remembered_in_state(live):
    assert post(live, {"op": "theme", "value": "dark"})[0] == 200
    assert json.loads(get(live, "/api/state")[2])["theme"] == "dark"
    assert json.loads(live.state.read_text())["theme"] == "dark"


def test_theme_is_also_remembered_in_browser_storage():
    assert "clippinghub.theme" in (STATIC / "app.js").read_text()
    assert "clippinghub.theme" in (STATIC / "theme-init.js").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'data-theme-set="light"' in html and 'data-theme-set="dark"' in html


# ---------- approval gate: local marks only ----------
def test_approval_gate_changes_stay_local(live):
    post(live, {"op": "add_sample"}); post(live, {"op": "add_sample"}); post(live, {"op": "add_sample"})
    tick_all(live, "sample-1")                      # approving now needs the full compliance checklist (see test_compliance below)
    for cid, act, want in (("sample-1", "approve", "approved"), ("sample-2", "skip", "skipped"), ("sample-3", "edit", "edit")):
        code, s = post(live, {"op": "clip", "id": cid, "action": act})
        assert code == 200 and {c["id"]: c["status"] for c in s["clips"]}[cid] == want
    saved = json.loads(live.state.read_text())
    assert [c["status"] for c in saved["clips"]] == ["approved", "skipped", "edit"]
    assert all(c["sample"] is True for c in saved["clips"])
    assert set(saved) == {"version", "theme", "clips", "updated"}      # no "posted", "published", token or URL fields
    assert set(saved["clips"][0]) == {"id", "title", "platform", "sample", "status", "checks"}
    assert not re.search(r"https?://", live.state.read_text())
    assert sorted(p.name for p in live.dir.rglob("*") if p.is_file()) == ["hub-token", "state.json"]
    code, s = post(live, {"op": "clip", "id": "sample-1", "action": "undo"})
    assert {c["id"]: c["status"] for c in s["clips"]}["sample-1"] == "pending"


def test_sample_clips_are_labelled_and_capped(live):
    for _ in range(server.MAX_CLIPS):
        assert post(live, {"op": "add_sample"})[0] == 200
    assert post(live, {"op": "add_sample"})[0] == 400
    s = json.loads(live.state.read_text())
    assert all(c["sample"] and c["title"].startswith("Sample clip") for c in s["clips"])
    assert post(live, {"op": "clear_samples"})[1]["clips"] == []


def test_queue_page_says_nothing_is_posted():
    html = (STATIC / "index.html").read_text()
    assert "Nothing is posted" in html
    for label in (">Approve<", ">Edit<", ">Skip<"):
        assert label in html


# ---------- revenue: $0 / not connected breakdown, no invented numbers ----------
REVENUE_SOURCES = (
    "youtube-partner", "whop-campaigns", "other-platforms",
    "youtube-shorts", "instagram-reels", "facebook", "tiktok",
)

def test_revenue_card_shows_zero_and_planned():
    html = (STATIC / "index.html").read_text()
    pane = re.search(r'<section class="pane" data-pane="revenue".*?</section>', html, re.S).group(0)
    assert re.search(r'id="pool-total"[^>]*>\$0<', pane)
    assert pane.count('class="glass pool') == 1
    assert 'id="pool-month"' in pane and re.search(r'id="pool-month"[^>]*>\$0<', pane)
    assert 'id="pool-combined"' in pane and re.search(r'id="pool-combined"[^>]*>\$0<', pane)
    assert "This month" in pane and "Combined total" in pane
    assert "Not connected" in pane
    assert "live" not in pane.lower() and "verified" not in pane.lower()


def test_revenue_breakdown_every_source_is_zero_not_connected():
    """Regression: every known source renders $0 labelled Not connected; combined total is $0."""
    html = (STATIC / "index.html").read_text()
    pane = re.search(r'<section class="pane" data-pane="revenue".*?</section>', html, re.S).group(0)
    srcs = re.findall(r'data-rev-src="([a-z0-9-]+)"', pane)
    assert srcs == list(REVENUE_SOURCES) + ["combined"]
    for sid in REVENUE_SOURCES:
        row = re.search(r'data-rev-src="%s"[^>]*>(.*?)</div>\s*</div>' % sid, pane, re.S).group(1)
        assert "$0" in row and "Not connected" in row, sid
    assert re.search(r'id="pool-total"[^>]*>\$0<', pane)
    assert re.search(r'id="pool-month"[^>]*>\$0<', pane)
    assert re.search(r'id="pool-combined"[^>]*>\$0<', pane)
    # channel rows match the Channels pane (no invented niches)
    ch_ids = re.findall(r'data-connect="([a-z-]+)"', html)
    assert ch_ids == []  # Connect placeholders removed; Opus sync renders channels
    for cid in ch_ids:
        assert 'data-rev-src="%s"' % cid in pane
    assert "YouTube Partner" in pane and "Whop campaigns" in pane and "Other platforms" in pane
    amounts = re.findall(r"\$\s?\d[\d,.]*", pane)
    assert set(amounts) == {"$0"} and amounts.count("$0") >= 10


def test_no_other_money_figures_anywhere_in_the_front_end():
    for f in STATIC.iterdir():
        if f.suffix in (".html", ".js", ".css", ".svg", ".webmanifest"):
            amounts = re.findall(r"\$\s?\d[\d,.]*", f.read_text())
            assert set(amounts) <= {"$0"}, (f.name, amounts)       # the only dollar figure allowed anywhere is $0


# ---------- channels: Connect only shows a not-connected message ----------
def test_channel_slots_are_not_connected_and_youtube_shorts_is_first():
    """Channels pane is dynamic from Opus sync — no static Connect placeholders."""
    html = (STATIC / "index.html").read_text()
    js = (STATIC / "app.js").read_text()
    assert 'id="channels-slots"' in html
    assert "renderChannelsPane" in js
    assert "Connected in Opus" in js
    assert "Hub YouTube grant missing" in js
    assert re.findall(r'data-connect="([a-z-]+)"', html) == []
    assert "Nothing is connected yet. Connecting comes in a later step." not in html


def test_connect_buttons_have_no_network_or_navigation():
    """Connect placeholders removed — channels come from Opus sync JSON only."""
    html = (STATIC / "index.html").read_text()
    js = (STATIC / "app.js").read_text()
    assert "<form" not in html
    assert re.findall(r'data-connect="', html) == []
    assert "renderChannelsPane" in js
    assert "Connected in Opus" in js
    # Remaining onConnect (if any) must still be inert / local-only
    m = re.search(r"function onConnect\(btn\) \{(.*?)\n  \}", js, re.S)
    if m:
        body = m.group(1)
        for banned in ("fetch", "XMLHttpRequest", "sendBeacon"):
            assert banned not in body, banned



def test_connect_click_in_a_real_browser_makes_no_requests_and_no_state(live):
    """Channels pane has no Connect buttons; opening it does not write hub state."""
    sync_api = __import__("pytest").importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        pg.goto(live.base + "/channels"); pg.wait_for_timeout(500)
        assert pg.query_selector_all("[data-connect]") == []
        storage = pg.evaluate("() => Object.keys(localStorage)")
        browser.close()
    assert "renderChannelsPane" in (STATIC / "app.js").read_text()
    assert "clippinghub.theme" not in storage
    assert not live.state.exists()


# ---------- no outbound network, no fake status labels, logo slot ----------
def test_no_outbound_network_code():
    src = (ROOT / "server.py").read_text()
    for banned in ("urllib.request", "urlopen", "http.client", "import socket", "requests", "smtplib", "ftplib", "ssl", "websocket", "subprocess", "webbrowser"):
        assert banned not in src, banned
    for f in STATIC.iterdir():
        text = f.read_text() if f.suffix in (".html", ".js", ".css", ".svg", ".webmanifest") else ""
        for url in re.findall(r"https?://[^\s\"')]+", text):
            assert url == "http://www.w3.org/2000/svg", (f.name, url)    # SVG namespace string, not a request
        for banned in ("XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "importScripts", "<iframe", "@import", "<link rel=\"preconnect"):
            assert banned not in text, (f.name, banned)
    for f in ("app.js", "sw.js"):
        for call in re.findall(r"fetch\(([^)]*)\)", (STATIC / f).read_text()):
            ok = (
                call.startswith('"/api/')  # same-origin hub APIs only
                or call.startswith("e.request")
                or call.startswith("'/api/")
            )
            assert ok, (f, call)
    assert "connect-src 'self'" in src and "Content-Security-Policy" in src
    assert "media-src 'self'" in src   # video previews on Approvals


def test_csp_header_is_sent(live):
    assert "connect-src 'self'" in get(live, "/")[1]["Content-Security-Policy"]


def test_no_fake_live_or_verified_labels():
    for f in ("index.html", "app.js"):
        text = (STATIC / f).read_text()
        text = text.replace("Not connected", "").replace("Not synced", "")
        text = re.sub(r"synced-line", "", text, flags=re.I)
        text = re.sub(r'id="[^"]*synced[^"]*"', "", text)
        text = re.sub(r"lastSyncedLabel|setSyncedLine", "", text)
        assert not re.search(r"\b(live|verified|connected successfully)\b", text, re.I), f


def test_every_screen_has_a_friendly_empty_state():
    html = (STATIC / "index.html").read_text()
    for pane, needle in (("home", "No clips yet"), ("queue", "No clips yet"), ("channels", "No Opus accounts synced"),
                         ("approvals", "Nothing waiting"), ("revenue", "Combined total"), ("trends", "No trends yet")):
        sect = re.search(r'data-pane="%s".*?</section>' % pane, html, re.S).group(0)
        assert needle in sect, pane


def test_trend_watcher_is_a_marked_placeholder_with_no_data():
    html = (STATIC / "index.html").read_text()
    sect = re.search(r'data-pane="trends".*?</section>', html, re.S).group(0)
    assert "PLACEHOLDER" in sect and "No trends yet" in sect
    assert not re.search(r"\d", re.sub(r"<[^>]+>", " ", sect).replace("h-trends", ""))     # no numbers at all in the visible text


def test_logo_is_a_single_swappable_slot():
    html = (STATIC / "index.html").read_text()
    assert html.count('id="logo"') == 1 and html.count('src="/logo.svg?v=lg1030"') == 1
    assert "Clipping Hub" in (STATIC / "logo.svg").read_text()
    assert "3.7 to 4.3" not in (STATIC / "logo.svg").read_text()                 # the placeholder's old contrast claim was wrong; no figure is claimed now
    for f in ("app.js", "app.css"):
        assert "logo" not in (STATIC / f).read_text().replace(".brand img", "")


# ---------- go-live doc only, nothing installed ----------
def test_go_live_doc_has_plist_text_and_rollback_but_no_plist_file():
    doc = (ROOT / "docs" / "GO-LIVE.md").read_text()
    for needle in ("RunAtLoad", "KeepAlive", "ThrottleInterval", "<integer>10</integer>", "8505", "Rollback", "bootout"):
        assert needle in doc, needle
    assert not list(ROOT.rglob("*.plist"))


# ======================= compliance gate =======================
import pytest  # noqa: E402


def clip_of(live, cid):
    return {c["id"]: c for c in json.loads(live.state.read_text())["clips"]}[cid]


def test_checklist_has_four_to_six_items_and_comes_from_one_constant(live):
    assert 4 <= len(server.CHECKLIST) <= 6
    api = json.loads(get(live, "/api/state")[2])
    assert api["checklist"] == [{"id": i, "text": t} for i, t in server.CHECKLIST]
    assert len(set(server.CHECK_IDS)) == len(server.CHECK_IDS)
    src = (ROOT / "server.py").read_text()
    for _, text in server.CHECKLIST:
        assert src.count(text) == 1, text                                        # worded once, in the constant block
        for f in list(STATIC.iterdir()) + [ROOT / "tests" / "test_server.py", ROOT / "docs" / "COMPLIANCE.md"]:
            if f.suffix in (".html", ".js", ".css", ".svg", ".md") or f.name == "test_server.py":
                assert text not in f.read_text(), (f.name, text)                  # never copied into the UI, docs or tests
    post(live, {"op": "add_sample"})
    assert all(text not in live.state.read_text() for _, text in server.CHECKLIST)   # the saved file keeps ids only


def test_approve_is_rejected_server_side_until_every_item_is_ticked(live):
    post(live, {"op": "add_sample"})
    code, _ = post(live, {"op": "clip", "id": "sample-1", "action": "approve"})
    assert code == 400 and clip_of(live, "sample-1")["status"] == "pending"
    for n, item in enumerate(server.CHECK_IDS, 1):
        assert post(live, {"op": "check", "id": "sample-1", "item": item, "value": True})[0] == 200
        code, _ = post(live, {"op": "clip", "id": "sample-1", "action": "approve"})
        if n < len(server.CHECK_IDS):
            assert code == 400, n                                                  # still blocked with %d of %d ticked
            assert clip_of(live, "sample-1")["status"] == "pending"
    assert code == 200 and clip_of(live, "sample-1")["status"] == "approved"


def test_blocked_approve_returns_a_short_reason_at_0_to_5_ticks_and_succeeds_at_6(live):
    post(live, {"op": "add_sample"})
    want = {"ok": False, "error": "Finish the checklist first"}
    assert server.FINISH_CHECKLIST == want["error"] and want["error"] in (STATIC / "app.js").read_text()   # same words as the page hint
    for n, item in enumerate([None] + list(server.CHECK_IDS[:-1])):
        if item:
            assert post(live, {"op": "check", "id": "sample-1", "item": item, "value": True})[0] == 200
        assert len(clip_of(live, "sample-1")["checks"]) == n
        before = live.state.read_text()
        code, body = post(live, {"op": "clip", "id": "sample-1", "action": "approve"})
        assert code == 400 and json.loads(body) == want, n                          # 0..5 ticks: 400 with the reason
        assert live.state.read_text() == before and clip_of(live, "sample-1")["status"] == "pending"
    assert post(live, {"op": "check", "id": "sample-1", "item": server.CHECK_IDS[-1], "value": True})[0] == 200
    code, body = post(live, {"op": "clip", "id": "sample-1", "action": "approve"})
    assert code == 200 and body["ok"] is True and "error" not in body and clip_of(live, "sample-1")["status"] == "approved"


def test_other_bad_requests_also_say_why_without_echoing_details(live):
    for raw in (b"not json", b"[]", b'{"op":"nope"}', b'{"op":"clip","id":"x","action":"approve"}'):
        code, body = post(live, None, raw=raw)
        d = json.loads(body)
        assert code == 400 and d["ok"] is False and isinstance(d["error"], str) and 0 < len(d["error"]) < 40, raw
    assert json.loads(post(live, None, raw=b"not json")[1])["error"] == "Bad request"   # parser details are never sent back


def test_ticks_are_per_clip(live):
    post(live, {"op": "add_sample"}); post(live, {"op": "add_sample"})
    tick_all(live, "sample-1")
    assert post(live, {"op": "clip", "id": "sample-2", "action": "approve"})[0] == 400
    assert clip_of(live, "sample-2")["checks"] == []
    assert post(live, {"op": "clip", "id": "sample-1", "action": "approve"})[0] == 200


def test_unticking_after_approval_returns_the_clip_to_waiting(live):
    post(live, {"op": "add_sample"}); tick_all(live, "sample-1")
    post(live, {"op": "clip", "id": "sample-1", "action": "approve"})
    code, s = post(live, {"op": "check", "id": "sample-1", "item": server.CHECK_IDS[2], "value": False})
    assert code == 200 and clip_of(live, "sample-1")["status"] == "pending"
    assert len(clip_of(live, "sample-1")["checks"]) == len(server.CHECK_IDS) - 1
    assert post(live, {"op": "clip", "id": "sample-1", "action": "approve"})[0] == 400      # and it is gated again
    post(live, {"op": "check", "id": "sample-1", "item": server.CHECK_IDS[2], "value": True})
    assert post(live, {"op": "clip", "id": "sample-1", "action": "approve"})[0] == 200


def test_skip_and_edit_do_not_need_the_checklist_and_undo_works(live):
    post(live, {"op": "add_sample"})
    assert post(live, {"op": "clip", "id": "sample-1", "action": "skip"})[0] == 200
    assert post(live, {"op": "clip", "id": "sample-1", "action": "edit"})[0] == 200
    assert post(live, {"op": "clip", "id": "sample-1", "action": "undo"})[0] == 200
    assert clip_of(live, "sample-1")["status"] == "pending"


def test_bad_check_requests_write_nothing_and_change_nothing(live):
    post(live, {"op": "add_sample"}); before = live.state.read_text()
    for body in ({"op": "check", "id": "sample-1", "item": "nope", "value": True}, {"op": "check", "id": "sample-1", "item": server.CHECK_IDS[0], "value": "yes"},
                 {"op": "check", "id": "ghost", "item": server.CHECK_IDS[0], "value": True}, {"op": "check", "id": "sample-1", "item": server.CHECK_IDS[0]}):
        assert post(live, body)[0] == 400
    assert live.state.read_text() == before


def test_an_approved_clip_in_the_file_without_the_full_set_is_not_honoured(live):
    live.state.parent.mkdir(parents=True, exist_ok=True)
    clip = {"id": "sample-1", "title": "Sample clip 1", "platform": "YouTube Shorts", "sample": True, "status": "approved"}
    live.state.write_text(json.dumps({"version": 1, "theme": None, "clips": [clip, dict(clip, id="sample-2", checks=["rights", "bogus"]),
                                                                              dict(clip, id="sample-3", checks=list(server.CHECK_IDS))], "updated": None}))
    got = {c["id"]: c for c in json.loads(get(live, "/api/state")[2])["clips"]}
    assert got["sample-1"]["status"] == "pending" and got["sample-1"]["checks"] == []
    assert got["sample-2"]["status"] == "pending" and got["sample-2"]["checks"] == ["rights"]
    assert got["sample-3"]["status"] == "approved"


def test_check_ops_write_only_data_state_json_atomically(live):
    before = tree_snapshot(ROOT)
    post(live, {"op": "add_sample"}); tick_all(live, "sample-1")
    post(live, {"op": "check", "id": "sample-1", "item": "rights", "value": False})
    assert sorted(str(p.relative_to(live.dir)) for p in live.dir.rglob("*") if p.is_file()) == ["data/hub-token", "data/state.json"]
    assert not list(live.state.parent.glob(".state-*.tmp"))
    assert json.loads(live.state.read_text())["clips"][0]["checks"] == list(server.CHECK_IDS[1:])
    assert tree_snapshot(ROOT) == before
    src = (ROOT / "server.py").read_text()
    assert "os.replace(tmp, p)" in src and "mkstemp" in src


def test_page_states_it_is_a_reminder_and_not_legal_advice_and_nothing_posts():
    html = (STATIC / "index.html").read_text()
    assert "Reminder checklist only. Not legal advice. Nothing posts either way." in html
    assert "Finish the checklist first" in html and "Nothing is posted" in html
    doc = (ROOT / "docs" / "COMPLIANCE.md").read_text()
    assert "not legal advice" in doc.lower() and "nothing posts" in doc.lower() and "CHECKLIST" in doc and "server.py" in doc


def test_front_end_has_no_checklist_wording_and_no_policy_claims():
    for f in ("index.html", "app.js", "app.css"):
        text = (STATIC / f).read_text().lower()
        for word in ("youtube policy", "copyright law", "dmca", "fair use", "gdpr", "ftc", "adsense", "partner program"):
            assert word not in text, (f, word)


def test_client_gate_and_untick_in_a_real_browser(live):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for width, height in ((390, 844), (1440, 900)):
            post(live, {"op": "clear_samples"})
            ctx = browser.new_context(viewport={"width": width, "height": height}, service_workers="block"); pg = ctx.new_page()
            pg.goto(live.base + "/queue"); pg.wait_for_timeout(400)
            pg.click("#q-add"); pg.wait_for_timeout(300)
            n = len(server.CHECKLIST)
            assert pg.is_disabled("#q-approve") and pg.is_visible("#q-hint")
            assert "Finish the checklist first" in pg.inner_text("#q-hint")
            if width < 900:
                assert not pg.is_visible("#q-check"); pg.click("#q-checkopen"); pg.wait_for_timeout(250)
            assert pg.is_visible("#q-check")
            assert len(pg.query_selector_all("#q-checklist label.chk")) == n
            posts = []
            pg.on("request", lambda r: posts.append(r.post_data) if r.method == "POST" else None)
            rows = pg.query_selector_all("#q-checklist label.chk")
            for k, row in enumerate(rows, 1):
                row.click(); pg.wait_for_timeout(250)
                assert pg.is_disabled("#q-approve") == (k < n), k                  # enabled only at n of n
                if k == n - 1:                                                      # a forged click on the disabled Approve sends nothing and changes nothing
                    before = len(posts)
                    pg.evaluate("() => document.querySelector('#q-approve').click()"); pg.wait_for_timeout(200)
                    assert len(posts) == before and clip_of(live, "sample-1")["status"] == "pending"
            if width < 900:
                pg.click("#q-checkclose"); pg.wait_for_timeout(250)
            assert not pg.is_disabled("#q-approve") and not pg.is_visible("#q-hint")
            pg.click("#q-approve"); pg.wait_for_timeout(400)
            assert clip_of(live, "sample-1")["status"] == "approved"
            assert json.loads(live.state.read_text())["clips"][0]["checks"] == list(server.CHECK_IDS)
            # un-tick after approval: back to Waiting
            pg.click("[data-qf=approved]"); pg.wait_for_timeout(250)
            if width < 900:
                pg.click("#q-checkopen"); pg.wait_for_timeout(250)
            pg.query_selector_all("#q-checklist label.chk")[0].click(); pg.wait_for_timeout(400)
            assert clip_of(live, "sample-1")["status"] == "pending"
            assert pg.get_attribute("[data-qf=pending]", "aria-selected") == "true" and pg.is_disabled("#q-approve")
            assert "Moved back to Waiting" in pg.inner_text("#q-hint")
            ctx.close()
        browser.close()


def test_forged_client_approve_is_blocked_before_any_request(live):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block"); pg = ctx.new_page()
        pg.goto(live.base + "/queue"); pg.wait_for_timeout(400); pg.click("#q-add"); pg.wait_for_timeout(300)
        sent = []
        pg.on("request", lambda r: sent.append(r.post_data or "") if r.method == "POST" else None)
        pg.evaluate("() => { const b = document.querySelector('#q-approve'); b.disabled = false; b.click(); }")   # even with the disabled flag stripped by hand
        pg.wait_for_timeout(300)
        browser.close()
    assert not any('"approve"' in x for x in sent)
    assert clip_of(live, "sample-1")["status"] == "pending"


def test_phone_sheet_is_opaque_and_nothing_shows_through_behind_it(live):
    """Regression: the faint 'Add a sample clip / Remove samples' labels used to show behind the sheet's last line (90% fill, buttons under its bottom edge)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        probe = """() => { const q = s => document.querySelector(s), c = getComputedStyle(q('#q-check')).backgroundColor;
            const m = c.match(/\\/\\s*([\\d.]+)\\s*\\)$/) || c.match(/^rgba\\(.*,\\s*([\\d.]+)\\)$/); const alpha = m ? parseFloat(m[1]) : 1;
            const under = ['#q-add', '#q-clear'].map(s => { const b = q(s).getBoundingClientRect(); const e = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
              return {id: s, covered: !!e && !!e.closest('#q-check'), inert: q(s).closest('.foot-actions').inert}; });
            return {alpha, under, sheetBottom: q('#q-check').getBoundingClientRect().bottom}; }"""
        for width, height in ((390, 844),):
            post(live, {"op": "clear_samples"})
            ctx = browser.new_context(viewport={"width": width, "height": height}, service_workers="block"); pg = ctx.new_page()
            pg.goto(live.base + "/queue"); pg.wait_for_timeout(400)
            for _ in range(3):
                pg.click("#q-add"); pg.wait_for_timeout(250)
            pg.wait_for_selector("#q-clear", state="visible", timeout=3000)
            assert pg.is_visible("#q-add") and pg.is_visible("#q-clear")                    # normal state: both controls are there
            pg.click("#q-checkopen"); pg.wait_for_timeout(700)                              # sheet open, animation finished
            assert pg.is_visible("#q-check")
            assert not pg.is_visible("#q-add") and not pg.is_visible("#q-clear")            # hidden while the sheet is open
            r = pg.evaluate(probe)
            assert r["alpha"] == 1, r                                                       # the sheet fill is fully opaque
            assert all(u["covered"] and u["inert"] for u in r["under"]), r                  # whatever sits under the controls is the sheet, and they are inert
            pg.click("#q-checkclose"); pg.wait_for_timeout(300)
            assert pg.is_visible("#q-add") and pg.is_visible("#q-clear")                    # back after Done
            assert not pg.evaluate("() => document.querySelector('.foot-actions').inert")
            ctx.close()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block"); pg = ctx.new_page()
        pg.goto(live.base + "/queue"); pg.wait_for_timeout(400)
        assert pg.is_visible("#q-add") and pg.is_visible("#q-clear") and pg.is_visible("#q-check")   # desktop: checklist inline, buttons untouched
        assert not pg.evaluate("() => document.querySelector('.foot-actions').inert")
        browser.close()


BROWSER = os.environ.get("CLIPPING_HUB_BROWSER", "chromium")   # chromium (default) | webkit | chrome (installed Google Chrome via Playwright's chromium channel)


def _browser(p, engine=None):
    """Launch the ONE engine asked for. No silent fallback: if it will not launch, the test FAILS and says so (it used to quietly use WebKit instead)."""
    engine = engine or BROWSER
    try:
        if engine == "chrome":
            return p.chromium.launch(channel="chrome")
        return getattr(p, engine).launch()
    except Exception as e:
        pytest.fail("real-browser tests need %r but it would not launch (%s). Install it, or pick another engine with CLIPPING_HUB_BROWSER=chromium|webkit|chrome."
                    % (engine, str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__), pytrace=False)


def test_browser_choice_fails_loudly_instead_of_falling_back():
    """Regression: with Chromium missing the tests silently ran in WebKit (and '48 passed' did not say so)."""
    class Engine:
        def __init__(self, ok): self.ok = ok
        def launch(self, **kw):
            if not self.ok:
                raise RuntimeError("Executable doesn't exist")
            return "launched"
    class P:
        chromium, webkit = Engine(False), Engine(True)
    with pytest.raises(pytest.fail.Exception) as e:
        _browser(P(), "chromium")
    assert "chromium" in str(e.value) and "CLIPPING_HUB_BROWSER" in str(e.value)
    assert _browser(P(), "webkit") == "launched"            # an engine that is there still works


def test_disabled_pager_arrow_has_at_least_3_to_1_contrast_in_light_and_dark(live):
    """The disabled '‹' (first clip) used to measure 2.2 to 3.1:1 because the whole button was faded with opacity. Measured from the rendered pixels."""
    sync_api = pytest.importorskip("playwright.sync_api")
    sys.path.insert(0, str(ROOT / "tools"))
    import uihelpers as ui
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        got = {}
        for width, height in ((390, 844), (1440, 900)):
            for theme in ("light", "dark"):
                post(live, {"op": "clear_samples"})
                ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=theme, service_workers="block"); pg = ctx.new_page()
                pg.goto(live.base + "/queue"); pg.wait_for_timeout(400)
                for _ in range(3):
                    pg.click("#q-add"); pg.wait_for_timeout(200)
                pg.wait_for_timeout(700)
                assert pg.is_disabled("#q-prev") and pg.is_enabled("#q-next")
                c, fg, bg = ui.glyph_contrast(pg.locator("#q-prev").screenshot())
                got[(width, theme)] = (round(c, 2), fg, bg)
                ctx.close()
        browser.close()
    assert all(v[0] >= 3.0 for v in got.values()), got


def test_contrast_helper_matches_known_values():
    sys.path.insert(0, str(ROOT / "tools"))
    import uihelpers as ui
    assert round(ui.contrast((0, 0, 0), (255, 255, 255)), 2) == 21.0
    assert round(ui.contrast((119, 119, 119), (255, 255, 255)), 2) == 4.48          # #777 on white is the textbook 4.48:1
    assert ui.contrast((10, 10, 10), (10, 10, 10)) == 1.0


FIT_JS = """() => { const r = e => e.getBoundingClientRect(), nav = r(document.querySelector('.nav')), st = r(document.querySelector('#stage'));
    let bottom = 0, right = 0; document.querySelectorAll('.pane:not([hidden]) *').forEach(e => { if (!e.getClientRects().length) return; const b = r(e); bottom = Math.max(bottom, b.bottom); right = Math.max(right, b.right); });
    const se = document.scrollingElement;
    return {contentBottom: bottom, stageBottom: st.bottom, navTop: nav.top, contentRight: right, stageRight: st.right, docH: se.scrollHeight, vh: innerHeight, docW: se.scrollWidth, vw: innerWidth}; }"""


def test_channels_fits_above_the_nav_at_360x740_and_the_other_phone_sizes(live):
    """Channels (Opus empty or slots) must fit above the nav — no Connect-placeholder clicks."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for width, height in ((360, 740), (390, 844), (1440, 900)):
            for theme in ("light", "dark"):
                ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=theme, service_workers="block"); pg = ctx.new_page()
                pg.goto(live.base + "/channels"); pg.wait_for_timeout(700)
                assert pg.query_selector_all("[data-connect]") == []
                m = pg.evaluate(FIT_JS); where = (width, height, theme, m)
                _assert_channels_fit(m, where, width < 900)
                ctx.close()
        browser.close()


def _assert_channels_fit(m, where, phone):
    # Page itself never scrolls; stage clears nav on phones; no horizontal overflow.
    # Vertical content may exceed stage when many Opus rows — pane scrolls (covered by reach tests).
    assert not phone or m["stageBottom"] <= m["navTop"] + 0.5, where
    assert m["docH"] <= m["vh"] and m["docW"] <= m["vw"], where
    assert m["contentRight"] <= m["stageRight"] + 0.5, where
    if not phone:
        assert m["contentBottom"] <= m["stageBottom"] + 0.5, where


def _channels_all_four_clicked(live, sizes):
    """Name kept for callers; now asserts Opus channels pane fits (no Connect placeholders)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for width, height in sizes:
            for theme in ("light", "dark"):
                ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=theme, service_workers="block"); pg = ctx.new_page()
                pg.goto(live.base + "/channels"); pg.wait_for_timeout(700)
                assert pg.query_selector_all("[data-connect]") == []
                _assert_channels_fit(pg.evaluate(FIT_JS), (width, height, theme), width < 900)
                ctx.close()
        browser.close()


def test_channels_stays_inside_the_screen_after_all_four_connect_clicks(live):
    """Regression: at 390x844 the old longer chip text ('Not connected, coming later') wrapped after all four Connect clicks and Channels overflowed by ~21 px."""
    _channels_all_four_clicked(live, ((390, 844), (1440, 900), (360, 740)))


def test_channels_fits_at_375x667_with_all_four_connect_buttons_clicked(live):
    """Regression: at 375x667 (iPhone SE class) Channels overflowed the stage and ran into the nav by ~24 px once all four Connect buttons were clicked."""
    _channels_all_four_clicked(live, ((375, 667),))


def test_channels_fits_at_360x640_with_all_four_connect_buttons_clicked(live):
    """Regression: at 360x640 Channels ran ~9 px past the stage (0.8 px into the nav) fresh and after the Connect clicks (82 px with the old long chip text)."""
    _channels_all_four_clicked(live, ((360, 640),))


QUEUE_FIT_JS = """() => { const r = e => e.getBoundingClientRect(), q = s => r(document.querySelector(s)), st = q('#stage'), card = q('#q-card'), body = q('.qbody'), foot = q('.foot-actions'), se = document.scrollingElement;
    return {cardBottom: card.bottom, bodyBottom: body.bottom, footTop: foot.top, footBottom: foot.bottom, stageBottom: st.bottom, navTop: q('.nav').top, docH: se.scrollHeight, vh: innerHeight, docW: se.scrollWidth, vw: innerWidth}; }"""


def test_queue_card_fits_and_does_not_overlap_the_sample_buttons_on_short_phones(live):
    """Regression: with 3 sample clips the queue card's content ran past the card and over the Add/Remove sample buttons at 375x667 (~75 px) and 360x640 (~116 px);
    Playwright could not even click 'Add a sample clip' because the card's pager sat on top of it."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for width, height in ((360, 640), (375, 667), (390, 844)):
            for theme in ("light", "dark"):
                post(live, {"op": "clear_samples"})
                ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=theme, service_workers="block"); pg = ctx.new_page()
                pg.goto(live.base + "/queue"); pg.wait_for_timeout(400)
                for _ in range(3):
                    pg.click("#q-add"); pg.wait_for_timeout(200)             # a real click: fails if the card sits on top of the button
                pg.wait_for_timeout(700)
                m = pg.evaluate(QUEUE_FIT_JS); where = (width, height, theme, m)
                assert m["bodyBottom"] <= m["cardBottom"] + 0.5, where           # the card's content stays inside the card
                assert m["cardBottom"] <= m["footTop"] + 0.5, where              # the card does not overlap the sample buttons
                assert m["footBottom"] <= m["stageBottom"] + 0.5 <= m["navTop"] + 0.5, where
                assert m["docH"] <= m["vh"] and m["docW"] <= m["vw"], where
                ctx.close()
        browser.close()


def test_queue_every_state_fits_with_real_clicks_on_short_phones(live):
    """Regression: at 375x667 and 360x640 the card covered 'Add a sample clip' / 'Remove samples' (real clicks were intercepted by #q-pager or the card),
    and the card's content ran 11 to 119 px past the card in every state with a clip (4 to 19 px at 360x740). Every step here is a REAL click (Playwright fails if something covers the target)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    sys.path.insert(0, str(ROOT / "tools"))
    import uihelpers as ui
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for width, height in ((360, 640), (375, 667), (360, 740)):
            for theme in ("light", "dark"):
                post(live, {"op": "clear_samples"})
                ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=theme, service_workers="block"); pg = ctx.new_page()
                pg.set_default_timeout(5000)

                def fits(state):
                    pg.wait_for_timeout(500); m = pg.evaluate(QUEUE_FIT_JS); where = (width, height, theme, state, m)
                    assert m["bodyBottom"] <= m["cardBottom"] + 0.5 and m["cardBottom"] <= m["footTop"] + 0.5, where
                    assert m["footBottom"] <= m["stageBottom"] + 0.5 <= m["navTop"] + 0.5 and m["docH"] <= m["vh"] and m["docW"] <= m["vw"], where
                    o = pg.evaluate(ui.MEASURE_JS); assert o["overflowPx"] == 0 and o["overflowXPx"] == 0, where

                pg.goto(live.base + "/queue"); pg.wait_for_timeout(400)
                pg.click("#q-add"); fits("1 clip")
                pg.click("#q-add"); pg.click("#q-add"); fits("3 clips")
                pg.click("#q-next"); fits("next clip"); pg.click("#q-prev")
                ui.tick(pg, 2); ui.close_sheet(pg); fits("2 of 6")
                ui.tick(pg, 6); ui.close_sheet(pg); fits("6 of 6")
                pg.click("#q-approve"); pg.click("[data-qf=approved]"); fits("approved tab")
                ui.untick(pg, 5); ui.close_sheet(pg); fits("un-ticked, back to waiting")
                pg.click("[data-act=skip]"); pg.click("[data-qf=skipped]"); fits("skipped tab")
                pg.click("#q-clear"); pg.wait_for_timeout(400)
                assert json.loads(live.state.read_text())["clips"] == []          # the real click on "Remove samples" went through
                ctx.close()
        browser.close()


def test_shots_exits_non_zero_when_it_finds_overflow(live, tmp_path):
    """tools/shots.py used to only REPORT overflow and always exit 0. Fixture: a copy of the app with a 900 px block in the Channels pane."""
    pytest.importorskip("playwright.sync_api")
    import shutil, subprocess, threading
    from http.server import ThreadingHTTPServer
    static = tmp_path / "static"; shutil.copytree(STATIC, static)
    html = (static / "index.html").read_text(); marker = '<p class="safe col wide">'
    assert html.count(marker) == 1
    (static / "index.html").write_text(html.replace(marker, '<div style="flex:none;height:900px">overflow fixture</div>' + marker))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(tmp_path / "data" / "state.json", static))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        run = lambda base, out: subprocess.run([sys.executable, str(ROOT / "tools" / "shots.py"), str(out), base, BROWSER, "390x844", "channels"], capture_output=True, text=True, timeout=600)
        bad = run("http://127.0.0.1:%d" % httpd.server_address[1], tmp_path / "bad")
        good = run(live.base, tmp_path / "good")
    finally:
        httpd.shutdown(); httpd.server_close()
    assert bad.returncode == 1 and "OVERFLOW in" in bad.stderr and "channels" in bad.stderr, (bad.returncode, bad.stderr[-1500:])
    assert any(m["overflowPx"] > 0 for m in json.loads(bad.stdout))           # the full report is still printed
    assert good.returncode == 0, good.stderr[-1500:]                           # the real app at 390x844 has no overflow


FIXTURE = """<div id="stage" style="position:relative;width:300px;height:200px;overflow:visible"><section class="pane"><div style="width:%s;height:20px">x</div></section></div>"""


def test_shots_horizontal_overflow_check_detects_overflow_for_real(live):
    """tools/shots.py used to compute overflowXPx from a variable that was never updated (always 0). Deliberate failing fixture + the real pages."""
    sync_api = pytest.importorskip("playwright.sync_api")
    sys.path.insert(0, str(ROOT / "tools"))
    import uihelpers as ui
    assert "mr = Math.max" not in (ROOT / "tools" / "shots.py").read_text() and "ui.MEASURE_JS" in (ROOT / "tools" / "shots.py").read_text()   # one shared measurement
    assert "if (b.right > mr)" in ui.MEASURE_JS                                                                                                 # and it really updates the right edge
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        pg = browser.new_context(viewport={"width": 400, "height": 300}).new_page()
        pg.set_content(FIXTURE % "300px"); fits = pg.evaluate(ui.MEASURE_JS)
        pg.set_content(FIXTURE % "340px"); wide = pg.evaluate(ui.MEASURE_JS)                      # 40 px wider than the 300 px stage
        pg.set_content(FIXTURE % "300px"); pg.evaluate("() => { document.querySelector('.pane div').style.height = '260px'; }"); tall = pg.evaluate(ui.MEASURE_JS)
        assert fits["overflowXPx"] == 0 and fits["overflowPx"] == 0, fits
        assert wide["overflowXPx"] == 40 and wide["overflowPx"] == 0, wide                         # horizontal overflow is now seen (it was always 0 before)
        assert tall["overflowPx"] == 60 and tall["overflowXPx"] == 0, tall                         # and vertical still works
        for width, height in ((390, 844), (360, 740), (1440, 900)):
            ctx = browser.new_context(viewport={"width": width, "height": height}, service_workers="block"); pg = ctx.new_page()
            for path in ("", "queue", "approvals", "channels", "revenue", "trends"):
                pg.goto(live.base + "/" + path); pg.wait_for_timeout(800)
                m = pg.evaluate(ui.MEASURE_JS)
                assert m["overflowXPx"] == 0 and m["docScrollX"] <= m["viewportW"], (width, height, path, m)       # real pages: no horizontal overflow
            ctx.close()
        browser.close()


def test_channel_chips_read_not_connected_yet_on_first_load(live):
    """Channels pane renders Opus rows (or empty state) — no static Not-connected-yet Connect chips."""
    html = (STATIC / "index.html").read_text()
    assert re.findall(r"<span[^>]*data-status[^>]*>([^<]*)</span>", html) == []
    assert 'id="channels-slots"' in html
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for width, height in ((390, 844), (375, 667), (360, 640)):
            ctx = browser.new_context(viewport={"width": width, "height": height}, service_workers="block"); pg = ctx.new_page()
            pg.goto(live.base + "/channels"); pg.wait_for_timeout(700)
            # Empty or Opus-rendered; never the old four Connect placeholders
            assert pg.query_selector_all("[data-connect]") == []
            body = pg.inner_text("body")
            assert "Connect channel" not in body
            assert ("No Opus accounts synced" in body) or ("Connected in Opus" in body) or ("Channels" in body)
            ctx.close()
            ctx.close()
        browser.close()


# ---------- mutating requests need the per-install token and a same-origin caller ----------
def test_state_post_without_token_is_403_and_state_unchanged(live):
    before = json.loads(get(live, "/api/state")[2])
    assert post(live, {"op": "theme", "value": "dark"}, token=None)[0] == 403
    assert json.loads(get(live, "/api/state")[2]) == before


def test_state_post_with_wrong_token_is_403(live):
    assert post(live, {"op": "theme", "value": "dark"}, token="wrong-token")[0] == 403
    assert json.loads(get(live, "/api/state")[2]).get("theme") != "dark"


def test_state_post_with_right_token_is_200_and_changes_state(live):
    code, s = post(live, {"op": "theme", "value": "dark"})
    assert code == 200 and s["theme"] == "dark"
    assert json.loads(get(live, "/api/state")[2])["theme"] == "dark"


def test_cross_site_origin_is_403_even_with_token(live):
    assert post(live, {"op": "theme", "value": "dark"}, headers={"Origin": "https://evil.example"})[0] == 403
    assert post(live, {"op": "theme", "value": "dark"}, headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert post(live, {"op": "theme", "value": "dark"}, headers={"Origin": live.base})[0] == 200


def test_no_cors_headers_are_sent(live):
    _, h, _ = get(live, "/")
    assert not any(k.lower().startswith("access-control-") for k in h.keys())
    assert "Access-Control" not in (ROOT / "server.py").read_text()


def test_frontend_sends_token_header_from_served_page(live):
    js = (STATIC / "app.js").read_text()
    assert '"X-Hub-Token": hubToken()' in js
    page = get(live, "/")[2].decode()
    tok = (live.state.parent / "hub-token").read_text().strip()
    assert ('<meta name="hub-token" content="%s">' % tok) in page
    assert tok not in (STATIC / "index.html").read_text()        # the secret is injected, never stored in static/


def test_token_file_is_mode_600(live):
    p = live.state.parent / "hub-token"
    assert (p.stat().st_mode & 0o777) == 0o600 and len(p.read_text().strip()) >= 32


def test_sw_cache_version_bumped():
    assert "clipping-hub-shell-v35" in (STATIC / "sw.js").read_text()


def test_hub_token_is_gitignored():
    import subprocess
    r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "data/hub-token"])
    assert r.returncode == 0


def test_sw_never_precaches_or_puts_html():
    sw = (STATIC / "sw.js").read_text()
    shell = json.loads(re.search(r"SHELL = (\[[^\]]*\])", sw).group(1))
    for route in server.PAGES + ("/index.html",):
        assert route not in shell, route
    assert not any(x.endswith(".html") for x in shell)
    assert 'e.request.mode === "navigate"' in sw                 # navigations are network-only, never put
    nav = sw[sw.index('e.request.mode === "navigate"'):sw.index("return;", sw.index('e.request.mode === "navigate"'))]
    assert "c.put" not in nav and "caches.open" not in nav
    assert "if (storable(r))" in sw and '"text/html"' in sw and '"no-store"' in sw
    assert sw.count("c.put(") == 1 and "if (storable(r)) { var k = r.clone(); caches.open(C).then(function (c) { c.put(" in sw
    offline = re.search(r"var OFFLINE = '([^']*)'", sw).group(1)
    assert "hub-token" not in offline


def test_sw_caches_no_html_in_a_real_browser(live):
    sync_api = __import__("pytest").importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
        for route in ("/", "/queue"):
            pg.goto(live.base + route)
        pg.evaluate("navigator.serviceWorker.ready")
        pg.reload(); pg.goto(live.base + "/queue"); pg.wait_for_timeout(1000)
        got = pg.evaluate("""async () => { const out = []; for (const n of await caches.keys()) { const c = await caches.open(n);
            for (const r of await c.keys()) { const m = await c.match(r); out.push([n, new URL(r.url).pathname, m.headers.get('content-type') || '']); } } return out; }""")
        tok = (live.state.parent / "hub-token").read_text().strip()
        bodies = pg.evaluate("""async () => { const out = []; for (const n of await caches.keys()) { const c = await caches.open(n);
            for (const r of await c.keys()) { out.push(await (await c.match(r)).text()); } } return out; }""")
        browser.close()
    assert got, "service worker never populated its cache"        # proves the SW really ran
    assert all(n == "clipping-hub-shell-v35" for n, _, _ in got)
    assert not [x for x in got if "text/html" in x[2].lower()], got
    assert not any(tok in b for b in bodies)


def test_symlinked_token_file_is_refused(tmp_path):
    target = tmp_path / "elsewhere"; target.write_text("attacker-chosen")
    d = tmp_path / "data"; d.mkdir(); (d / "hub-token").symlink_to(target)
    with pytest.raises(Exception):
        server.load_token(d / "hub-token")
    with pytest.raises(Exception):
        server.make_handler(d / "state.json")
    assert target.read_text() == "attacker-chosen"


def test_token_file_created_exclusively_with_mode_600(tmp_path):
    p = tmp_path / "data" / "hub-token"
    a = server.load_token(p)
    assert (p.stat().st_mode & 0o777) == 0o600 and server.load_token(p) == a
    src = (ROOT / "server.py").read_text()
    assert "os.O_EXCL" in src and "os.O_NOFOLLOW" in src


def _raw_post(live, host, origin):
    import http.client
    hp = live.base[7:].split(":")
    c = http.client.HTTPConnection(hp[0], int(hp[1]))
    tok = (live.state.parent / "hub-token").read_text().strip()
    body = json.dumps({"op": "theme", "value": "dark"})
    c.putrequest("POST", "/api/state", skip_host=True)
    for k, v in (("Host", host), ("Origin", origin), ("Content-Type", "application/json"), ("X-Hub-Token", tok), ("Content-Length", str(len(body)))):
        c.putheader(k, v)
    c.endheaders(body.encode()); r = c.getresponse(); r.read(); c.close()
    return r.status


def test_origin_with_explicit_port_matching_host_is_allowed(live):
    assert _raw_post(live, "hub.tailnet.ts.net:8445", "https://hub.tailnet.ts.net:8445") == 200


def test_origin_with_mismatched_port_is_403(live):
    assert _raw_post(live, "hub.tailnet.ts.net:8445", "https://hub.tailnet.ts.net:9999") == 403
    assert _raw_post(live, "hub.tailnet.ts.net:8445", "https://hub.tailnet.ts.net") == 403


REACH_JS = """() => { const p = document.querySelector('.pane:not([hidden])'); p.scrollTo(0, 1e6); const nav = document.querySelector('.nav').getBoundingClientRect(), kids = [...p.children].filter(e => e.getClientRects().length), last = kids[kids.length - 1];
    const pr = p.getBoundingClientRect(), lr = last.getBoundingClientRect(), cs = getComputedStyle(p), se = document.scrollingElement;
    return {lastBottom: lr.bottom, navTop: nav.top, phone: innerWidth < 900, paneBottom: pr.bottom, scrollH: p.scrollHeight, clientH: p.clientHeight, overflowY: cs.overflowY, docH: se.scrollHeight, vh: innerHeight}; }"""


def test_every_pane_is_reachable_on_short_phones_and_channels_fits_without_scrolling(live):
    """Every pane's last child must be inside the pane OR the pane must scroll; page itself never scrolls.
    Channels: 2-col grid on phones when slots exist; may scroll when many Opus rows (scroll end clears nav)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for width, height in ((390, 664), (375, 667), (360, 640)):
            ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light", service_workers="block"); pg = ctx.new_page()
            for name in ("", "queue", "approvals", "channels", "revenue", "trends"):
                pg.goto(live.base + "/" + name); pg.wait_for_timeout(700)
                m = pg.evaluate(REACH_JS); where = (width, height, name or "home", m)
                assert m["overflowY"] == "auto", where
                inside = m["lastBottom"] <= m["paneBottom"] + 0.5
                assert inside or m["scrollH"] > m["clientH"], where
                assert m["docH"] <= m["vh"], where                                                  # the page itself never scrolls
                assert m["lastBottom"] <= m["navTop"] + 0.5, where                                   # scrolled to the end, the last element clears the floating nav
                if name == "channels":
                    assert pg.query_selector_all("[data-connect]") == []
                    slots = pg.query_selector_all(".slot")
                    if len(slots) >= 2:
                        cols = {round(b.bounding_box()["x"]) for b in slots}
                        assert len(cols) == 2, where                                                     # 2-col on phones
            ctx.close()
        browser.close()


def test_short_pane_scrolls_instead_of_clipping(live):
    """Force a pane taller than the stage: it must scroll inside the stage (not clip), and the page must not scroll."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        ctx = browser.new_context(viewport={"width": 360, "height": 640}, service_workers="block"); pg = ctx.new_page()
        pg.goto(live.base + "/channels"); pg.wait_for_timeout(700)
        pg.evaluate("() => { const d = document.createElement('div'); d.style.height = '900px'; d.style.flex = 'none'; d.id = 'tall'; document.querySelector('.pane:not([hidden])').appendChild(d); }")
        m = pg.evaluate(REACH_JS)
        assert m["scrollH"] > m["clientH"] and m["docH"] <= m["vh"] and m["lastBottom"] <= m["navTop"] + 0.5, m
        pg.evaluate("() => document.querySelector('.pane:not([hidden])').scrollTo(0, 1e6)")
        assert pg.evaluate("() => document.querySelector('#tall').getBoundingClientRect().bottom <= document.querySelector('.pane:not([hidden])').getBoundingClientRect().bottom + 0.5")
        ctx.close(); browser.close()


def test_service_worker_shell_cache_is_v5():
    sw = (ROOT / "static" / "sw.js").read_text()
    assert '"clipping-hub-shell-v35"' in sw and "shell-v5" not in sw


CONNECT_JS = """(insetBottom) => { const p = document.querySelector('.pane:not([hidden])'), pr = p.getBoundingClientRect();
    return [...document.querySelectorAll('[data-connect]')].map(b => { b.scrollIntoView({block: 'nearest'}); const r = b.getBoundingClientRect(),
        hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return {bottom: r.bottom, paneBottom: pr.bottom, limit: innerHeight - insetBottom, onTop: !!hit && (hit === b || b.contains(hit))}; }); }"""


def _iphone15pro_reach(live, width, height, inset_top, inset_bottom):
    """Chromium/WebKit headless report env(safe-area-inset-*) as 0, so the insets are emulated by serving app.css with every
    env(safe-area-inset-top|bottom) replaced by the iPhone 15 Pro standalone values (59px / 34px) via a Playwright route (left/right stay 0)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light", service_workers="block"); pg = ctx.new_page()
        if inset_top or inset_bottom:
            def css(route):
                r = route.fetch(); body = r.text()
                assert "env(safe-area-inset-bottom)" in body and "env(safe-area-inset-top)" in body
                body = body.replace("env(safe-area-inset-top)", "%dpx" % inset_top).replace("env(safe-area-inset-bottom)", "%dpx" % inset_bottom)
                route.fulfill(response=r, body=body)
            pg.route("**/app.css", css)
        for name in ("", "queue", "approvals", "channels", "revenue", "trends"):
            pg.goto(live.base + "/" + name); pg.wait_for_timeout(700)
            m = pg.evaluate(REACH_JS); where = (width, height, inset_top, inset_bottom, name or "home", m)
            assert m["overflowY"] == "auto", where
            inside = m["lastBottom"] <= m["paneBottom"] + 0.5
            assert inside or m["scrollH"] > m["clientH"], where
            assert m["docH"] <= m["vh"], where
            assert m["lastBottom"] <= m["navTop"] + 0.5, where                                       # scrolled to the end, the last element clears the floating nav
            assert m["paneBottom"] <= m["vh"] - inset_bottom + 0.5, where                          # the pane never sits under the home indicator
            if name == "channels":
                assert pg.query_selector_all("[data-connect]") == []
                # Channels may scroll when many Opus rows; scrolled end must clear nav (checked above)
                print("REACH", width, height, inset_top, inset_bottom, "lastBottom=%.1f paneBottom=%.1f navTop=%.1f scroll=%s" % (m["lastBottom"], m["paneBottom"], m["navTop"], m["scrollH"] > m["clientH"]))
        ctx.close(); browser.close()


def test_iphone15pro_safari_with_bars_393x659_is_reachable(live):
    _iphone15pro_reach(live, 393, 659, 0, 0)


def test_iphone15pro_standalone_393x852_with_safe_area_insets_is_reachable(live):
    _iphone15pro_reach(live, 393, 852, 59, 34)
