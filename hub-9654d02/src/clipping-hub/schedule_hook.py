"""Approve -> schedule-post stub for Clipper.

Flag: CLIP_AUTOPOST_ENABLED (default false / off). When off, on_approved() is a no-op
but route_for_item() still works so the UI can show the routed target.
When on, approving marks the item 'scheduled' and appends one job record.
NEVER calls any external poster. No outbound network.

Routing (from data/post_targets.json):
  meta.is_ad == true OR campaign_id set -> PAID (+ #ad hashtag, paid_promotion=true)
  else -> MAIN (paid_promotion=false)
  Storyblocks YouTube is bound to the MAIN channel id unconditionally.
  That rule is not behind CLIP_PUBLIC_PUBLISH. Facebook may still be
  selected: the license finding did not ban that platform, and that
  does not lift the YouTube channel binding. Non-Storyblocks campaign
  items stay on PAID and GTA items stay on GAMING. Campaign rules can
  hold a campaign or deny platforms (CoD is TikTok and Instagram only).

AI disclosure (default true): job line gets ai_disclosure plus
per-platform flags (youtube.altered_synthetic, tiktok.ai_generated,
instagram.ai_info_label). AI-on jobs use privacy=private and
status=label_pending until labels are confirmed. Never mutate
title/caption with AI wording.

See docs/AUTOPOST_HOOK.md.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOBS_PATH = Path(os.environ.get("CLIPPING_HUB_AUTOPOST_JOBS", ROOT / "data" / "autopost_jobs.jsonl"))
TARGETS_PATH = Path(os.environ.get("CLIPPING_HUB_POST_TARGETS", ROOT / "data" / "post_targets.json"))
FLAG = "CLIP_AUTOPOST_ENABLED"

# Platform AI disclosure flags for Clipper/poster handoff (not written into caption/title).
AI_PLATFORM_FLAGS = {
    "youtube": {"altered_synthetic": True},
    "tiktok": {"ai_generated": True},
    "instagram": {"ai_info_label": True},
}

# Storyblocks YouTube must be the MAIN channel. Never silent-reroute.
# The legacy allowlist is what LABEL_STEP used before public publish. Facebook
# is not a license ban: it is only added when CLIP_PUBLIC_PUBLISH is on, so the
# label step does not gain a newly eligible upload while that flag is off.
MAIN_YOUTUBE_CHANNEL_ID = "UCgMuVjQmB9WvZtSz4e23THw"
LEGACY_STORYBLOCKS_PLATFORMS = frozenset({
    "Clipped Motions YouTube",
    "TikTok Business",
    "IG Business",
})
PUBLIC_STORYBLOCKS_PLATFORMS = LEGACY_STORYBLOCKS_PLATFORMS | {"FB Page"}


def public_publish_enabled(env=None):
    e = env if env is not None else os.environ
    v = str(e.get("CLIP_PUBLIC_PUBLISH", "false")).strip().lower()
    return v in ("1", "true", "yes", "on")


def storyblocks_allowed_platforms(env=None):
    if public_publish_enabled(env):
        return PUBLIC_STORYBLOCKS_PLATFORMS
    return LEGACY_STORYBLOCKS_PLATFORMS


# Back-compat name. Callers that need the live set use storyblocks_allowed_platforms.
STORYBLOCKS_ALLOWED_PLATFORMS = PUBLIC_STORYBLOCKS_PLATFORMS


def license_sources(item):
    """Collect license.source values from item.license and item.licenses (meta.json shapes)."""
    out = []
    if not isinstance(item, dict):
        return out
    lic = item.get("license")
    if isinstance(lic, dict) and lic.get("source") is not None:
        out.append(str(lic.get("source") or "").strip().lower())
    raw = item.get("licenses")
    if isinstance(raw, dict) and raw.get("source") is not None:
        out.append(str(raw.get("source") or "").strip().lower())
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict) and row.get("source") is not None:
                out.append(str(row.get("source") or "").strip().lower())
    return out


def is_storyblocks(item):
    return "storyblocks" in license_sources(item)


def storyblocks_block_reason(item, *, target_key, channel_id, platforms, env=None):
    """Unconditional MAIN-channel bind for Storyblocks.

    Any non-MAIN target is blocked. A MAIN row whose channel id is not the
    known MAIN id is blocked. The target is never rewritten. Facebook is on
    the allowlist only while CLIP_PUBLIC_PUBLISH is on. With that flag off,
    the pre-feature platform set is used so the label step stays unchanged.
    """
    if not is_storyblocks(item):
        return None
    key = str(target_key or "").upper()
    if key != "MAIN":
        return "storyblocks_main_only_blocks_non_main_target"
    cid = str(channel_id or "").strip()
    if cid and cid != MAIN_YOUTUBE_CHANNEL_ID:
        return "storyblocks_main_only_blocks_non_main_youtube"
    allowed = storyblocks_allowed_platforms(env)
    for plat in platforms or []:
        if not isinstance(plat, str):
            continue
        if plat not in allowed:
            return "storyblocks_main_only_blocks_platform"
    return None


def parse_ai_disclosure(item, default=True):
    """Bool from meta/item. Missing key => default (True). Explicit false stays false."""
    if not isinstance(item, dict):
        return bool(default)
    if "ai_disclosure" not in item:
        return bool(default)
    v = item.get("ai_disclosure")
    if v is False:
        return False
    if v is True:
        return True
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("0", "false", "no", "off"):
            return False
        if s in ("1", "true", "yes", "on"):
            return True
    return bool(default)


def ai_platform_map(enabled=True):
    """Return the per-platform disclosure map when AI label is on; empty when off."""
    if not enabled:
        return {
            "youtube": {"altered_synthetic": False},
            "tiktok": {"ai_generated": False},
            "instagram": {"ai_info_label": False},
        }
    # deep copy constants
    return {
        "youtube": dict(AI_PLATFORM_FLAGS["youtube"]),
        "tiktok": dict(AI_PLATFORM_FLAGS["tiktok"]),
        "instagram": dict(AI_PLATFORM_FLAGS["instagram"]),
    }



def enabled(env=None):
    e = env if env is not None else os.environ
    v = str(e.get(FLAG, "false")).strip().lower()
    return v in ("1", "true", "yes", "on")


def load_targets(path=None):
    p = Path(path) if path else TARGETS_PATH
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return {"version": 1, "poster": "opus", "targets": {}}
    if not isinstance(d, dict):
        return {"version": 1, "poster": "opus", "targets": {}}
    targets = d.get("targets") if isinstance(d.get("targets"), dict) else {}
    clean = {}
    for key in ("MAIN", "PAID", "GAMING"):
        t = targets.get(key)
        if not isinstance(t, dict):
            continue
        clean[key] = {
            "name": str(t.get("name") or "")[:120],
            "handle": str(t.get("handle") or "")[:64],
            "yt": str(t.get("yt") or "")[:64],
            "opus_post_account_id": str(t.get("opus_post_account_id") or "")[:64],
            "opus_sub_account_id": str(t.get("opus_sub_account_id") or t.get("sub_account_id") or "")[:64],
            "whop": str(t.get("whop") or "")[:64],
        }
    out = {
        "version": int(d.get("version") or 1),
        "poster": str(d.get("poster") or "opus")[:32],
        "targets": clean,
    }
    if isinstance(d.get("type_routes"), dict):
        out["type_routes"] = {str(k)[:40]: str(v)[:16] for k, v in d["type_routes"].items()}
    rules = _clean_campaign_rules(d.get("campaign_rules"))
    if rules:
        out["campaign_rules"] = rules
    accounts = _clean_accounts(d.get("accounts"))
    if accounts:
        out["accounts"] = accounts
    return out


def _campaign_key(raw) -> str:
    return "".join(ch for ch in str(raw or "").strip().lower() if ch.isalnum())[:40]


def _clean_campaign_rules(raw):
    """Hold / per-platform deny list. Not a poster and not a support message."""
    if not isinstance(raw, dict):
        return {}
    known = {
        "Clipped Motions YouTube",
        "TikTok Business",
        "IG Business",
        "FB Page",
    }
    out = {}
    for k, v in raw.items():
        cid = _campaign_key(k)
        if not cid or not isinstance(v, dict):
            continue
        deny = []
        for p in v.get("deny_platforms") or []:
            if isinstance(p, str) and p in known and p not in deny:
                deny.append(p)
        out[cid] = {
            "hold": v.get("hold") is True,
            "deny_platforms": deny,
            "reason": str(v.get("reason") or "")[:80],
        }
    return out


def _clean_accounts(raw):
    """Per-target accounts only. Missing rows are not filled from another target."""
    if not isinstance(raw, dict):
        return {}
    plats = ("youtube", "tiktok", "instagram", "facebook")
    out = {}
    for tkey, rows in raw.items():
        tk = str(tkey or "").strip().upper()
        if tk not in ("MAIN", "PAID", "GAMING") or not isinstance(rows, dict):
            continue
        cleaned = {}
        for pk, row in rows.items():
            if pk not in plats or not isinstance(row, dict):
                continue
            cleaned[pk] = {
                "provider": str(row.get("provider") or "")[:40],
                "account_name": str(row.get("account_name") or "")[:120],
                "account_id": str(row.get("account_id") or "")[:64],
                "external_id": str(row.get("external_id") or "")[:64],
                "auth_verified": row.get("auth_verified") is True,
            }
        if cleaned:
            out[tk] = cleaned
    return out


def campaign_rule_for(item, cfg):
    rules = (cfg or {}).get("campaign_rules") or {}
    if not isinstance(rules, dict):
        return None
    return rules.get(_campaign_key((item or {}).get("campaign_id") if isinstance(item, dict) else ""))


def apply_campaign_gate(item, cfg, route):
    """Campaign hold excludes the item. A deny list blocks named platforms only.

    A missing rule is reported as absent. It is not turned into a hold and it
    is not treated as an allow. Status does not clear a configured hold.
    """
    if not isinstance(route, dict):
        return route
    route["held"] = False
    route["deny_platforms"] = []
    route["campaign_config"] = "not_campaign"
    cid = str((item or {}).get("campaign_id") or "").strip() if isinstance(item, dict) else ""
    is_ad = _truthy_ad((item or {}).get("is_ad")) if isinstance(item, dict) else False
    if not cid and not is_ad:
        return route
    rule = campaign_rule_for(item, cfg)
    if not isinstance(rule, dict):
        route["campaign_config"] = "absent"
        route["campaign_config_id"] = cid[:64]
        return route
    route["deny_platforms"] = list(rule.get("deny_platforms") or [])
    if rule.get("hold"):
        route["campaign_config"] = "held"
        route["held"] = True
        route["blocked"] = True
        route["block_reason"] = rule.get("reason") or "campaign_held"
    else:
        route["campaign_config"] = "configured"
    return route


def _truthy_ad(v):
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "on"):
        return True
    return False


def _hashtags(raw):
    if isinstance(raw, list):
        out = []
        for h in raw:
            if isinstance(h, str) and h.strip() and h.strip() not in out:
                out.append(h.strip()[:64])
        return out
    if isinstance(raw, str) and raw.strip():
        return [p for p in raw.replace(",", " ").split() if p][:30]
    return []


def ensure_ad_hashtag(tags):
    tags = list(tags or [])
    low = {t.lower() for t in tags}
    if "#ad" not in low and "ad" not in low:
        tags.append("#ad")
    return tags


def _load_channels():
    try:
        import clipper_data as _cd
        return _cd.load_channels()
    except Exception:
        return {"channels": []}


def _stamped_route(item, cfg, channels):
    """Typed clips (clip_type present) route ONLY by their creation-time stamp, re-verified here. Fail closed."""
    import destination_routing as _dr
    dest, err = _dr.verify_stamp(item, cfg, channels if channels is not None else _load_channels())
    is_ad = _truthy_ad(item.get("is_ad"))
    campaign_id = str(item.get("campaign_id") or "").strip()
    paid = bool(is_ad or campaign_id)
    if not err:
        key = dest["target"]
        if paid and key != "PAID":
            err = "campaign_requires_PAID"
        elif key == "PAID" and not campaign_id:
            err = "campaign_id_missing"
    tags = _hashtags(item.get("hashtags"))
    if paid:
        tags = ensure_ad_hashtag(tags)
    key = dest["target"] if (dest and not err) else ""
    block = ""
    if not err and is_storyblocks(item):
        block = storyblocks_block_reason(
            item, target_key=key, channel_id=(dest or {}).get("yt", ""), platforms=list(item.get("platforms") or []),
        ) or ""
    route = {
        "target": key,
        "name": (dest or {}).get("name", "") if not err else "",
        "handle": (dest or {}).get("handle", "") if not err else "",
        "channel_id": (dest or {}).get("yt", "") if not err else "",
        "opus_post_account_id": (dest or {}).get("opus_post_account_id", "") if not err else "",
        "whop": ((cfg.get("targets") or {}).get(key) or {}).get("whop", "") if key else "",
        "paid_promotion": paid,
        "poster": cfg.get("poster") or "opus",
        "hashtags": tags,
        "campaign_id": campaign_id[:64],
        "is_ad": is_ad,
        "storyblocks": is_storyblocks(item),
        "needs_destination": bool(err),
        "destination_reason": err,
        "blocked": bool(err or block),
        "block_reason": ("needs_destination:" + err) if err else block,
    }
    if public_publish_enabled():
        return apply_campaign_gate(item, cfg, route)
    route["held"] = False
    route["deny_platforms"] = []
    return route


def route_for_item(item, targets=None, channels=None):
    """Pick MAIN or PAID. Pure. Never posts.
    Returns dict: target, channel_id (yt), opus_post_account_id, paid_promotion,
    handle, name, whop, poster, hashtags (possibly with #ad).
    When Storyblocks forbids the would-be target, returns the same shape with
    blocked=True and block_reason set — target is NOT rewritten to MAIN.
    """
    if not isinstance(item, dict):
        return None
    cfg = targets if isinstance(targets, dict) and "targets" in targets else load_targets()
    if "clip_type" in item or "destination" in item or "destination_error" in item:
        return _stamped_route(item, cfg, channels)
    poster = cfg.get("poster") or "opus"
    bucket = cfg.get("targets") or {}
    is_ad = _truthy_ad(item.get("is_ad"))
    campaign_id = str(item.get("campaign_id") or "").strip()
    paid = bool(is_ad or campaign_id)
    key = "PAID" if paid else "MAIN"
    t = bucket.get(key) or {}
    tags = _hashtags(item.get("hashtags"))
    if paid:
        tags = ensure_ad_hashtag(tags)
    channel_id = t.get("yt") or ""
    platforms = list(item.get("platforms") or [])
    block = storyblocks_block_reason(
        item, target_key=key, channel_id=channel_id, platforms=platforms,
    )
    route = {
        "target": key,
        "name": t.get("name") or key,
        "handle": t.get("handle") or "",
        "channel_id": channel_id,
        "opus_post_account_id": t.get("opus_post_account_id") or "",
        "whop": t.get("whop") or "",
        "paid_promotion": paid,
        "poster": poster,
        "hashtags": tags,
        "campaign_id": campaign_id[:64],
        "is_ad": is_ad,
        "storyblocks": is_storyblocks(item),
        "blocked": bool(block),
        "block_reason": block,
    }
    if public_publish_enabled():
        return apply_campaign_gate(item, cfg, route)
    route["held"] = False
    route["deny_platforms"] = []
    return route


def job_record(item, *, now=None, targets=None):
    if not isinstance(item, dict):
        return None
    iid = str(item.get("id") or "").strip()
    if not iid:
        return None
    ts = now if isinstance(now, str) and now else time.strftime("%Y-%m-%dT%H:%M:%S%z")
    route = route_for_item(item, targets=targets) or {}
    if route.get("blocked"):
        # Fail closed: never enqueue a Storyblocks job for a forbidden target.
        return None
    return {
        "version": 1,
        "op": "schedule_post",
        "id": iid[:64],
        "video": str(item.get("video") or "")[:400],
        "caption": str(item.get("caption") or "")[:500],
        "title": str(item.get("title") or "")[:200],
        "platforms": list(item.get("platforms") or []),
        "hashtags": list(route.get("hashtags") or []),
        "scheduled_at": str(item.get("scheduled_at") or "")[:64],
        "approved_at": str(item.get("decided_at") or ts)[:64],
        "queued_at": ts[:64],
                "source": "clipping-hub-approvals",
        "poster": route.get("poster") or "opus",
        "target": route.get("target") or "MAIN",
        "channel_id": route.get("channel_id") or "",
        "opus_post_account_id": route.get("opus_post_account_id") or "",
        "paid_promotion": bool(route.get("paid_promotion")),
        "campaign_id": route.get("campaign_id") or "",
        "is_ad": bool(route.get("is_ad")),
        "ai_disclosure": parse_ai_disclosure(item, default=True),
        "ai_platform": ai_platform_map(parse_ai_disclosure(item, default=True)),
        # Convenience mirrors for posters that expect flat keys:
        "youtube_altered_synthetic": bool(parse_ai_disclosure(item, default=True)),
        "tiktok_ai_generated": bool(parse_ai_disclosure(item, default=True)),
        "instagram_ai_info_label": bool(parse_ai_disclosure(item, default=True)),
        # Interim: AI-on jobs stay private until labels confirmed.
        "privacy": "private" if parse_ai_disclosure(item, default=True) else "public",
        "status": ("label_pending" if parse_ai_disclosure(item, default=True) else "queued"),
        "youtube_label_set": False,
        "tiktok_label_set": False,
        "instagram_label_set": False,
        "remote_ids": {},
        "error": None,
    }


def append_job(record, path=None):
    p = Path(path) if path else JOBS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    return True


def on_approved(item, *, jobs_path=None, env=None, now=None, targets=None):
    try:
        if not enabled(env):
            return False
        if not isinstance(item, dict) or item.get("status") != "approved":
            return False
        rec = job_record(item, now=now, targets=targets)
        if not rec:
            return False
        append_job(rec, path=jobs_path)
        item["status"] = rec["status"]  # label_pending when AI on; queued→scheduled only when AI off
        if rec["status"] == "queued":
            item["status"] = "scheduled"
        item["privacy"] = rec["privacy"]
        item["route_target"] = rec["target"]
        item["paid_promotion"] = rec["paid_promotion"]
        item["ai_disclosure"] = rec["ai_disclosure"]
        item["youtube_label_set"] = False
        item["tiktok_label_set"] = False
        item["instagram_label_set"] = False
        return True
    except Exception:
        return False
