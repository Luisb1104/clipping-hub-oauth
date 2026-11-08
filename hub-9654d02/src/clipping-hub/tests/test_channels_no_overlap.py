"""Channels cards: name / platform / badges / link must not overlap at key viewports."""
from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import server

ROOT = Path(__file__).resolve().parents[1]
LIVE_CHANNELS = Path("/workspace/api-channels-live.json")
SIZES = [(1024, 700), (1280, 800), (393, 852)]

OVERLAP_JS = """() => {
  function box(el) {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { t: r.top, l: r.left, b: r.bottom, r: r.right, w: r.width, h: r.height };
  }
  function overlaps(a, b) {
    if (!a || !b || a.w < 1 || a.h < 1 || b.w < 1 || b.h < 1) return false;
    return !(a.r <= b.l || b.r <= a.l || a.b <= b.t || b.b <= a.t);
  }
  const cards = [...document.querySelectorAll('.channels-slot')];
  const report = [];
  for (const card of cards) {
    const nm = box(card.querySelector('.nm'));
    const plat = box(card.querySelector('.plat'));
    const chips = box(card.querySelector('.chips'));
    const link = box(card.querySelector('.chan-link'));
    const pairs = [
      ['nm', nm, 'plat', plat],
      ['nm', nm, 'chips', chips],
      ['nm', nm, 'link', link],
      ['plat', plat, 'chips', chips],
      ['plat', plat, 'link', link],
      ['chips', chips, 'link', link],
    ];
    const bad = [];
    for (const [an, a, bn, b] of pairs) {
      if (overlaps(a, b)) bad.push(an + '+' + bn);
    }
    // Also ensure card itself has min-width 0 / no overflow past parent
    const cr = card.getBoundingClientRect();
    const parent = card.parentElement.getBoundingClientRect();
    report.push({
      name: (card.querySelector('.nm') || {}).textContent || '',
      bad,
      nm, plat, chips, link,
      cardW: cr.width, parentW: parent.width,
      overflowsParent: cr.right > parent.right + 0.5 || cr.left < parent.left - 0.5,
    });
  }
  return { n: cards.length, report };
}"""


def _write_channels(root: Path, payload) -> None:
    d = root / "channels"
    d.mkdir(parents=True, exist_ok=True)
    (d / "channels.json").write_text(json.dumps(payload))


@pytest.fixture()
def channels_server(tmp_path, monkeypatch):
    if not LIVE_CHANNELS.exists():
        pytest.skip("live Mac /api/channels fixture missing")
    live = json.loads(LIVE_CHANNELS.read_text())
    assert live.get("channels") and len(live["channels"]) >= 5
    _write_channels(tmp_path / "clipper", live)
    import clipper_data as cd
    monkeypatch.setattr(cd, "CLIPPER_ROOT", tmp_path / "clipper")
    monkeypatch.setattr(cd, "CHANNELS_DIR", tmp_path / "clipper" / "channels")
    monkeypatch.setenv("CLIPPING_HUB_CLIPPER_ROOT", str(tmp_path / "clipper"))
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"version": 1, "theme": "system", "clips": [], "updated": "", "checklist": []}))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, ROOT / "static"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, live
    httpd.shutdown()


@pytest.mark.parametrize("vw,vh", SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
def test_channels_cards_no_bbox_overlap(channels_server, vw, vh):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    base, live = channels_server
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": vw, "height": vh})
        page.goto(base + "/channels", wait_until="networkidle")
        page.wait_for_selector(".channels-slot")
        # wait for fetch adopt
        page.wait_for_function("() => document.querySelectorAll('.channels-slot').length >= 5")
        data = page.evaluate(OVERLAP_JS)
        browser.close()
    assert data["n"] == len(live["channels"]), data
    for row in data["report"]:
        assert row["bad"] == [], (vw, vh, row)
        assert row["overflowsParent"] is False, (vw, vh, row)
        assert row["nm"] and row["plat"] and row["chips"] and row["link"]


def test_channels_markup_is_block_column():
    js = (ROOT / "static/app.js").read_text()
    css = (ROOT / "static/app.css").read_text()
    assert 'class="chan-link"' in js
    assert "'<div class=\"nm\">' + name + \"</div>\"" in js or '<div class="nm">' in js
    assert "flex-direction:column" in css
    assert "overflow-wrap:anywhere" in css
    assert ".channels-slot .chan-link" in css
