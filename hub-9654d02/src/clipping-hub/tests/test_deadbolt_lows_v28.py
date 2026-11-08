"""Deadbolt Lows on d3beeef..2cb0d95: SW no-206/no-samples cache, symlink refuse, esc() on campaigns/shorts."""
from __future__ import annotations

import http.client
import json
import os
import stat
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import server

ROOT = Path(__file__).resolve().parents[1]
SW = (ROOT / "static" / "sw.js").read_text()
JS = (ROOT / "static" / "app.js").read_text()


def test_sw_v35_never_caches_206_or_samples():
    assert "clipping-hub-shell-v35" in SW
    assert "r.status === 200" in SW
    assert "r.ok &&" not in SW.split("function storable")[1].split("function ")[0]
    assert 'u.pathname.indexOf("/samples/") === 0' in SW
    # still skips api
    assert 'u.pathname.indexOf("/api/") === 0' in SW


def test_campaigns_and_shorts_use_full_esc():
    # campaigns: name, status, rate_per_1k via esc()
    camp = JS[JS.find("function renderCampaigns") : JS.find("function adoptScriptQueue")]
    assert "esc(c.name" in camp
    assert "esc(c.status" in camp
    assert "esc(c.rate_per_1k)" in camp
    assert ".replace(/[<>]/g" not in camp
    # shorts status + title
    shorts = JS[JS.find("function renderShorts") if "function renderShorts" in JS else JS.find("shorts") :]
    # locate the list.map for shorts more precisely
    idx = JS.find('ul.innerHTML = list.map(function (it)')
    chunk = JS[idx : idx + 280]
    assert "esc(it.status" in chunk
    assert "esc(it.title" in chunk or "esc(it.title || it.id" in chunk


def test_samples_symlink_component_refused(tmp_path):
    """Any symlink component under static/samples → 404 (lstat before resolve)."""
    static = tmp_path / "static"
    samples = static / "samples"
    samples.mkdir(parents=True)
    real = tmp_path / "outside.mp4"
    real.write_bytes(b"FAKEMP4DATA" * 20)
    link = samples / "evil.mp4"
    link.symlink_to(real)
    assert link.is_symlink()
    # also a symlink directory component
    leak_dir = tmp_path / "leak"
    leak_dir.mkdir()
    (leak_dir / "secret.mp4").write_bytes(b"SECRET" * 10)
    (samples / "via").symlink_to(leak_dir)

    state = tmp_path / "state.json"
    state.write_text(json.dumps({"version": 1, "theme": "system", "clips": [], "updated": "", "checklist": []}))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, static))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    host, port = httpd.server_address
    try:
        for path in ("/samples/evil.mp4", "/samples/via/secret.mp4"):
            c = http.client.HTTPConnection(host, port, timeout=5)
            c.request("GET", path)
            r = c.getresponse()
            body = r.read()
            assert r.status == 404, path
            assert b"SECRET" not in body and b"FAKEMP4DATA" not in body
            c.close()
        # control: real file under samples still works
        good = samples / "ok.mp4"
        good.write_bytes(b"GOOD" * 50)
        c = http.client.HTTPConnection(host, port, timeout=5)
        c.request("GET", "/samples/ok.mp4")
        r = c.getresponse()
        body = r.read()
        assert r.status == 200 and body.startswith(b"GOOD")
        assert r.getheader("Accept-Ranges") == "bytes"
        c.close()
    finally:
        httpd.shutdown()
