"""Declutter v35: drawer closed by default, no overlay, SW bump, accurate copy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static/index.html").read_text()
CSS = (ROOT / "static/app.css").read_text()
JS = (ROOT / "static/app.js").read_text()
SW = (ROOT / "static/sw.js").read_text()


def test_sw_v26():
    assert "clipping-hub-shell-v35" in SW


def test_home_has_approve_queue():
    assert 'id="home-appr"' in HTML
    assert 'id="home-appr-list"' in HTML


def test_alerts_drawer_closed_by_default_never_overlays():
    assert 'id="alerts-drawer"' in HTML
    assert 'id="alerts-drawer" hidden' in HTML or 'alerts-drawer" id="alerts-drawer" hidden' in HTML or 'hidden aria-hidden="true"' in HTML
    assert "alerts-drawer" in CSS
    assert "never position:absolute over videos" in CSS or "UNDER the approve list" in CSS
    assert "closeAlertsDrawer" in JS
    assert "openAlertsDrawer" in JS
    # Legacy dropdown forced hidden
    assert 'id="alerts-dropdown" hidden' in HTML or 'alerts-dropdown" id="alerts-dropdown" hidden' in HTML


def test_turn_on_alerts_hides_when_on_or_unsupported():
    assert "b.hidden = !!on || !supported" in JS


def test_stamp_approve_to_post_copy():
    assert "APPROVE ACTIONS SHOWN PER CLIP" in JS and "YOU POST MANUALLY" not in JS
    assert "APPROVE ACTIONS SHOWN PER CLIP" in HTML and "YOU POST MANUALLY" not in HTML
    assert "APPROVE TO POST" not in JS and "APPROVE TO POST" not in HTML


def test_placeholder_channels_strings_removed():
    assert "Nothing is connected yet. Connecting comes in a later step." not in HTML
    assert "The Connect buttons only show a not-connected message" not in HTML
    assert 'id="channels-slots"' in HTML
