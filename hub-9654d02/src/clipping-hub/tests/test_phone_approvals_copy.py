"""Approvals persist server-side; UI must not say computer-only."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "static" / "index.html").read_text()
JS = (ROOT / "static" / "app.js").read_text()
SW = (ROOT / "static" / "sw.js").read_text()

def test_no_computer_only_approval_note():
    assert "on this computer" not in HTML.lower()
    assert "token auth" in HTML.lower() or "hub (token" in HTML.lower()

def test_sw_never_caches_html_token():
    assert "NEVER HTML" in SW or "text/html" in SW
    assert "index.html" not in SW.split("SHELL")[1].split("]")[0] if "SHELL" in SW else True

def test_shell_bumped():
    assert "clipping-hub-shell-v35" in SW
