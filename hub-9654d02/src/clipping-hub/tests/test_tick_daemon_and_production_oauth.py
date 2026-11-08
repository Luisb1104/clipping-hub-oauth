"""Daemon tick (flag-gated) + Production vs Testing OAuth modes."""
from __future__ import annotations

import time

import pytest

import server as S
import youtube_label_step as Y


@pytest.fixture(autouse=True)
def _reset_tick(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "_TICK_STATE_PATH", tmp_path / "tick.json")
    S.stop_youtube_label_tick_daemon()
    yield
    S.stop_youtube_label_tick_daemon()


def test_production_mode_hides_countdown_no_ttl_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.TESTING_MODE_FLAG, "false")
    Y.save_token("MAIN", {
        "refresh_token": "rt", "access_token": "a",
        "granted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 10 * 86400)),
        "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions",})
    meta = Y.grant_meta("MAIN")
    assert meta["testing_mode"] is False
    assert meta["show_countdown"] is False
    assert meta["expired"] is False
    assert meta["needs_regrant"] is False
    assert meta["expires_in_days"] is None
    assert Y.grants_summary()["testing_mode"] is False
    assert Y.needs_oauth("MAIN") is False
    assert Y.maybe_warn_grant_expiry("MAIN", push_fn=lambda *a, **k: True) is False


def test_testing_mode_countdown_and_ttl(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.TESTING_MODE_FLAG, "true")
    Y.save_token("MAIN", {
        "refresh_token": "rt", "access_token": "a",
        "granted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 8 * 86400)),
        "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions",})
    meta = Y.grant_meta("MAIN")
    assert meta["testing_mode"] is True
    assert meta["show_countdown"] is True
    assert meta["expired"] is True
    assert Y.needs_oauth("MAIN") is True


def test_tick_alerts_revoked_once(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setenv(Y.TESTING_MODE_FLAG, "false")
    (tmp_path / "cid").write_text("c")
    (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    Y.save_token("MAIN", {
        "refresh_token": "rt", "access_token": "a",
        "granted_at": "2026-01-01T00:00:00-0500",
        "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions",})
    alerts = []
    monkeypatch.setattr(Y, "refresh_access", lambda *a, **k: (None, "invalid_grant"))
    monkeypatch.setattr(Y, "maybe_warn_grant_expiry", lambda *a, **k: False)

    def push(title, body, key=None):
        alerts.append(title)
        return True

    monkeypatch.setattr(S, "TICK_MIN_GAP_S", 0)  # allow back-to-back for dedupe test
    r1 = S.run_youtube_label_tick(force=True, push_fn=push)
    assert any("revoked" in a.lower() or "expired" in a.lower() for a in alerts) or "MAIN" in (r1.get("revoked") or [])
    n = len(alerts)
    S.run_youtube_label_tick(force=True, push_fn=push)
    assert len(alerts) == n


def test_daemon_starts_only_when_flag_on(monkeypatch):
    monkeypatch.setenv(Y.FLAG, "false")
    assert S.start_youtube_label_tick_daemon() is None
    monkeypatch.setenv(Y.FLAG, "true")
    calls = []
    monkeypatch.setattr(S, "run_youtube_label_tick", lambda **k: calls.append(1) or {"ok": True})
    monkeypatch.setattr(S, "TICK_INTERVAL_S", 0)
    monkeypatch.setattr(S, "TICK_JITTER_S", 0)
    th = S.start_youtube_label_tick_daemon()
    assert th is not None and th.is_alive()
    deadline = time.time() + 2.0
    while time.time() < deadline and not calls:
        time.sleep(0.05)
    S.stop_youtube_label_tick_daemon()
    assert calls, "daemon should call tick logic when flag ON"


def test_tick_rate_limit_shared(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(S, "_TICK_STATE_PATH", tmp_path / "tick.json")
    monkeypatch.setattr(S, "TICK_MIN_GAP_S", 5 * 60)
    monkeypatch.setattr(Y, "maybe_warn_grant_expiry", lambda *a, **k: False)
    monkeypatch.setattr(Y, "check_grant_alive", lambda *a, **k: (True, None))
    r1 = S.run_youtube_label_tick(force=False)
    assert r1.get("error") != "label_step_off"
    r2 = S.run_youtube_label_tick(force=False)
    assert r2.get("skipped") is True
    assert r2.get("error") == "rate_limited"
    # force also rate-limited (does not bypass 5-min cap)
    r3 = S.run_youtube_label_tick(force=True)
    assert r3.get("skipped") is True
    assert r3.get("error") == "rate_limited"
