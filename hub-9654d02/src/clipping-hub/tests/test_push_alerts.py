"""Clipping Hub ntfy push: fail closed, dedupe, rate limit, Click header. Never hits the network."""
import json
import os
from pathlib import Path

import push_alerts as P

ROOT = Path(__file__).resolve().parents[1]


class _FakeResp:
    def read(self):
        return b"ok"


def test_topic_rejects_short_or_wrong_prefix(tmp_path, monkeypatch):
    f = tmp_path / "t"
    f.write_text("nope")
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    assert P.topic() is None
    f.write_text("tt-short")
    assert P.topic() is None
    f.write_text("tt-" + ("a" * 20))
    assert P.topic() == "tt-" + ("a" * 20)


def test_send_fails_closed_without_topic(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "TOPIC_FILE", tmp_path / "missing")
    monkeypatch.setattr(P, "STATE_PATH", tmp_path / "st.json")
    calls = []
    assert P.send_ntfy("T", "B", opener=lambda r, timeout: calls.append(r) or _FakeResp()) is False
    assert calls == []


def test_send_fails_closed_when_ntfy_off(tmp_path, monkeypatch):
    f = tmp_path / "t"
    f.write_text("tt-" + ("b" * 20))
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    monkeypatch.setattr(P, "STATE_PATH", tmp_path / "st.json")
    monkeypatch.setenv("TT_NTFY", "off")
    calls = []
    assert P.send_ntfy("T", "B", opener=lambda r, timeout: calls.append(r) or _FakeResp()) is False
    assert calls == []


def test_send_posts_with_click_and_never_returns_topic(tmp_path, monkeypatch):
    topic = "tt-" + ("c" * 24)
    f = tmp_path / "t"
    f.write_text(topic)
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    monkeypatch.setattr(P, "STATE_PATH", tmp_path / "st.json")
    monkeypatch.delenv("TT_NTFY", raising=False)
    seen = []

    def opener(req, timeout):
        seen.append(req)
        return _FakeResp()

    assert P.send_ntfy("Hello", "body text", opener=opener, now=1_000.0) is True
    assert len(seen) == 1
    req = seen[0]
    assert req.get_method() == "POST"
    assert req.full_url.endswith("/" + topic)
    assert req.get_header("Title") == "Hello"
    assert req.get_header("Click") == "https://hub.example.test/approvals"
    assert req.get_header("Click") == P.safe_click(P.CLICK)
    # topic must not appear in module public helpers' return for notify
    assert P.notify_event({"id": "e1", "title": "Clip ready", "body": "Tap Approvals"}) in (True, False)


def test_click_header_rejects_untrusted_and_malformed(tmp_path, monkeypatch):
    f = tmp_path / "t"
    f.write_text("tt-" + ("f" * 20))
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    monkeypatch.setattr(P, "STATE_PATH", tmp_path / "st.json")
    monkeypatch.setenv("CLIPPING_HUB_CLICK_HOSTS", "hub.example.test")
    seen = []

    def opener(req, timeout):
        seen.append(req)
        return _FakeResp()

    bad = (
        "javascript:alert(1)",
        "http://hub.example.test/approvals",
        "https://evil.example/approvals",
        "https://hub.example.test/ok\r\nX-Injected: yes",
        "https://user:secret@hub.example.test/approvals",
        "https://evil.example#@hub.example.test/approvals",
    )
    for i, raw in enumerate(bad):
        assert P.safe_click(raw) == ""
        assert P.send_ntfy("T%d" % i, "B", click=raw, opener=opener, now=5000.0 + i) is True
        assert seen[-1].get_header("Click") is None
    good = P.safe_click("https://hub.example.test/approvals")
    assert good == "https://hub.example.test/approvals"
    assert P.send_ntfy("Tok", "B", click=good, opener=opener, now=9000.0) is True
    assert seen[-1].get_header("Click") == good
    monkeypatch.delenv("CLIPPING_HUB_CLICK_HOSTS", raising=False)
    monkeypatch.setenv("CLIPPING_HUB_CLICK_HOSTS_FILE", str(tmp_path / "missing-hosts"))
    assert P.safe_click("https://hub.example.test/approvals") == ""


def test_dedupe_blocks_second_identical_within_window(tmp_path, monkeypatch):
    f = tmp_path / "t"
    f.write_text("tt-" + ("d" * 20))
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    st = {}
    calls = []

    def opener(req, timeout):
        calls.append(1)
        return _FakeResp()

    assert P.send_ntfy("T", "B", state=st, now=100.0, opener=opener) is True
    assert P.send_ntfy("T", "B", state=st, now=200.0, opener=opener) is False
    assert P.send_ntfy("T", "B", state=st, now=100.0 + P.DEDUPE_S + 1, opener=opener) is True
    assert len(calls) == 2


def test_rate_limit_caps_sends_per_hour(tmp_path, monkeypatch):
    f = tmp_path / "t"
    f.write_text("tt-" + ("e" * 20))
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    monkeypatch.setattr(P, "RATE_MAX", 3)
    st = {}
    calls = []

    def opener(req, timeout):
        calls.append(1)
        return _FakeResp()

    for i in range(5):
        P.send_ntfy(f"T{i}", "B", state=st, now=1000.0 + i, opener=opener, key=f"k{i}")
    assert len(calls) == 3


def test_notify_event_and_approval_shapes(tmp_path, monkeypatch):
    f = tmp_path / "t"
    f.write_text("tt-" + ("f" * 20))
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    st = {}
    titles = []

    def opener(req, timeout):
        titles.append(req.get_header("Title"))
        return _FakeResp()

    assert P.notify_event({"id": "1", "title": "New clip", "body": "Review me"}, state=st, now=1.0, opener=opener)
    assert P.notify_approval_waiting({"id": "a1", "title": "Friday reel"}, state=st, now=2.0, opener=opener)
    assert titles[0] == "New clip"
    assert titles[1] == "Approval waiting"
    assert P.notify_event(None, state=st, opener=opener) is False


def test_server_hooks_push_without_urllib_in_server_source():
    py = (ROOT / "server.py").read_text()
    assert "push_alerts" in py and "notify_event" in py
    assert "urllib.request" not in py
    assert "socket.create_connection" not in py

def test_send_test_bypasses_persisted_dedupe(tmp_path, monkeypatch):
    f = tmp_path / "t"
    f.write_text("tt-" + ("g" * 20))
    monkeypatch.setattr(P, "TOPIC_FILE", f)
    monkeypatch.setattr(P, "STATE_PATH", tmp_path / "st.json")
    calls = []
    def opener(req, timeout):
        calls.append(req)
        return _FakeResp()
    assert P.send_test(opener=opener, state={}, now=1.0) is True
    assert P.send_test(opener=opener, state={}, now=1.0) is True  # new key each time
    assert len(calls) == 2
    assert calls[0].get_header("Title") == "Clipping Hub test"

