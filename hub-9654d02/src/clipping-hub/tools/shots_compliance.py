#!/usr/bin/env python3
"""Compliance-gate screenshots against an ALREADY RUNNING local server (use a temp state file).
Usage: python tools/shots_compliance.py OUTDIR [BASE_URL] [chromium|webkit|chrome] [ONLY], where ONLY is an optional comma list of screen names to save (default: all). Prints a JSON overflow report (page overflow and sheet-internal scroll) and exits 1 if any shot overflows or the sheet scrolls inside."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
import uihelpers as ui

OUT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8505"
ENGINE = sys.argv[3] if len(sys.argv) > 3 else "chromium"
ONLY = [x for x in (sys.argv[4].split(",") if len(sys.argv) > 4 else []) if x]    # e.g. queue-unfinished-sheet-open,queue-complete-sheet-open
assert BASE.startswith("http://127.0.0.1:") or BASE.startswith("http://localhost:"), "local only"
os.makedirs(OUT, exist_ok=True)
MEASURE = """() => {
  const st = document.querySelector('#stage').getBoundingClientRect(); let mx = 0, mr = 0, hit = '';
  document.querySelector('.pane:not([hidden])').querySelectorAll('*').forEach(e => {
    if (!e.getClientRects().length) return; const r = e.getBoundingClientRect(); mr = Math.max(mr, r.right);
    if (r.bottom > mx) { mx = r.bottom; hit = e.tagName + '.' + (typeof e.className === 'string' ? e.className : '') + '#' + e.id; } });
  const sh = document.querySelector('#q-check'); const shown = sh && sh.getClientRects().length > 0;
  return {overflowPx: Math.max(0, Math.round(mx - st.bottom)), overflowXPx: Math.max(0, Math.round(mr - st.right - 0.5)), docScroll: document.scrollingElement.scrollHeight, viewport: innerHeight,
          checklistVisible: !!shown, checklistInnerScrollPx: shown ? Math.max(0, sh.scrollHeight - sh.clientHeight) : 0, lowest: hit,
          approveDisabled: document.querySelector('#q-approve') ? document.querySelector('#q-approve').disabled : null,
          progress: document.querySelector('#q-check-count').textContent};
}"""
report = []
with sync_playwright() as p:
    b = ui.launch(p, ENGINE)
    for vw, vh, tag in ((390, 844, "phone"), (1440, 900, "desktop")):
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": vw, "height": vh}, color_scheme=theme, service_workers="block"); pg = ctx.new_page()

            def shot(name):
                if ONLY and name not in ONLY:
                    return                                       # re-shoot only the named screens; the other steps still run to reach them
                pg.wait_for_timeout(600)
                m = pg.evaluate(MEASURE); m.update(screen=name, size=tag, theme=theme); report.append(m)
                pg.screenshot(path="%s/%s-%s-%s.png" % (OUT, tag, theme, name))

            pg.goto(BASE + "/queue"); pg.wait_for_timeout(400)
            if pg.is_visible("#q-clear"):
                pg.click("#q-clear"); pg.wait_for_timeout(300)        # start every run from an empty queue
            for _ in range(3):                                   # 3 clips = worst case (pager shown)
                pg.click("#q-add"); pg.wait_for_timeout(150)
            ui.tick(pg, 2); ui.close_sheet(pg)
            shot("queue-unfinished")                              # 2 of 6 ticked, Approve disabled
            if tag == "phone":
                ui.open_sheet(pg); shot("queue-unfinished-sheet-open"); ui.close_sheet(pg)
            ui.tick(pg, 6); ui.close_sheet(pg)
            shot("queue-complete")                                # 6 of 6 ticked, Approve enabled
            if tag == "phone":
                ui.open_sheet(pg); shot("queue-complete-sheet-open"); ui.close_sheet(pg)
            pg.click("#q-approve"); pg.wait_for_timeout(400); pg.click("[data-qf=approved]")
            shot("queue-approved-tab")
            ui.untick(pg, 5); ui.close_sheet(pg)                  # un-tick after approval: clip returns to Waiting
            shot("queue-unticked-back-to-waiting")
            ctx.close()
    b.close()
print(json.dumps(report, indent=1))
ui.exit_on_overflow(report)          # exit 1 if any shot overflowed (the report above still lists every shot)
