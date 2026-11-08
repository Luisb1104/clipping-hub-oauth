"""Clip type -> destination channel (MAIN / PAID / GAMING). Pure; never posts, never calls Opus/YouTube.

Assignment happens ONCE, when a new clip is created (tools/assign_destination.py, used by the clip writer).
The result is stamped on the item as `destination` (or `destination_error`) and is never reassigned:
  - items that already carry `destination` or `destination_error` are returned unchanged
  - items without `clip_type` (all existing queue items) are untouched and keep legacy MAIN/PAID routing
Fail closed: unknown type, missing mapping/target, account not connected in Opus, or IDs that do not
match -> no destination + `destination_error` (UI shows 'needs destination'; Approve refused). No fallback.
This is NOT autopost permission: every publish, AI-disclosure and campaign gate still applies after Approve.
"""
from __future__ import annotations

import re
import time

KNOWN_TARGETS = ("MAIN", "PAID", "GAMING")
_YT_ID = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
_OPUS_ID = re.compile(r"^[0-9a-f]{24}$")


def norm_type(raw) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")[:40]


def type_routes(cfg) -> dict:
    raw = (cfg or {}).get("type_routes") if isinstance(cfg, dict) else None
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            t = norm_type(k); key = str(v or "").strip().upper()
            if t and key in KNOWN_TARGETS:
                out[t] = key
    return out


def _yt_from_url(url) -> str:
    m = re.search(r"/channel/(UC[0-9A-Za-z_-]{22})(?:[/?#]|$)", str(url or ""))
    return m.group(1) if m else ""


def check_target(key, cfg, channels):
    """Return (row, "") when target `key` is configured, well-formed and connected in Opus with matching IDs; else (None, reason)."""
    if key not in KNOWN_TARGETS:
        return None, "unknown_target"
    row = ((cfg or {}).get("targets") or {}).get(key)
    if not isinstance(row, dict) or not row.get("yt") or not row.get("opus_post_account_id"):
        return None, "target_missing:" + key
    yt, opus = str(row["yt"]), str(row["opus_post_account_id"])
    if not _YT_ID.match(yt) or not _OPUS_ID.match(opus):
        return None, "target_ids_malformed:" + key
    rows = [c for c in ((channels or {}).get("channels") or []) if isinstance(c, dict)]
    acct = [c for c in rows if str(c.get("post_account_id") or "") == opus]
    if not acct:
        return None, "not_connected_in_opus:" + key
    a = acct[0]
    if str(a.get("platform") or "").upper() != "YOUTUBE":
        return None, "opus_account_not_youtube:" + key
    if _yt_from_url(a.get("profile_url")) != yt:
        return None, "id_mismatch:" + key
    return row, ""


def resolve(clip_type, cfg, channels):
    """(destination_dict, "") or (None, reason)."""
    t = norm_type(clip_type)
    if not t:
        return None, "missing_type"
    routes = type_routes(cfg)
    if not routes:
        return None, "mapping_missing"
    key = routes.get(t)
    if not key:
        return None, "unknown_type:" + t
    row, err = check_target(key, cfg, channels)
    if err:
        return None, err
    return {
        "target": key,
        "name": str(row.get("name") or key)[:120],
        "handle": str(row.get("handle") or "")[:64],
        "yt": str(row["yt"])[:64],
        "opus_post_account_id": str(row["opus_post_account_id"])[:64],
        "clip_type": t,
    }, ""


def assign(item, cfg, channels, *, now=None):
    """Creation-time stamp. Returns a NEW dict; never reassigns an item that already has a decision or no clip_type."""
    if not isinstance(item, dict):
        return item
    if "destination" in item or "destination_error" in item or "clip_type" not in item:
        return dict(item)
    out = dict(item)
    dest, err = resolve(item.get("clip_type"), cfg, channels)
    ts = now or time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if dest:
        dest["assigned_at"] = ts
        out["destination"] = dest
    else:
        out["destination_error"] = err[:120]
    return out


def verify_stamp(item, cfg, channels):
    """Read-time check of a stamped item WITHOUT changing the stamp. Returns (dest, "") or (None, reason).
    Only meaningful for items with clip_type; callers keep legacy routing for items without it."""
    if not isinstance(item, dict):
        return None, "bad_item"
    if item.get("destination_error"):
        return None, str(item["destination_error"])[:120]
    d = item.get("destination")
    if not isinstance(d, dict):
        return None, "needs_destination"
    key = str(d.get("target") or "")
    row, err = check_target(key, cfg, channels)
    if err:
        return None, err
    if str(d.get("yt") or "") != row["yt"] or str(d.get("opus_post_account_id") or "") != row["opus_post_account_id"]:
        return None, "id_mismatch:" + key
    return d, ""


def clean_stamp(c):
    """Sanitize stamped fields from approvals.json for the hub item."""
    out = {}
    if "clip_type" in c:
        out["clip_type"] = norm_type(c.get("clip_type"))
    d = c.get("destination")
    if isinstance(d, dict):
        out["destination"] = {k: str(d.get(k) or "")[:120] for k in ("target", "name", "handle", "yt", "opus_post_account_id", "clip_type", "assigned_at")}
    if c.get("destination_error"):
        out["destination_error"] = str(c.get("destination_error"))[:120]
    return out
