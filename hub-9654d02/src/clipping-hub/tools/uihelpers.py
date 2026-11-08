"""Shared Playwright helpers for the Clipping Hub tools and tests (local pages only)."""


def open_sheet(pg):
    """On a phone-width page the checklist is a bottom sheet: open it. No-op on desktop (inline)."""
    if pg.is_visible("#q-checkopen") and not pg.is_visible("#q-check"):
        pg.click("#q-checkopen"); pg.wait_for_timeout(250)


def close_sheet(pg):
    if pg.is_visible("#q-checkclose"):
        pg.click("#q-checkclose"); pg.wait_for_timeout(250)


def tick(pg, n, only_first=None):
    """Tick the first `n` checklist items by tapping their rows (opens the sheet if needed)."""
    open_sheet(pg)
    items = pg.query_selector_all("#q-checklist label.chk")
    for lab in items[:n]:
        if not lab.query_selector("input").is_checked():
            lab.click(); pg.wait_for_timeout(200)


def untick(pg, index):
    open_sheet(pg)
    pg.query_selector_all("#q-checklist label.chk")[index].click(); pg.wait_for_timeout(250)


# ---- contrast helpers (stdlib only: no Pillow needed) ----
def png_pixels(data):
    """Decode an 8-bit RGB/RGBA non-interlaced PNG (what Playwright screenshots are) to (w, h, rows of (r, g, b) tuples)."""
    import struct, zlib
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8]); body = data[pos + 8:pos + 8 + n]; pos += 12 + n
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body); assert depth == 8 and ctype in (2, 6) and inter == 0
        elif typ == b"IDAT":
            idat += body
    bpp = 3 if ctype == 2 else 4; stride = w * bpp; raw = zlib.decompress(idat); rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]; line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)]); prev = line
    return w, h, rows


def luminance(rgb):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def glyph_contrast(png_bytes):
    """Contrast of the strongest glyph pixel against the dominant (background) colour of a small element screenshot."""
    from collections import Counter
    w, h, rows = png_pixels(png_bytes)
    bg = Counter(p for r in rows for p in r).most_common(1)[0][0]
    fg = max((p for r in rows for p in r), key=lambda p: contrast(p, bg))
    return contrast(fg, bg), fg, bg


# One-screen measurement used by tools/shots.py and the tests: how far the visible pane's content runs past the stage (down and to the right).
MEASURE_JS = """() => {
  const st = document.querySelector('#stage').getBoundingClientRect(); let mx = 0, mr = 0, hit = '', hitx = '';
  document.querySelector('.pane:not([hidden])').querySelectorAll('*').forEach(e => {
    if (!e.getClientRects().length) return; const b = e.getBoundingClientRect(), id = e.tagName + '.' + (typeof e.className === 'string' ? e.className : '') + '#' + e.id;
    if (b.bottom > mx) { mx = b.bottom; hit = id; }
    if (b.right > mr) { mr = b.right; hitx = id; } });
  const se = document.scrollingElement;
  return {contentBottom: Math.round(mx), stageBottom: Math.round(st.bottom), docScroll: se.scrollHeight, viewport: innerHeight, overflowPx: Math.max(0, Math.round(mx - st.bottom)),
          contentRight: Math.round(mr), stageRight: Math.round(st.right), overflowXPx: Math.max(0, Math.round(mr - st.right - 0.5)), docScrollX: se.scrollWidth, viewportW: innerWidth, lowest: hit, rightmost: hitx};
}"""


def launch(p, engine):
    """chromium | webkit | firefox, or chrome (an installed Google Chrome through Playwright's chromium channel)."""
    return p.chromium.launch(channel="chrome") if engine == "chrome" else getattr(p, engine).launch()


def overflow_failures(report):
    """Shots whose visible pane runs past the stage (down or right), whose page scrolls, or whose checklist sheet scrolls inside."""
    return [m for m in report if m.get("overflowPx", 0) > 0 or m.get("overflowXPx", 0) > 0 or m.get("docScroll", 0) > m.get("viewport", float("inf"))
            or m.get("docScrollX", 0) > m.get("viewportW", float("inf")) or m.get("checklistInnerScrollPx", 0) > 0]


def exit_on_overflow(report):
    """Called after the JSON report is printed: exit 1 (and say which shots) if anything overflowed, so a run can no longer pass with overflow in it."""
    import sys
    bad = overflow_failures(report)
    if bad:
        print("OVERFLOW in %d of %d shots: %s" % (len(bad), len(report), ", ".join("%s/%s/%s (down %s, right %s)" % (m.get("size"), m.get("theme"), m.get("screen"), m.get("overflowPx"), m.get("overflowXPx")) for m in bad)), file=sys.stderr)
        sys.exit(1)
