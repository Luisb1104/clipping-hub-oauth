"""Mac Notification Center helper."""
import mac_notify as M


def test_enabled_defaults_on(monkeypatch):
    monkeypatch.delenv("CLIP_MAC_NOTIFY", raising=False)
    assert M.enabled() is True
    monkeypatch.setenv("CLIP_MAC_NOTIFY", "off")
    assert M.enabled() is False


def test_notify_runs_osascript(monkeypatch):
    calls = []
    def runner(cmd, **kw):
        calls.append(cmd)
        class R: returncode = 0
        return R()
    assert M.notify("Hello", "World", runner=runner) is True
    assert calls[0][:2] == ["osascript", "-e"]
    assert "Hello" in calls[0][2] and "World" in calls[0][2]


def test_notify_noop_when_off(monkeypatch):
    monkeypatch.setenv("CLIP_MAC_NOTIFY", "false")
    calls = []
    def runner(cmd, **kw):
        calls.append(cmd)
        class R: returncode = 0
        return R()
    assert M.notify("T", "B", runner=runner) is False
    assert calls == []


def test_notify_escapes_quotes():
    calls = []
    def runner(cmd, **kw):
        calls.append(cmd)
        class R: returncode = 0
        return R()
    assert M.notify('Say "hi"', 'body "x"', runner=runner) is True
    assert '\\"hi\\"' in calls[0][2]
