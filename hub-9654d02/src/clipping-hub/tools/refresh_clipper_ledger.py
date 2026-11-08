#!/usr/bin/env python3
"""Write Clipper ledger mirrors for the hub (Mac-side helper).

Prefer the box script /workspace/clipping-hub/sync/sync.py for Frankie's
9 AM run. This Mac helper accepts the same JSON shape (or the older nested
shape) and writes data/clipper including revenue.json.
Never invents numbers. Never prints secrets.
"""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CLIPPING_HUB_CLIPPER_ROOT", ROOT / "data" / "clipper"))
ET = ZoneInfo("America/New_York")
EL_PLAN = 30000


def now_et():
    s = datetime.now(ET).strftime("%Y-%m-%dT%H:%M:%S%z")
    return s[:-2] + ":" + s[-2:] if len(s) >= 5 else s


def atomic_write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def write_credits(payload, as_of):
    opus = payload.get("opus") if isinstance(payload.get("opus"), dict) else {}
    el = payload.get("elevenlabs") if isinstance(payload.get("elevenlabs"), dict) else {}
    # Frankie's shape: used/total/remaining OR older remaining-only
    remaining = opus.get("remaining")
    total = opus.get("total", opus.get("monthly", 300))
    used = opus.get("used", opus.get("spent"))
    el_used = el.get("used", el.get("spent"))
    plan = int(el.get("plan_chars", el.get("monthly", EL_PLAN)) or EL_PLAN)
    el_unverified = el_used is None
    out = {
        "as_of": as_of,
        "last_synced": as_of,
        "empty": False,
        "opus": {
            "monthly": total,
            "reserve": opus.get("reserve", 30),
            "budget_voice": opus.get("budget_voice", 60),
            "budget_clips": opus.get("budget_clips", 210),
            "spent_today": opus.get("spent_today"),
            "remaining_today": opus.get("remaining_today", remaining),
            "spent": used,
            "used": used,
            "remaining": remaining,
            "source": opus.get("source") or "sync",
        },
        "elevenlabs": {
            "monthly": plan,
            "spent_today": el.get("spent_today"),
            "remaining_today": None if el_unverified else max(0, plan - el_used),
            "spent": el_used,
            "used": el_used,
            "remaining": None if el_unverified else max(0, plan - el_used),
            "source": "unavailable" if el_unverified else (el.get("source") or "sync"),
            "reason": "30k/mo plan, usage unverified" if el_unverified else (el.get("reason") or ""),
            "label": "30k/mo plan, usage unverified" if el_unverified else "",
        },
    }
    atomic_write(OUT / "ledger" / "credits.json", out)
    return out


def write_campaigns(payload, as_of):
    rows = payload.get("campaigns") if isinstance(payload.get("campaigns"), list) else []
    cleaned = []
    for c in rows:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        cleaned.append({
            "name": str(c.get("name"))[:120],
            "status": str(c.get("status") or "")[:64],
            "rate_per_1k": c.get("rate_per_1k"),
            "min_payout": c.get("min_payout"),
            "source": str(c.get("source") or "")[:200],
            "id": str(c.get("id") or c.get("campaign_id") or "")[:64],
        })
    out = {"as_of": as_of, "last_synced": as_of, "empty": len(cleaned) == 0,
           "campaigns": cleaned, "reason": "" if cleaned else "no campaigns in payload"}
    atomic_write(OUT / "ledger" / "campaigns.json", out)
    return out


def write_script_queue(payload, as_of):
    rows = payload.get("script_queue") if isinstance(payload.get("script_queue"), list) else []
    items = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        items.append({
            "id": str(r["id"])[:64],
            "title": str(r.get("title") or "")[:200],
            "hook": str(r.get("hook") or "")[:300],
            "status": str(r.get("status") or "")[:64],
        })
    out = {"as_of": as_of, "last_synced": as_of, "empty": len(items) == 0, "items": items,
           "reason": "" if items else "Clipper has not queued scripts yet"}
    atomic_write(OUT / "ledger" / "script-queue.json", out)
    return out


def write_channels(payload, as_of):
    rows = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    items = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        items.append({
            "post_account_id": str(r.get("post_account_id") or "")[:64],
            "platform": str(r.get("platform") or "")[:40],
            "name": str(r.get("name") or "")[:120],
            "profile_url": str(r.get("profile_url") or "")[:300],
        })
    out = {"as_of": as_of, "last_synced": as_of, "empty": len(items) == 0, "channels": items,
           "source": payload.get("channels_source") or "sync",
           "reason": "" if items else "no linked accounts in payload"}
    atomic_write(OUT / "channels" / "channels.json", out)
    return out


def write_revenue(payload, as_of):
    rev = payload.get("revenue") if isinstance(payload.get("revenue"), dict) else {}
    whop = rev.get("whop") if isinstance(rev.get("whop"), dict) else {}
    yt = rev.get("youtube")
    try:
        total_f = float(whop.get("total_usd", whop.get("lifetime_usd") or 0) or 0)
    except (TypeError, ValueError):
        total_f = 0.0
    yt_connected = isinstance(yt, dict) and yt.get("connected") is True
    yt_amount = 0.0
    if yt_connected:
        try:
            yt_amount = float(yt.get("total_usd") or 0)
        except (TypeError, ValueError):
            yt_amount = 0.0
    whop_present = bool(whop) or ("revenue" in payload)
    sources = [
        {
            "id": "whop-campaigns",
            "name": "Whop Content Rewards",
            "amount_usd": total_f,
            "connected": whop_present,
            "label": "Connected" if whop_present else "Not connected",
        },
        {
            "id": "youtube-partner",
            "name": "YouTube Partner",
            "amount_usd": yt_amount if yt_connected else 0.0,
            "connected": yt_connected,
            "label": "Connected" if yt_connected else "No API path",
        },
        {
            "id": "youtube-shorts",
            "name": "YouTube Shorts",
            "amount_usd": 0.0,
            "connected": False,
            "label": "No API path",
        },
        {
            "id": "other-platforms",
            "name": "Other platforms",
            "amount_usd": 0.0,
            "connected": False,
            "label": "Not connected",
        },
    ]
    out = {
        "as_of": as_of,
        "last_synced": as_of,
        "empty": False,
        "connected": whop_present,
        "banner": "connected" if whop_present else "not connected",
        "total_usd": total_f + yt_amount,
        "currency": "USD",
        "sources": sources,
        "youtube": None if yt is None else yt,
        "whop": {
            "connected": whop_present,
            "total_usd": total_f,
            "lifetime_usd": float(whop.get("lifetime_usd") or total_f or 0),
            "last_30_days_usd": float(whop.get("last_30_days_usd") or 0),
            "balance_usd": float(whop.get("balance_usd") or 0),
            "source": "whop.users_me",
        },
        "reason": "" if whop_present else "Whop not in payload",
    }
    atomic_write(OUT / "ledger" / "revenue.json", out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="JSON payload path (else stdin)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    raw = Path(args.file).read_text() if args.file else sys.stdin.read()
    payload = json.loads(raw)
    as_of = payload.get("as_of") or now_et()
    if args.dry_run:
        print("ok", as_of, "keys", sorted(payload.keys()))
        return 0
    write_credits(payload, as_of)
    write_campaigns(payload, as_of)
    write_script_queue(payload, as_of)
    write_channels(payload, as_of)
    write_revenue(payload, as_of)
    print("wrote", OUT, "as_of", as_of)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
