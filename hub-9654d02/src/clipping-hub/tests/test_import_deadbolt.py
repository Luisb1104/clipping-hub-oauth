"""Import scan: no private hostnames and no obvious live secrets in the tree."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "uploads", "__pycache__", ".pytest_cache", "agent-tools"}


def _files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP for part in p.parts):
            continue
        if p.suffix.lower() in {".png", ".mp4", ".ico", ".woff", ".woff2"}:
            continue
        yield p


def test_no_private_click_hostname_in_source():
    text = (ROOT / "push_alerts.py").read_text()
    assert "CLIPPING_HUB_CLICK" in text
    assert "CLIPPING_HUB_CLICK_FILE" in text
    assert "CLIPPING_HUB_CLICK_HOSTS" in text
    assert "127.0.0.1:8445" not in text
    # The previous click default named a private machine. That string must not return.
    for p in _files():
        if p.name == "test_import_deadbolt.py":
            continue
        raw = p.read_text(errors="ignore")
        assert "tail2" not in raw, p


def test_no_obvious_live_secrets():
    needles = ("-----BEGIN", "sk_live_", "ghp_", "xoxb-", "ya29.")
    for p in _files():
        if p.name == "test_import_deadbolt.py":
            continue
        raw = p.read_text(errors="ignore")
        for n in needles:
            assert n not in raw, (p, n)
    targets = (ROOT / "tests" / "fixtures" / "post_targets.json").read_text()
    assert "refresh_token" not in targets
    assert "client_secret" not in targets
    assert "access_token" not in targets
