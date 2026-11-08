"""Static capability table for multi-platform Approve (Opus primary)."""
from __future__ import annotations

# Hub platform labels (approvals UI) → Opus platform + policy
# privacy_via_opus: whether POST /api/post-tasks documents a private mode for this platform
# ai_label_via_opus: whether Opus create-post can set an AI disclosure flag
# auto_post_when_ai: if False, hub must NOT auto-post when ai_disclosure (needs manual label)

PLATFORM_CAPABILITIES = {
    "Clipped Motions YouTube": {
        "key": "youtube",
        "opus_platform": "YOUTUBE",
        "can_post_opus": True,
        "privacy_via_opus": ("private", "unlisted", "public"),
        "private_value": "private",
        "ai_label_via_opus": False,  # YouTube Data API containsSyntheticMedia instead
        "auto_post_when_ai": True,   # private → label step → public
        "needs_sub_account": False,
    },
    "TikTok Business": {
        "key": "tiktok",
        "opus_platform": "TIKTOK_BUSINESS",
        "can_post_opus": True,
        "privacy_via_opus": (),  # Publish docs: privacy is YouTube-only
        "private_value": None,
        "ai_label_via_opus": False,
        # Postiz TT Business: privacy discarded on video DIRECT_POST
        "auto_post_when_ai": False,
        "block_reason": "needs_manual_label",
        "needs_sub_account": False,
    },
    "IG Business": {
        "key": "instagram",
        "opus_platform": "INSTAGRAM_BUSINESS",
        "can_post_opus": True,
        "privacy_via_opus": (),
        "private_value": None,
        "ai_label_via_opus": False,
        "auto_post_when_ai": False,
        "block_reason": "needs_manual_label",
        "needs_sub_account": True,
    },
    "FB Page": {
        "key": "facebook",
        "opus_platform": "FACEBOOK_PAGE",
        "can_post_opus": True,
        "privacy_via_opus": (),
        "private_value": None,
        "ai_label_via_opus": False,
        "auto_post_when_ai": False,
        "block_reason": "needs_manual_label",
        "needs_sub_account": True,
    },
}

# Opus account ids live in data/post_targets.json only — never hard-code here.
POSTIZ_CONNECTED = False  # integrationList returned []


def opus_accounts_from_post_targets(targets=None):
    """Read opus_post_account_id / opus_sub_account_id from post_targets.json rows."""
    try:
        import schedule_hook as _sched
        cfg = targets if isinstance(targets, dict) and "targets" in targets else _sched.load_targets()
    except Exception:
        cfg = targets if isinstance(targets, dict) else {}
    out = {}
    for key, row in ((cfg or {}).get("targets") or {}).items():
        if not isinstance(row, dict):
            continue
        out[str(key)] = {
            "post_account_id": str(row.get("opus_post_account_id") or "")[:64],
            "sub_account_id": str(
                row.get("opus_sub_account_id") or row.get("sub_account_id") or ""
            )[:64],
            "yt": str(row.get("yt") or "")[:64],
        }
    # Optional top-level platform_accounts map in post_targets.json
    for key, row in ((cfg or {}).get("platform_accounts") or {}).items():
        if not isinstance(row, dict):
            continue
        out[str(key)] = {
            "post_account_id": str(row.get("opus_post_account_id") or row.get("post_account_id") or "")[:64],
            "sub_account_id": str(row.get("opus_sub_account_id") or row.get("sub_account_id") or "")[:64],
            "yt": str(row.get("yt") or "")[:64],
        }
    return out


def capability_for(platform_label: str):
    return PLATFORM_CAPABILITIES.get(platform_label)


def plan_platforms(item, *, ai_disclosure=True):
    """Return list of {platform, key, action, reason} for one Approve.
    action: youtube_flow | needs_manual_label | skip
    """
    plats = list(item.get("platforms") or []) if isinstance(item, dict) else []
    out = []
    for label in plats:
        cap = capability_for(label)
        if not cap:
            out.append({"platform": label, "key": "unknown", "action": "skip", "reason": "unknown_platform"})
            continue
        if ai_disclosure and not cap.get("auto_post_when_ai"):
            out.append({
                "platform": label,
                "key": cap["key"],
                "action": "needs_manual_label",
                "reason": cap.get("block_reason") or "needs_manual_label",
                "opus_platform": cap["opus_platform"],
            })
        elif cap["key"] == "youtube":
            out.append({
                "platform": label,
                "key": "youtube",
                "action": "youtube_flow",
                "reason": None,
                "opus_platform": "YOUTUBE",
            })
        else:
            out.append({
                "platform": label,
                "key": cap["key"],
                "action": "opus_post",
                "reason": None,
                "opus_platform": cap["opus_platform"],
            })
    return out
