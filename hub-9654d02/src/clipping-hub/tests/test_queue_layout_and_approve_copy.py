"""Queue sample card never overlaps the tabs or the Add/Remove buttons (real clicks), and Approve copy is truthful per clip."""
import json
import pytest
from tests.test_server import post, _browser

SIZES = [(1024, 700, 0, 0), (1280, 800, 0, 0), (393, 852, 59, 34), (360, 640, 0, 0)]   # 393x852 = iPhone 15 Pro standalone insets
BOXES = """() => { const r = s => { const e = document.querySelector(s); return e && e.getClientRects().length ? e.getBoundingClientRect() : null; };
  const add = r('#q-add'), clr = r('#q-clear'), card = r('#q-card'), tabs = r('.qhead [role=tablist]') || r('[data-qf=pending]');
  const hit = b => { if (!b) return true; const e = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2); return !!e && !!e.closest('.foot-actions'); };
  const kids = [...document.querySelectorAll('#q-card .qbody > *')].filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
    .map(e => e.getBoundingClientRect());
  return {add, clr, card, tabs, addHit: hit(add), clrHit: hit(clr), docH: document.scrollingElement.scrollHeight, vh: innerHeight,
          kidsTop: Math.min(...kids.map(k => k.top)), kidsBottom: Math.max(...kids.map(k => k.bottom)),
          bodyBox: (document.querySelector('#q-card .qbody') || document.body).getBoundingClientRect()}; }"""


def _ov(a, b):
    return bool(a and b and not (a["right"] <= b["left"] or b["right"] <= a["left"] or a["bottom"] <= b["top"] or b["bottom"] <= a["top"]))


def _page(browser, live, w, h, top, bot):
    ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block"); pg = ctx.new_page(); pg.set_default_timeout(4000)
    if top or bot:
        def css(route):
            r = route.fetch(); body = r.text().replace("env(safe-area-inset-top)", "%dpx" % top).replace("env(safe-area-inset-bottom)", "%dpx" % bot)
            route.fulfill(response=r, body=body)
        pg.route("**/app.css", css)
    return ctx, pg


@pytest.mark.parametrize("w,h,top,bot", SIZES, ids=["%dx%d%s" % (s[0], s[1], "-standalone" if s[2] else "") for s in SIZES])
def test_queue_samples_1_to_3_real_clicks_no_overlap(live, w, h, top, bot):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        for n in (1, 2, 3):
            post(live, {"op": "clear_samples"})                                   # reset between runs
            ctx, pg = _page(browser, live, w, h, top, bot)
            pg.goto(live.base + "/queue"); pg.wait_for_timeout(400)
            for _ in range(n):
                pg.click("#q-add"); pg.wait_for_timeout(200)                     # real click: fails if anything covers it
            pg.wait_for_timeout(400)
            m = pg.evaluate(BOXES); where = (w, h, n, m)
            assert len(json.loads(live.state.read_text())["clips"]) == n, where
            assert m["addHit"] and m["clrHit"], where
            for b in ("add", "clr"):
                assert not _ov(m["card"], m[b]), (b, where)
            assert not _ov(m["card"], m["tabs"]), where
            bb = m["bodyBox"]
            assert m["kidsTop"] >= m["card"]["top"] - 0.5 or bb["top"] >= m["card"]["top"] - 0.5, where   # nothing over the tabs
            assert bb["bottom"] <= m["card"]["bottom"] + 0.5, where             # body clipped/scrolls inside the card
            assert m["docH"] <= m["vh"], where
            pg.click("#q-clear"); pg.wait_for_timeout(300)                       # real click on Remove samples
            assert json.loads(live.state.read_text())["clips"] == [], where
            ctx.close()
        browser.close()


@pytest.mark.parametrize("flag", ["1", "0"])
def test_approve_copy_is_truthful_per_clip(live, monkeypatch, flag):
    import server
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", flag)
    assert server.payload(server.default_state())["label_step_enabled"] is (flag == "1")
    sync_api = pytest.importorskip("playwright.sync_api")
    ap = live.state.parent / "approvals.json"; ap.parent.mkdir(parents=True, exist_ok=True)
    base = {"video": "", "caption": "c", "platforms": ["youtube"], "status": "pending"}
    ap.write_text(json.dumps({"version": 1, "items": [dict(base, id="ai-on", caption="AI clip", ai_disclosure=True),
                                                      dict(base, id="ai-off", caption="Plain clip", ai_disclosure=False, is_ad=True)]}))
    with sync_api.sync_playwright() as p:
        browser = _browser(p); ctx = browser.new_context(viewport={"width": 1280, "height": 800}, service_workers="block"); pg = ctx.new_page()
        pg.goto(live.base + "/approvals"); pg.wait_for_timeout(700)
        on = pg.inner_text('#approvals-pane [data-appr-id="ai-on"] .appr-what, [data-pane=approvals] [data-appr-id="ai-on"] .appr-what')
        off = pg.inner_text('[data-pane=approvals] [data-appr-id="ai-off"] .appr-what')
        stamp = pg.inner_text("#shell-stamp")
        browser.close()
    if flag == "1":
        assert on.startswith("Approve = uploads PRIVATE to MAIN") and "otherwise waits for the grant" in on, on
    else:
        assert on == "Approve = marks PRIVATE + label-pending · no upload (label step off)", on
    assert off == "Approve = marks ready · you post manually", off
    assert "APPROVE ACTIONS SHOWN PER CLIP" in stamp and "YOU POST MANUALLY" not in stamp, stamp
