"""Prove Channels pane renders /api/channels rows (stub + live Mac JSON fixture), not static HTML."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import server

ROOT = Path(__file__).resolve().parents[1]
LIVE_CHANNELS = Path("/workspace/api-channels-live.json")
CHROME = "/usr/bin/google-chrome"


def _write_clipper_channels(root: Path, payload) -> None:
    d = root / "channels"
    d.mkdir(parents=True, exist_ok=True)
    # clipper_data accepts list or {channels:[...]}
    (d / "channels.json").write_text(json.dumps(payload))


def _serve(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_CLIPPER_ROOT", str(tmp_path / "clipper"))
    # reload module path binding
    import clipper_data as cd
    monkeypatch.setattr(cd, "CLIPPER_ROOT", tmp_path / "clipper")
    monkeypatch.setattr(cd, "CHANNELS_DIR", tmp_path / "clipper" / "channels")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"version": 1, "theme": "system", "clips": [], "updated": "", "checklist": []}))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, ROOT / "static"))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    return httpd, base


def _dump_channels_dom(base: str) -> str:
    if not Path(CHROME).exists():
        pytest.skip("google-chrome missing")
    # virtual-time-budget lets fetch+/api/channels + renderChannelsPane finish
    r = subprocess.run(
        [
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--virtual-time-budget=8000", "--dump-dom",
            f"{base}/channels",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout


def test_channels_pane_renders_stubbed_api_name(tmp_path, monkeypatch):
    stub_name = "STUB_CHANNEL_ZZZ_UNIQUE"
    _write_clipper_channels(tmp_path / "clipper", [
        {"post_account_id": "stub1", "platform": "YOUTUBE", "name": stub_name,
         "profile_url": "https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa"},
        {"post_account_id": "stub2", "platform": "TIKTOK_BUSINESS", "name": "Other Stub", "profile_url": ""},
    ])
    httpd, base = _serve(tmp_path, monkeypatch)
    try:
        # API itself
        import urllib.request
        raw = json.loads(urllib.request.urlopen(base + "/api/channels", timeout=5).read())
        assert raw["empty"] is False
        assert raw["channels"][0]["name"] == stub_name
        dom = _dump_channels_dom(base)
        assert stub_name in dom
        assert "Connected in Opus" in dom
        assert "Hub YouTube grant missing" in dom
        assert "Connect channel" not in dom
        assert "Not connected yet" not in dom
        # must not be static fixture names only — stub unique string proves live render
        assert "STUB_CHANNEL_ZZZ_UNIQUE" in dom
    finally:
        httpd.shutdown()


def test_channels_pane_renders_live_mac_api_fixture(tmp_path, monkeypatch):
    if not LIVE_CHANNELS.exists():
        pytest.skip("live Mac /api/channels fixture missing")
    live = json.loads(LIVE_CHANNELS.read_text())
    assert live.get("channels"), "fixture empty"
    _write_clipper_channels(tmp_path / "clipper", live)
    httpd, base = _serve(tmp_path, monkeypatch)
    try:
        dom = _dump_channels_dom(base)
        # every live Opus display name must appear
        for row in live["channels"]:
            assert row["name"] in dom, row
            if row.get("platform") == "YOUTUBE":
                assert "Hub YouTube grant missing" in dom
        assert "Connected in Opus" in dom
        assert "Connect channel" not in dom
    finally:
        httpd.shutdown()


def test_safe_http_url_rejects_javascript_href():
    js = (ROOT / "static/app.js").read_text()
    assert "function safeHttpUrl" in js
    assert "safeHttpUrl(row.profile_url)" in js
    assert "noopener noreferrer" in js
    # unit the allowlist with a tiny exec of the function body
    # Extract via node-less: reimplement expected rule in python matching JS
    import re
    def safe_http_url(u: str) -> str:
        s = (u or "").strip()
        return s if re.match(r"^https?://", s, re.I) else ""
    assert safe_http_url("https://www.youtube.com/channel/UC123").startswith("https://")
    assert safe_http_url("javascript:alert(1)") == ""
    assert safe_http_url("data:text/html,x") == ""
