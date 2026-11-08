#!/usr/bin/env python3
"""Screenshot + one-screen check for every screen (390x844 and 1440x900, light and dark) against an ALREADY RUNNING local server.
Usage: python tools/shots.py OUTDIR [BASE_URL] [chromium|webkit|chrome] [SIZES] [ONLY]
SIZES: comma list of WxH (default 390x844,1440x900; 390 is tagged "phone", 1440 "desktop", anything else "phone-WxH" or "desktop-WxH" by width).
ONLY: comma list of screen names to save (default all), e.g. channels. Only talks to the base URL (127.0.0.1). Prints a JSON overflow report (vertical AND horizontal) and exits 1 if any shot overflows."""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
import uihelpers as ui

OUT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8505"
ENGINE = sys.argv[3] if len(sys.argv) > 3 else "chromium"
SIZES = [tuple(int(v) for v in x.split("x")) for x in (sys.argv[4] if len(sys.argv) > 4 else "390x844,1440x900").split(",")]
ONLY = [x for x in (sys.argv[5].split(",") if len(sys.argv) > 5 else []) if x]
MEASURE = ui.MEASURE_JS
assert BASE.startswith("http://127.0.0.1:") or BASE.startswith("http://localhost:"), "local only"
os.makedirs(OUT, exist_ok=True)
SCREENS = [("home", ""), ("queue", "queue"), ("approvals", "approvals"), ("channels", "channels"), ("revenue", "revenue"), ("trends", "trends")]
report = []
with sync_playwright() as p:
    b = ui.launch(p, ENGINE)
    for vw, vh in SIZES:
        kind = "phone" if vw < 900 else "desktop"
        tag = kind if (vw, vh) in ((390, 844), (1440, 900)) else "%s-%dx%d" % (kind, vw, vh)
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": vw, "height": vh}, color_scheme=theme, service_workers="block")
            pg = ctx.new_page()

            def shot(name, extra=None):
                if ONLY and name not in ONLY:
                    return
                pg.wait_for_timeout(700)
                m = pg.evaluate(MEASURE); m.update(screen=name, size=tag, theme=theme)
                pg.screenshot(path="%s/%s-%s-%s.png" % (OUT, tag, theme, name)); report.append(m)

            for name, path in SCREENS:
                pg.goto(BASE + "/" + path); shot(name)
            # queue with sample clips: waiting view, then approved view
            pg.goto(BASE + "/queue"); pg.wait_for_timeout(400)
            if pg.is_visible("#q-clear"):
                pg.click("#q-clear"); pg.wait_for_timeout(300)        # always start from an empty queue
            for _ in range(3):
                pg.click("#q-add"); pg.wait_for_timeout(150)
            shot("queue-with-samples")
            ui.tick(pg, 6); ui.close_sheet(pg); pg.click("[data-act=approve]"); pg.wait_for_timeout(300); pg.click("[data-qf=approved]"); shot("queue-approved-tab")
            pg.click("#q-clear"); pg.wait_for_timeout(300)
            # Connect clicks show the label only
            pg.goto(BASE + "/channels")
            for btn in pg.query_selector_all("[data-connect]"):
                btn.click()                                       # all four, the worst case for the chip text
            shot("channels-after-connect-click")
            ctx.close()
    b.close()
print(json.dumps(report, indent=1))
ui.exit_on_overflow(report)          # exit 1 if any shot overflowed (the report above still lists every shot)
