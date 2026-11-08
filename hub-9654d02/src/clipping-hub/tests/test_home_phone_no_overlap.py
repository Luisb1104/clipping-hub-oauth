"""Home phone layout: greeting must not sit under the cards grid."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "static" / "app.css").read_text()
SW = (ROOT / "static" / "sw.js").read_text()

def test_phone_home_reorders_greeting_then_cards():
    assert "greeting first, then cards, then empty/safe" in CSS
    assert ".pane[data-pane=home]>.col{display:contents}" in CSS
    assert ".pane[data-pane=home] #h-home{order:1" in CSS
    assert ".pane[data-pane=home] .grid2{order:3" in CSS
    assert ".pane[data-pane=home] .empty{order:4" in CSS
    assert ".pane[data-pane=home] .safe{order:5" in CSS

def test_shell_cache_bumped_for_overlap_fix():
    assert "clipping-hub-shell-v35" in SW
