"""Home stamp/lede and credits copy track real revenue + autopost state."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "app.js").read_text()
HTML = (ROOT / "static" / "index.html").read_text()
SERVER = (ROOT / "server.py").read_text()
SW = (ROOT / "static" / "sw.js").read_text()


def test_stamp_and_lede_driven_by_updateShellTruth():
    assert "function updateShellTruth" in JS
    assert "REVENUE CONNECTED" in JS
    assert "AUTOPOST OFF" in JS
    assert "Revenue is connected. Autopost is off. Clips wait for your Approve" in JS
    # no hardcoded CONNECTED-only stamp that ignores autopost
    assert "LOCAL SHELL · APPROVE TO POST · CONNECTED" not in JS
    assert "APPROVE TO POST" not in JS
    assert "APPROVE ACTIONS SHOWN PER CLIP" in JS and "YOU POST MANUALLY" not in JS
    assert 'id="home-lede"' in HTML
    assert 'id="shell-stamp"' in HTML
    # stale contradiction gone from static HTML
    home = HTML[HTML.find('data-pane="home"'):HTML.find('data-pane="queue"')]
    assert "nothing is connected yet" not in home.lower()
    assert "Nothing is posted and nothing is connected yet" not in HTML


def test_api_state_exposes_autopost_flag():
    assert "autopost_enabled" in SERVER
    assert "schedule_hook" in SERVER


def test_elevenlabs_null_used_shows_unverified():
    # elLabel must prefer unverified when used/spent is null
    assert "30k/mo plan, usage unverified" in JS
    assert "function elLabel" in JS
    # static HTML default must not be the dash form
    assert "ElevenLabs: — / 30000" not in HTML
    assert "ElevenLabs: 30k/mo plan, usage unverified" in HTML
    # unit the pure logic by extracting isn't needed — assert branch order
    idx = JS.find("function elLabel")
    chunk = JS[idx:idx + 700]
    assert chunk.find("e.label") < chunk.find("30k/mo plan, usage unverified")
    assert "used == null" in chunk
    assert "e.source === \"unavailable\"" in chunk or "e.reason" in chunk


def test_opus_label_is_this_month_not_today():
    assert "Opus left this month (reserve" in JS
    assert "Opus left today" not in JS
    assert "Opus remaining today" not in HTML
    assert "Opus left this month (reserve 30)" in HTML


def test_shell_cache_bumped():
    assert "clipping-hub-shell-v35" in SW
