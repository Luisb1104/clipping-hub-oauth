"""Typed Clipping Hub alerts (phone ntfy + Mac banner via push_alerts).

Types: short_ready, credits_low, campaign_status, render_fail, sent, paid.
Reads Clipper mirror via clipper_data (empty => no alert). Never invents data.
Autopost is unrelated and stays off.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import clipper_data as CD
import push_alerts as P

ROOT = Path(__file__).resolve().parent
STATE_PATH = Path(os.environ.get("CLIPPING_HUB_ALERT_STATE", ROOT / "data" / "clipper_alert_state.json"))


def _load_state():
    try:
        s = json.loads(STATE_PATH.read_text())
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(s):
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(s))
        tmp.replace(STATE_PATH)
    except OSError:
        pass


ALERT_TYPES = (
    "short_ready",       # Short ready to approve
    "credits_low",       # credits below reserve
    "campaign_status",   # campaign status change
    "render_fail",       # render failed
    "sent",              # post sent
    "paid",              # payout paid
)


def alert_short_ready(item, **kw):
    title = "Short ready to approve"
    body = (item.get("title") or item.get("id") or "A Short").strip()[:120]
    body = f"{body} is waiting for your OK."
    return P.send_ntfy(title, body, key=f"short_ready:{item.get('id')}", tags="scissors", priority="high", **kw)


def alert_credits_low(kind, remaining, reserve, **kw):
    title = "Credits below reserve"
    body = f"{kind}: {remaining} left (reserve {reserve})."
    return P.send_ntfy(title, body, key=f"credits_low:{kind}:{remaining}", tags="warning", priority="high", **kw)


def alert_campaign_status(name, status, **kw):
    title = "Campaign status"
    body = f"{name}: {status}"
    return P.send_ntfy(title, body, key=f"campaign:{name}:{status}", tags="label", **kw)


def alert_render_fail(item, **kw):
    title = "Render failed"
    body = (item.get("title") or item.get("id") or "Short").strip()[:120] + " failed to render."
    return P.send_ntfy(title, body, key=f"render_fail:{item.get('id')}", tags="x", priority="high", **kw)


def alert_sent(item, **kw):
    title = "Post sent"
    body = (item.get("title") or item.get("id") or "Short").strip()[:120] + " was marked sent."
    return P.send_ntfy(title, body, key=f"sent:{item.get('id')}", tags="outbox_tray", **kw)


def alert_paid(name, **kw):
    title = "Paid"
    body = f"{name} payout recorded." if name else "A payout was recorded."
    return P.send_ntfy(title, body, key=f"paid:{name or 'x'}", tags="dollar", **kw)


def scan(state=None, *, send=True, opener=None):
    """Compare Clipper mirror to last alert state; enqueue typed alerts. Returns list of type keys sent."""
    st = state if state is not None else _load_state()
    sent = []
    shorts = CD.load_shorts()
    for it in shorts.get("items") or []:
        iid = it["id"]
        status = it.get("status")
        if status in ("queued", "rendered") and it.get("has_final"):
            # ready to approve
            prev = (st.get("shorts") or {}).get(iid)
            if prev != "ready" and send:
                if alert_short_ready(it, opener=opener, state=st.setdefault("_push", {})):
                    sent.append(f"short_ready:{iid}")
            st.setdefault("shorts", {})[iid] = "ready"
        if status == "failed":
            prev = (st.get("shorts") or {}).get(iid)
            if prev != "failed" and send:
                if alert_render_fail(it, opener=opener, state=st.setdefault("_push", {})):
                    sent.append(f"render_fail:{iid}")
            st.setdefault("shorts", {})[iid] = "failed"
        if status == "posted":
            prev = (st.get("shorts") or {}).get(iid)
            if prev != "posted" and send:
                if alert_sent(it, opener=opener, state=st.setdefault("_push", {})):
                    sent.append(f"sent:{iid}")
            st.setdefault("shorts", {})[iid] = "posted"

    credits = CD.load_credits()
    if not credits.get("empty"):
        opus = credits["opus"]
        rem = opus.get("remaining_today")
        if rem is None:
            rem = opus.get("remaining")
        reserve = opus.get("reserve", 30)
        if isinstance(rem, (int, float)) and rem < reserve:
            key = f"opus:{rem}"
            if st.get("credits_low") != key and send:
                if alert_credits_low("Opus", rem, reserve, opener=opener, state=st.setdefault("_push", {})):
                    sent.append("credits_low:opus")
            st["credits_low"] = key

    camps = CD.load_campaigns()
    seen = st.setdefault("campaigns", {})
    for c in camps.get("campaigns") or []:
        name, status = c["name"], c["status"]
        if not status:
            continue
        if seen.get(name) != status:
            if seen.get(name) is not None and send:  # only on change, not first sight
                if alert_campaign_status(name, status, opener=opener, state=st.setdefault("_push", {})):
                    sent.append(f"campaign_status:{name}")
            # "paid" heuristic
            if status.lower() in ("paid", "payout_paid") and send and seen.get(name) != status:
                if alert_paid(name, opener=opener, state=st.setdefault("_push", {})):
                    sent.append(f"paid:{name}")
            seen[name] = status

    if state is None:
        # strip ephemeral push dedupe before save? keep _push for dedupe across scans
        _save_state({k: v for k, v in st.items()})
    return sent


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--scan" in argv:
        dry = "--dry-run" in argv
        sent = scan(send=not dry)
        print("alerts:", ", ".join(sent) if sent else ("(dry-run ok)" if dry else "(none)"))
        return 0
    if "--types" in argv:
        print(" ".join(ALERT_TYPES))
        return 0
    print("Usage: clipper_alerts.py [--scan] [--dry-run] [--types]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
