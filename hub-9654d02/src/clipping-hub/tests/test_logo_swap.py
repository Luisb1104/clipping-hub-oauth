"""Logo swap 10/30: every manifest icon exists at its declared pixel size, apple-touch is opaque, sw cache bumped."""
import json, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def _size(p):
    b = p.read_bytes(); assert b[:8] == b"\x89PNG\r\n\x1a\n", p
    return struct.unpack(">II", b[16:24]), b[25]
def test_manifest_icons_exist_at_declared_sizes():
    m = json.loads((ROOT / "static/manifest.webmanifest").read_text())
    assert m["icons"]
    for i in m["icons"]:
        if i["type"] != "image/png": continue
        p = ROOT / "static" / i["src"].split("?")[0].lstrip("/")
        assert p.is_file() and p.stat().st_size > 0, p
        (w, h), ct = _size(p)
        assert f"{w}x{h}" == i["sizes"], (p, w, h, i["sizes"])
        assert "?v=lg1030" in i["src"]
def test_apple_touch_is_opaque_square():
    (w, h), ct = _size(ROOT / "static/apple-touch-icon.png")
    assert (w, h) == (180, 180) and ct == 2   # colour type 2 = RGB, no alpha
def test_sw_cache_bumped_for_logos():
    assert 'var C = "clipping-hub-shell-v35"' in (ROOT / "static/sw.js").read_text()
