"""Bounded HTTP Range support for /samples/* (206 / 416 / HEAD / traversal)."""
from __future__ import annotations

import http.client
import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import server

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4"


@pytest.fixture()
def live(tmp_path):
    assert SAMPLE.is_file()
    static = tmp_path / "static"
    (static / "samples").mkdir(parents=True)
    shutil.copy(SAMPLE, static / "samples" / "sample-a.mp4")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"version": 1, "theme": "system", "clips": [], "updated": "", "checklist": []}))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, static))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    h, pnum = httpd.server_address
    class Live:
        pass
    live = Live()
    live.host = h
    live.port = pnum
    live.base = f"http://{h}:{pnum}"
    yield live
    httpd.shutdown()


def _req(live, method, path, headers=None):
    c = http.client.HTTPConnection(live.host, live.port, timeout=5)
    c.request(method, path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    hdrs = {k.lower(): v for k, v in r.getheaders()}
    status = r.status
    c.close()
    return status, hdrs, body


def test_parse_bytes_range_unit():
    assert server.parse_bytes_range("bytes=0-1", 100) == (0, 1)
    assert server.parse_bytes_range("bytes=100-", 150) == (100, 149)
    assert server.parse_bytes_range("bytes=-500", 1000) == (500, 999)
    assert server.parse_bytes_range("bytes=-500", 100) == (0, 99)
    with pytest.raises(ValueError):
        server.parse_bytes_range("bytes=999-", 10)
    with pytest.raises(ValueError):
        server.parse_bytes_range("bytes=5-1", 10)
    with pytest.raises(ValueError):
        server.parse_bytes_range("bytes=abc-1", 10)
    with pytest.raises(ValueError):
        server.parse_bytes_range("bytes=0-1,2-3", 10)


def test_full_get_accept_ranges(live):
    size = SAMPLE.stat().st_size
    st, h, body = _req(live, "GET", "/samples/sample-a.mp4")
    assert st == 200
    assert h.get("accept-ranges") == "bytes"
    assert h.get("content-type") == "video/mp4"
    assert h.get("content-length") == str(size)
    assert len(body) == size
    assert "content-range" not in h


def test_valid_single_range_0_1(live):
    size = SAMPLE.stat().st_size
    st, h, body = _req(live, "GET", "/samples/sample-a.mp4", {"Range": "bytes=0-1"})
    assert st == 206
    assert h.get("content-type") == "video/mp4"
    assert h.get("accept-ranges") == "bytes"
    assert h.get("content-range") == f"bytes 0-1/{size}"
    assert h.get("content-length") == "2"
    assert body == SAMPLE.read_bytes()[:2]


def test_open_ended_range(live):
    size = SAMPLE.stat().st_size
    st, h, body = _req(live, "GET", "/samples/sample-a.mp4", {"Range": "bytes=100-"})
    assert st == 206
    assert h.get("content-range") == f"bytes 100-{size - 1}/{size}"
    assert h.get("content-length") == str(size - 100)
    assert body == SAMPLE.read_bytes()[100:]


def test_suffix_range(live):
    size = SAMPLE.stat().st_size
    st, h, body = _req(live, "GET", "/samples/sample-a.mp4", {"Range": "bytes=-500"})
    assert st == 206
    start = max(0, size - 500)
    assert h.get("content-range") == f"bytes {start}-{size - 1}/{size}"
    assert h.get("content-length") == str(size - start)
    assert body == SAMPLE.read_bytes()[start:]


def test_unsatisfiable_and_invalid_416(live):
    size = SAMPLE.stat().st_size
    for rng in ("bytes=999999999-9999999999", "bytes=abc-def", "bytes=5-1", "bytes=0-1,2-3", "items=0-1"):
        st, h, body = _req(live, "GET", "/samples/sample-a.mp4", {"Range": rng})
        assert st == 416, rng
        assert h.get("content-range") == f"bytes */{size}", rng
        assert h.get("accept-ranges") == "bytes"
        assert h.get("content-type") == "video/mp4"
        assert body == b""


def test_head_full_and_range(live):
    size = SAMPLE.stat().st_size
    st, h, body = _req(live, "HEAD", "/samples/sample-a.mp4")
    assert st == 200 and body == b""
    assert h.get("content-length") == str(size)
    assert h.get("accept-ranges") == "bytes"
    assert h.get("content-type") == "video/mp4"

    st, h, body = _req(live, "HEAD", "/samples/sample-a.mp4", {"Range": "bytes=0-1"})
    assert st == 206 and body == b""
    assert h.get("content-length") == "2"
    assert h.get("content-range") == f"bytes 0-1/{size}"


def test_samples_path_traversal_blocked(live):
    for p in (
        "/samples/../server.py",
        "/samples/%2e%2e/server.py",
        "/samples/..%2fserver.py",
        "/samples/%2e%2e%2fserver.py",
        "/samples//etc/passwd",
        "/samples/../../etc/passwd",
    ):
        st, h, body = _req(live, "GET", p)
        assert st in (404, 400), p
        assert b"def make_handler" not in body
        assert b"ThreadingHTTPServer" not in body
