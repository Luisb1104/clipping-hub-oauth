"""Mac Notification Center helper for Clipping Hub. Local only; never posts.
Flag: CLIP_MAC_NOTIFY (default on). Fail closed on error. Never raises."""
from __future__ import annotations

import os
import subprocess


def enabled(env=None):
    e = env if env is not None else os.environ
    v = str(e.get("CLIP_MAC_NOTIFY", "on")).strip().lower()
    return v not in ("0", "false", "no", "off")


def _escape(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def notify(title, body, *, runner=subprocess.run, env=None):
    """Show a Notification Center banner. True if osascript exited 0."""
    try:
        if not enabled(env):
            return False
        title = _escape(str(title or "Clipping Hub")[:80])
        body = _escape(str(body or "")[:200])
        script = f'display notification "{body}" with title "{title}"'
        r = runner(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False
