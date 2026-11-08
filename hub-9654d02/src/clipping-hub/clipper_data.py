"""Read-only Clipper data contract for the hub.

Mac mirror (pull-only): data/clipper/{shorts,ledger}
Box source (Clipper writes): /workspace/clipping-hub/{shorts,ledger}

Hub never invents rows. Missing/unreadable files => empty payloads with
`empty: true` and a short reason. Never writes Clipper files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIPPER_ROOT = Path(os.environ.get("CLIPPING_HUB_CLIPPER_ROOT", ROOT / "data" / "clipper"))
SHORTS_DIR = CLIPPER_ROOT / "shorts"
LEDGER_DIR = CLIPPER_ROOT / "ledger"
CHANNELS_DIR = CLIPPER_ROOT / "channels"

SHORT_STATUSES = (
    "scripted", "voiced", "rendered", "queued", "approved", "rejected",
    "scheduled", "posted", "failed",
)
COMPLIANCE_TICKS = 6
TICK_VALUES = ("pass", "fail", "needs_check")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text()), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as e:
        return None, "unreadable"


def empty_credits():
    return {
        "empty": True,
        "reason": "Clipper has not written ledger/credits.json yet",
        "opus": {"monthly": 300, "reserve": 30, "budget_voice": 60, "budget_clips": 210,
                 "spent_today": None, "remaining_today": None},
        "elevenlabs": {"monthly": 30000, "spent_today": None, "remaining_today": None},
    }


def empty_campaigns():
    return {"empty": True, "reason": "Clipper has not written ledger/campaigns.json yet", "campaigns": []}


def empty_script_queue():
    return {"empty": True, "reason": "Clipper has not written ledger/script-queue.json yet", "items": []}


def empty_shorts():
    return {"empty": True, "reason": "No shorts under data/clipper/shorts yet", "items": []}


def load_credits(path=None):
    p = Path(path) if path else LEDGER_DIR / "credits.json"
    raw, err = _read_json(p)
    if err or not isinstance(raw, dict):
        out = empty_credits()
        if err:
            out["reason"] = f"credits.json {err}"
        return out
    opus = raw.get("opus") if isinstance(raw.get("opus"), dict) else {}
    el = raw.get("elevenlabs") if isinstance(raw.get("elevenlabs"), dict) else {}
    return {
        "empty": False,
        "reason": "",
        "as_of": raw.get("as_of") or raw.get("updated_at") or "",
        "last_synced": raw.get("last_synced") or raw.get("as_of") or raw.get("updated_at") or "",
        "opus": {
            "monthly": opus.get("monthly", 300),
            "reserve": opus.get("reserve", 30),
            "budget_voice": opus.get("budget_voice", 60),
            "budget_clips": opus.get("budget_clips", 210),
            "spent_today": opus.get("spent_today"),
            "remaining_today": opus.get("remaining_today"),
            "spent": opus.get("spent"),
            "used": opus.get("used", opus.get("spent")),
            "remaining": opus.get("remaining"),
            "source": opus.get("source"),
        },
        "elevenlabs": {
            "monthly": el.get("monthly", 30000),
            "spent_today": el.get("spent_today"),
            "remaining_today": el.get("remaining_today"),
            "spent": el.get("spent"),
            "used": el.get("used", el.get("spent")),
            "remaining": el.get("remaining"),
            "source": el.get("source"),
            "reason": el.get("reason") or "",
            "label": el.get("label") or "",
        },
    }


def load_campaigns(path=None):
    p = Path(path) if path else LEDGER_DIR / "campaigns.json"
    raw, err = _read_json(p)
    if err or not isinstance(raw, (dict, list)):
        out = empty_campaigns()
        if err:
            out["reason"] = f"campaigns.json {err}"
        return out
    rows = raw if isinstance(raw, list) else (raw.get("campaigns") or raw.get("items") or [])
    campaigns = []
    for c in rows:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        campaigns.append({
            "name": str(c.get("name"))[:120],
            "status": str(c.get("status") or "")[:64],
            "rate_per_1k": c.get("rate_per_1k"),
            "min_payout": c.get("min_payout"),
            "source": str(c.get("source") or "")[:200],
            "id": str(c.get("id") or c.get("campaign_id") or "")[:64],
        })
    as_of = str((raw.get("last_synced") or raw.get("as_of") or "") if isinstance(raw, dict) else "")
    return {"empty": len(campaigns) == 0 and err is None, "reason": "" if campaigns else "campaigns.json has no rows", "campaigns": campaigns, "as_of": as_of}


def load_script_queue(path=None):
    p = Path(path) if path else LEDGER_DIR / "script-queue.json"
    raw, err = _read_json(p)
    if err or not isinstance(raw, (dict, list)):
        out = empty_script_queue()
        if err:
            out["reason"] = f"script-queue.json {err}"
        return out
    rows = raw if isinstance(raw, list) else (raw.get("items") or raw.get("queue") or [])
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
    as_of = str((raw.get("last_synced") or raw.get("as_of") or "") if isinstance(raw, dict) else "")
    return {"empty": len(items) == 0, "reason": "" if items else "script-queue.json has no rows", "items": items, "as_of": as_of, "last_synced": as_of}


def _clean_meta(meta, folder_id):
    if not isinstance(meta, dict):
        return None
    iid = str(meta.get("id") or folder_id)[:64]
    if not iid:
        return None
    status = meta.get("status") if meta.get("status") in SHORT_STATUSES else str(meta.get("status") or "")[:32]
    comp = meta.get("compliance") if isinstance(meta.get("compliance"), dict) else {}
    # Expect 6 tick keys; pass through only pass|fail|needs_check
    ticks = {}
    for k, v in list(comp.items())[:12]:
        if isinstance(v, str) and v in TICK_VALUES:
            ticks[str(k)[:40]] = v
    credits = meta.get("credits") if isinstance(meta.get("credits"), dict) else {}
    return {
        "id": iid,
        "lane": str(meta.get("lane") or "")[:64],
        "channel": str(meta.get("channel") or "")[:64],
        "niche": str(meta.get("niche") or "")[:64],
        "title": str(meta.get("title") or "")[:200],
        "caption": str(meta.get("caption") or "")[:500],
        "hashtags": meta.get("hashtags") if isinstance(meta.get("hashtags"), list) else [],
        "is_ad": bool(meta.get("is_ad")) if "is_ad" in meta else None,
        "ai_disclosure": True if "ai_disclosure" not in meta else bool(meta.get("ai_disclosure")),
        "duration_s": meta.get("duration_s"),
        "created_at": str(meta.get("created_at") or "")[:64],
        "status": status,
        "compliance": ticks,
        "licenses": meta.get("licenses") if isinstance(meta.get("licenses"), (list, dict)) else [],
        "credits": {
            "opus": credits.get("opus"),
            "elevenlabs": credits.get("elevenlabs"),
        },
        "campaign_id": str(meta.get("campaign_id") or "")[:64],
        "paths": {
            "dir": str(SHORTS_DIR / iid),
            "final": str(SHORTS_DIR / iid / "final.mp4"),
            "thumb": str(SHORTS_DIR / iid / "thumb.png"),
            "script": str(SHORTS_DIR / iid / "script.md"),
            "meta": str(SHORTS_DIR / iid / "meta.json"),
        },
        "has_final": (SHORTS_DIR / iid / "final.mp4").is_file(),
        "has_thumb": (SHORTS_DIR / iid / "thumb.png").is_file(),
        "has_script": (SHORTS_DIR / iid / "script.md").is_file(),
    }


def load_shorts(root=None):
    d = Path(root) if root else SHORTS_DIR
    if not d.is_dir():
        return empty_shorts()
    items = []
    try:
        kids = sorted([p for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")])
    except OSError:
        return empty_shorts()
    for folder in kids:
        meta_path = folder / "meta.json"
        raw, err = _read_json(meta_path)
        if err:
            continue
        cleaned = _clean_meta(raw, folder.name)
        if cleaned:
            items.append(cleaned)
    if not items:
        return empty_shorts()
    return {"empty": False, "reason": "", "items": items}


def empty_channels():
    return {"empty": True, "reason": "channels.json missing", "channels": [], "as_of": ""}


def load_channels(path=None):
    p = Path(path) if path else CHANNELS_DIR / "channels.json"
    raw, err = _read_json(p)
    if err or not isinstance(raw, (dict, list)):
        out = empty_channels()
        if err:
            out["reason"] = f"channels.json {err}"
        return out
    rows = raw if isinstance(raw, list) else (raw.get("channels") or raw.get("accounts") or [])
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
    return {
        "empty": len(items) == 0,
        "reason": "" if items else "channels.json has no rows",
        "channels": items,
        "as_of": str((raw.get("last_synced") or raw.get("as_of") or "") if isinstance(raw, dict) else ""),
        "last_synced": str((raw.get("last_synced") or raw.get("as_of") or "") if isinstance(raw, dict) else ""),
        "source": str(raw.get("source") or "") if isinstance(raw, dict) else "",
    }


def empty_revenue():
    return {
        "empty": True,
        "reason": "revenue.json missing",
        "connected": False,
        "banner": "not connected",
        "total_usd": 0,
        "currency": "USD",
        "sources": [],
        "as_of": "",
        "last_synced": "",
        "whop": {"connected": False},
        "youtube": None,
    }


def load_revenue(path=None):
    p = Path(path) if path else LEDGER_DIR / "revenue.json"
    raw, err = _read_json(p)
    if err or not isinstance(raw, dict):
        out = empty_revenue()
        if err:
            out["reason"] = f"revenue.json {err}"
        return out
    sources = []
    for s in raw.get("sources") or []:
        if not isinstance(s, dict):
            continue
        sources.append({
            "id": str(s.get("id") or "")[:40],
            "name": str(s.get("name") or "")[:80],
            "amount_usd": s.get("amount_usd"),
            "connected": bool(s.get("connected")),
            "label": str(s.get("label") or "")[:40],
        })
    try:
        total = float(raw.get("total_usd") or 0)
    except (TypeError, ValueError):
        total = 0.0
    return {
        "empty": False,
        "reason": str(raw.get("reason") or ""),
        "connected": bool(raw.get("connected")),
        "banner": str(raw.get("banner") or ("connected" if raw.get("connected") else "not connected")),
        "total_usd": total,
        "currency": str(raw.get("currency") or "USD")[:8],
        "sources": sources,
        "as_of": str(raw.get("as_of") or ""),
        "last_synced": str(raw.get("last_synced") or raw.get("as_of") or ""),
        "whop": raw.get("whop") if isinstance(raw.get("whop"), dict) else {},
        "youtube": raw.get("youtube"),
    }
