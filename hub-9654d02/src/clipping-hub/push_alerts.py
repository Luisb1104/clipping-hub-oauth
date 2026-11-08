"""Clipping Hub phone push via shared Banking Hub ntfy topic (READ-ONLY notifier).
Topic: ~/grok-trading-work/.ntfy_topic (TT_NTFY_TOPIC_FILE). Never printed, never committed.
Fail closed: missing/invalid topic or TT_NTFY=off -> no send. Dedupes 60 min; rate-limits 12/hour.
Click opens the hub on the phone (CLIPPING_HUB_CLICK). Never raises."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
TOPIC_FILE = Path(os.environ.get("TT_NTFY_TOPIC_FILE") or Path.home() / "grok-trading-work" / ".ntfy_topic")
SERVER = os.environ.get("TT_NTFY_SERVER", "https://ntfy.sh")
def _click_source():
    """Raw click string from deployment config. Not trusted by itself."""
    env = os.environ.get("CLIPPING_HUB_CLICK", "")
    if env.strip():
        return env
    raw = os.environ.get("CLIPPING_HUB_CLICK_FILE", "").strip()
    path = Path(raw) if raw else (Path.home() / ".config" / "clipping-hub" / "click-url")
    try:
        return path.read_text()
    except OSError:
        return ""


def trusted_click_hosts():
    """Hostnames allowed to appear in the Click header.

    This list is the trust decision. A URL is not trusted because it is HTTPS
    or because its own host looks like a hub. CLIPPING_HUB_CLICK_HOSTS is
    comma-separated. Otherwise CLIPPING_HUB_CLICK_HOSTS_FILE, or
    ~/.config/clipping-hub/click-hosts, one hostname per line.
    """
    env = os.environ.get("CLIPPING_HUB_CLICK_HOSTS")
    if env is not None and env.strip():
        parts = env.split(",")
    else:
        raw = os.environ.get("CLIPPING_HUB_CLICK_HOSTS_FILE", "").strip()
        path = Path(raw) if raw else (Path.home() / ".config" / "clipping-hub" / "click-hosts")
        try:
            parts = path.read_text().splitlines()
        except OSError:
            parts = []
    hosts = []
    for part in parts:
        host = part.split("#", 1)[0].strip().lower().rstrip(".")
        if not host or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in host):
            continue
        if any(mark in host for mark in ("/", "\\", "@", ":", "?")):
            continue
        hosts.append(host)
    return frozenset(hosts)


def safe_click(raw):
    """HTTPS click URL whose host is on the trusted list, or empty.

    Malformed values, control characters, non-HTTPS schemes, userinfo, and
    hosts that are not explicitly configured are dropped. The header value is
    rebuilt from the allowlisted host, not copied from the raw string.
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in raw):
        return ""
    if "\\" in raw or "@" in raw:
        return ""
    parts = urlsplit(raw.strip())
    if parts.scheme != "https" or parts.username or parts.password:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or host not in trusted_click_hosts():
        return ""
    path = parts.path or "/"
    if not path.startswith("/") or "\\" in path:
        return ""
    port = parts.port
    netloc = host if port in (None, 443) else "%s:%d" % (host, port)
    query = parts.query
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in query):
        return ""
    return urlunsplit(("https", netloc, path, query, ""))


def resolve_click_url():
    """Safe click URL, or empty when unset or not explicitly trusted."""
    return safe_click(_click_source())


CLICK = resolve_click_url()
STATE_PATH = Path(os.environ.get("CLIPPING_HUB_NOTIFY_STATE", ROOT / "data" / "notify_state.json"))
DEDUPE_S = int(os.environ.get("CLIPPING_HUB_NOTIFY_DEDUPE_S", "3600"))
RATE_MAX = int(os.environ.get("CLIPPING_HUB_NOTIFY_RATE_MAX", "12"))
RATE_WINDOW_S = int(os.environ.get("CLIPPING_HUB_NOTIFY_RATE_WINDOW_S", "3600"))


def topic():
    try:
        t = TOPIC_FILE.read_text().strip()
        return t if t.startswith("tt-") and len(t) >= 20 else None
    except OSError:
        return None


def _ssl_ctx():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _hdr(v):
    import base64
    try:
        v.encode("ascii")
        return v
    except UnicodeEncodeError:
        return "=?UTF-8?B?" + base64.b64encode(v.encode()).decode() + "?="


def load_state(path=None):
    p = Path(path) if path else STATE_PATH
    try:
        s = json.loads(p.read_text())
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state, path=None):
    p = Path(path) if path else STATE_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(p)
    except OSError:
        pass


def _rate_ok(state, now):
    stamps = [float(x) for x in (state.get("sent_at") or []) if now - float(x) < RATE_WINDOW_S]
    state["sent_at"] = stamps
    return len(stamps) < RATE_MAX


def send_ntfy(title, body, *, key=None, tags="scissors", priority="default",
              state=None, now=None, opener=None, topic_fn=None, click=None):
    """POST to ntfy. True if sent. Never raises, never prints the topic."""
    try:
        now_s = time.time() if now is None else float(now)
        st = state if state is not None else load_state()
        k = key or f"{title}|{body}"
        seen = st.setdefault("sent", {})
        if k in seen and now_s - float(seen[k]) < DEDUPE_S:
            if state is None:
                save_state(st)
            return False
        if not _rate_ok(st, now_s):
            if state is None:
                save_state(st)
            return False
        if os.environ.get("TT_NTFY", "on").lower() == "off":
            return False
        t = (topic_fn or topic)()
        if not t:
            return False
        safe = safe_click(CLICK if click is None else click)
        headers = {
            "Title": _hdr(title or "Clipping Hub"),
            "Tags": tags,
            "Priority": priority,
        }
        if safe:
            headers["Click"] = safe
        req = urllib.request.Request(
            f"{SERVER}/{t}",
            data=(body or "").encode(),
            method="POST",
            headers=headers,
        )
        if opener:
            opener(req, timeout=5).read()
        else:
            urllib.request.urlopen(req, timeout=5, context=_ssl_ctx()).read()
        try:
            import mac_notify as _mac
            _mac.notify(title or "Clipping Hub", body or "")
        except Exception:
            pass
        seen[k] = now_s
        st.setdefault("sent_at", []).append(now_s)
        for old in [x for x, v in list(seen.items()) if now_s - float(v) > 2 * DEDUPE_S]:
            seen.pop(old, None)
        if state is None:
            save_state(st)
        return True
    except Exception:
        return False


def notify_event(item, **kwargs):
    """Push for a new hub event. item is the cleaned events.json row. Fail closed."""
    try:
        if not item or not isinstance(item, dict):
            return False
        title = (item.get("title") or item.get("type") or "Clipping Hub").strip()[:80] or "Clipping Hub"
        body = (item.get("body") or "Something is waiting in Clipping Hub.").strip()[:240]
        eid = str(item.get("id") or title)
        return send_ntfy(title, body, key=f"ev:{eid}", tags="scissors", **kwargs)
    except Exception:
        return False


def notify_approval_waiting(item, **kwargs):
    """Push when a scheduling approval is waiting. Fail closed."""
    try:
        if not item or not isinstance(item, dict):
            return False
        title = "Approval waiting"
        name = (item.get("title") or item.get("id") or "clip").strip()[:60]
        body = f"{name} needs a yes/no in Approvals."
        aid = str(item.get("id") or name)
        return send_ntfy(title, body, key=f"ap:{aid}", tags="inbox_tray", priority="high", **kwargs)
    except Exception:
        return False


def send_test(*, opener=None, state=None, now=None):
    """One intentional test push. Bypasses dedupe via unique key. Never prints the topic."""
    import uuid
    key = "test:" + uuid.uuid4().hex[:12]
    ok = send_ntfy(
        "Clipping Hub test",
        "Push works. Open the hub when something is waiting.",
        key=key,
        tags="white_check_mark",
        priority="default",
        state=state if state is not None else {},  # ephemeral: do not persist test keys
        now=now,
        opener=opener,
    )
    return ok


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--test" in argv:
        ok = send_test()
        # Never print topic or URL with topic. Only yes/no.
        print("test push: sent" if ok else "test push: not sent (no topic, TT_NTFY=off, or network failed)")
        return 0 if ok else 1
    if "--status" in argv:
        t = topic()
        print("topic: configured" if t else "topic: missing or invalid")
        print("ntfy:", "off" if os.environ.get("TT_NTFY", "on").lower() == "off" else "on")
        print("click host:", CLICK.split("/")[2] if "://" in CLICK else "(set CLIPPING_HUB_CLICK)")
        return 0
    print("Usage: push_alerts.py [--test] [--status]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
