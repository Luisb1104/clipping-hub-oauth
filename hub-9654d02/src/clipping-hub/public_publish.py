"""Explicit PUBLIC publish confirmation. Flag CLIP_PUBLIC_PUBLISH defaults off.

When the flag is off, this module is not used and Approve keeps the existing
private-label behavior. When it is on, Approve does not dispatch until the
client sends the manifest hash it showed. A changed caption, file, account, or
label invalidates that hash.

YouTube promote uses publish_adapters.youtube_promote_http when no test double
is installed. That is the production transport, still gated by the public flag,
confirmation hashes, and the promote preflight. Other platforms are not armed.
A mocked socket is not a live post.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

import post_idempotency as idem
import schedule_hook as sched

FLAG = "CLIP_PUBLIC_PUBLISH"
ROOT = Path(__file__).resolve().parent

# What this session verified on official pages (not a search-result paraphrase).
# False means the field was not in the page this session fetched, so dispatch
# must not invent it.
VERIFIED = {
    "opus_create_requires_project_and_clip": True,
    "opus_accepts_local_file": False,
    "opus_ai_toggle": False,
    "opus_paid_toggle": False,
    "postiz_integrations_seen": 0,
    "tiktok_business_video_has_privacy_field": False,
    "tiktok_business_is_ai_generated": True,
    "tiktok_business_is_branded_content": True,
    "tiktok_business_is_brand_organic": True,
    "tiktok_business_upload_to_draft_ignores_post_info": True,
    "tiktok_direct_post_is_aigc": True,
    "tiktok_direct_post_brand_toggles": True,
    "tiktok_upload_publishes": False,
    "ig_is_ai_generated": True,
    "ig_is_paid_partnership": True,
    "ig_branded_content_sponsor_ids": True,
    "ig_video_url_in_content_publishing": True,
    "ig_resumable_local_file": True,
    "ig_media_publish_creation_id": True,
    "youtube_resumable_local_upload": True,
    "youtube_unverified_projects_not_forced_private": True,
    "fb_reels_endpoint": True,
    "fb_reels_is_ai_generated": True,
    "fb_reels_paid_field": False,
    "youtube_contains_synthetic_media": True,
    # Insert "you can set" list fetched 2026-11-03 does not name this field.
    # A mock 201 that echoes it is not writable-field proof.
    "youtube_has_paid_product_placement": False,
}

PLATFORM_KEY = {
    "Clipped Motions YouTube": "youtube",
    "TikTok Business": "tiktok",
    "IG Business": "instagram",
    "FB Page": "facebook",
}
LEDGER_KEY = {
    "youtube": "pub:youtube",
    "tiktok": "pub:tiktok",
    "instagram": "pub:ig",
    "facebook": "pub:fb",
}
PROMOTE_LEDGER_KEY = "pub:youtube:promote"


def enabled(env=None) -> bool:
    e = env if env is not None else os.environ
    v = str(e.get(FLAG, "false")).strip().lower()
    return v in ("1", "true", "yes", "on")


def external_runners():
    """Test doubles only. Production does not invent a runner."""
    return {}


def credentials():
    """Validated identities from the outside-git publish config. Empty when unset."""
    import publish_runtime as runtime
    return runtime.load_publish_credentials()


def youtube_grant_status(channel):
    """Grant presence and bind check. The token itself is not returned."""
    try:
        import youtube_label_step as yls
        meta = yls.grant_meta(channel)
        present = bool(meta.get("present")) and not meta.get("expired") and not meta.get("needs_regrant")
        bound = bool(yls.token_bind_ok(channel)) if present else False
        return {"present": present, "bound": bound}
    except Exception:
        return {"present": False, "bound": False}


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def resolve_artifact(video, root=None):
    """Hash a same-origin /samples file. Never fetches a remote URL."""
    rel = str(video or "").strip()
    if not rel.startswith("/samples/"):
        return None, "media_not_local_sample"
    name = rel[len("/samples/"):]
    if not name or "/" in name or "\\" in name or name.startswith(".") or name != Path(name).name:
        return None, "bad_media_path"
    import publish_adapters as adapters
    path = adapters.open_sample(name, root)
    if path is None:
        return None, "media_missing"
    data = path.read_bytes()
    return {
        "name": name,
        "sha256": _sha256_bytes(data),
        "size": len(data),
    }, None


def _account(cfg, target, key):
    """Exact account row. No fallback to another target or provider."""
    rows = (cfg or {}).get("accounts") if isinstance(cfg, dict) else None
    if not isinstance(rows, dict):
        return None
    bucket = rows.get(target)
    if not isinstance(bucket, dict):
        return None
    row = bucket.get(key)
    return row if isinstance(row, dict) else None


def _ids(item):
    project_id = str(item.get("projectId") or item.get("project_id") or "")[:64]
    clip_id = str(item.get("clipId") or item.get("clip_id") or "")[:64]
    return project_id, clip_id


def _blocked(platform, key, *, reason, transport, account, artifact, caption, restrictions, disclosures, line):
    return {
        "platform": platform,
        "key": key,
        "public_action": "blocked",
        "will_dispatch": False,
        "reason": reason,
        "transport": transport,
        "account_name": (account or {}).get("account_name") or "",
        "account_id": (account or {}).get("account_id") or "",
        "external_id": (account or {}).get("external_id") or "",
        "provider": (account or {}).get("provider") or "",
        "artifact_sha256": (artifact or {}).get("sha256") or "",
        "artifact_name": (artifact or {}).get("name") or "",
        "caption": caption,
        "restrictions": restrictions,
        "disclosures": disclosures,
        "line": line,
    }


def _not_public(platform, key, *, reason, account, artifact, caption, restrictions, disclosures, line):
    row = _blocked(
        platform, key, reason=reason, transport="none", account=account,
        artifact=artifact, caption=caption, restrictions=restrictions,
        disclosures=disclosures, line=line,
    )
    row["public_action"] = "not_public"
    return row


def tiktok_business_body(row):
    """Body allowed by the fetched Business video publish reference.

    No privacy_level: that field is not in the video publish parameter table.
    upload_to_draft is not set: the same page says it ignores post_info and
    lands in the inbox, which is not a public post.
    """
    return {
        "business_id": row.get("account_id") or "",
        "post_info": {
            "caption": row.get("caption") or "",
            "is_ai_generated": bool((row.get("disclosures") or {}).get("ai")),
            "is_branded_content": bool((row.get("disclosures") or {}).get("paid")),
            "is_brand_organic": False,
        },
    }


def instagram_container_body(row):
    """Fields present on the fetched IG User media create reference. No #ad toggle."""
    disc = row.get("disclosures") or {}
    body = {
        "caption": row.get("caption") or "",
        "is_ai_generated": bool(disc.get("ai")),
        "is_paid_partnership": bool(disc.get("paid")),
    }
    sponsors = disc.get("sponsor_ids") or []
    if disc.get("paid") and sponsors:
        body["branded_content_sponsor_ids"] = list(sponsors)
    return body


def facebook_reels_body(row):
    """Only is_ai_generated from the fetched Page video_reels reference.

    Paid-partnership fields from Instagram are not copied onto this body.
    """
    return {
        "description": row.get("caption") or "",
        "is_ai_generated": bool((row.get("disclosures") or {}).get("ai")),
        "upload_phase": "FINISH",
        "video_state": "PUBLISHED",
    }


def _disclosures(item, route):
    ai = sched.parse_ai_disclosure(item, default=True)
    paid = bool((route or {}).get("paid_promotion"))
    return {
        "ai": ai,
        "paid": paid,
        "hashtag_ad_is_not_a_paid_toggle": True,
        "sponsor_ids": [],
    }


def _is_campaign(item, route):
    if not isinstance(item, dict):
        return False
    if item.get("is_ad") or str(item.get("campaign_id") or "").strip():
        return True
    if str(item.get("clip_type") or "") == "campaign":
        return True
    return bool((route or {}).get("paid_promotion"))


def _apply_rights(item, route, row):
    """rights_ok is required on every dispatchable row. Campaigns also need terms.

    A row that is already blocked keeps its reason. A row that would upload,
    or that would be marked ready, is blocked before any hash treats it as public.
    """
    if not isinstance(row, dict):
        return row
    missing = []
    if item.get("rights_ok") is not True:
        missing.append("rights_unconfirmed")
    if _is_campaign(item, route) and item.get("campaign_terms_ok") is not True:
        missing.append("campaign_terms_unconfirmed")
    if not missing:
        return row
    row = dict(row)
    row["restrictions"] = list(row.get("restrictions") or []) + [m for m in missing if m not in (row.get("restrictions") or [])]
    if row.get("will_dispatch") or row.get("public_action") in ("public_publish", "not_public"):
        row["will_dispatch"] = False
        row["public_action"] = "blocked"
        row["reason"] = missing[0]
        row["line"] = "Not a public post. %s must be true before any upload." % missing[0]
    return row


def decide_platform(item, platform, route, cfg, artifact, artifact_err):
    return _apply_rights(item, route, _decide_platform(item, platform, route, cfg, artifact, artifact_err))


def _decide_platform(item, platform, route, cfg, artifact, artifact_err):
    key = PLATFORM_KEY.get(platform, "unknown")
    caption = str(item.get("caption") or "")
    disc = _disclosures(item, route)
    target = str((route or {}).get("target") or "")
    account = _account(cfg, target, key) if target else None
    restrictions = []
    if (route or {}).get("storyblocks"):
        restrictions.append("storyblocks_main_youtube_only")
    for denied in (route or {}).get("deny_platforms") or []:
        if denied == platform:
            restrictions.append("campaign_denies_platform")
    if artifact_err:
        restrictions.append(artifact_err)

    if (route or {}).get("blocked"):
        reason = str((route or {}).get("block_reason") or "route_blocked")[:120]
        return _blocked(
            platform, key, reason=reason, transport="none",
            account=account, artifact=artifact, caption=caption,
            restrictions=restrictions + [reason], disclosures=disc,
            line="Not a public post. Route blocked (%s)." % reason,
        )

    if (route or {}).get("storyblocks") and key == "youtube":
        cid = str((route or {}).get("channel_id") or "").strip()
        if target not in ("", "MAIN"):
            return _blocked(
                platform, key, reason="storyblocks_main_only_blocks_non_main_target",
                transport="none", account=account, artifact=artifact, caption=caption,
                restrictions=restrictions, disclosures=disc,
                line="Not a public post. Storyblocks YouTube stays on MAIN.",
            )
        if target == "MAIN" and cid and cid != sched.MAIN_YOUTUBE_CHANNEL_ID:
            return _blocked(
                platform, key, reason="storyblocks_main_only_blocks_non_main_youtube",
                transport="none", account=account, artifact=artifact, caption=caption,
                restrictions=restrictions, disclosures=disc,
                line="Not a public post. Storyblocks YouTube channel id is not the MAIN grant.",
            )

    if key == "unknown":
        return _blocked(
            platform, key, reason="unknown_platform", transport="none",
            account=account, artifact=artifact, caption=caption,
            restrictions=restrictions, disclosures=disc,
            line="Not a public post. %s is not a hub platform." % platform,
        )

    if platform in ((route or {}).get("deny_platforms") or []):
        reason = "campaign_denies_youtube" if key == "youtube" else "campaign_denies_platform"
        return _blocked(
            platform, key, reason=reason, transport="none",
            account=account, artifact=artifact, caption=caption,
            restrictions=restrictions, disclosures=disc,
            line="Not a public post. Campaign rule blocks %s (%s)." % (platform, reason),
        )

    if key == "youtube" and str(item.get("clip_type") or "") == "horror" and target not in ("", "MAIN"):
        return _blocked(
            platform, key, reason="horror_youtube_main_only", transport="none",
            account=account, artifact=artifact, caption=caption,
            restrictions=restrictions + ["horror_youtube_main_only"], disclosures=disc,
            line="Not a public post. Horror YouTube stays on MAIN only (this item is routed %s)." % (target or "?"),
        )

    # Explicit AI off is the existing manual mark. It is not a public post,
    # and a caption hashtag does not turn it into one.
    if item.get("ai_disclosure") is False:
        return _not_public(
            platform, key, reason="manual", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line="Not a public post. Marks ready · you post manually.",
        )

    accounts = (cfg or {}).get("accounts") if isinstance(cfg, dict) else None
    if not isinstance(accounts, dict) or not accounts:
        import publish_readiness as prep
        return _blocked(
            platform, key, reason="accounts_map_absent", transport="none",
            account=None, artifact=artifact, caption=caption,
            restrictions=restrictions + ["accounts_map_absent"], disclosures=disc,
            line=prep.accounts_diagnostic(cfg, target, key),
        )

    if not account or not str(account.get("account_id") or "").strip():
        return _blocked(
            platform, key, reason="account_unconfigured", transport="none",
            account=account, artifact=artifact, caption=caption,
            restrictions=restrictions, disclosures=disc,
            line="Not a public post. No %s account is configured for %s. Nothing is substituted from another account." % (platform, target or "?"),
        )

    if not disc["ai"] and not disc["paid"] and key != "youtube":
        # Manual, unlabeled, unpaid: still not a silent public post.
        pass

    if key == "youtube":
        return _youtube_row(item, platform, route, account, artifact, artifact_err, caption, restrictions, disc)
    if key == "tiktok":
        return _tiktok_row(platform, account, artifact, caption, restrictions, disc)
    if key == "instagram":
        return _instagram_row(platform, account, artifact, caption, restrictions, disc)
    if key == "facebook":
        return _facebook_row(platform, account, artifact, caption, restrictions, disc)
    return _blocked(
        platform, key, reason="no_adapter", transport="none",
        account=account, artifact=artifact, caption=caption,
        restrictions=restrictions, disclosures=disc,
        line="Not a public post. No sanctioned adapter for %s." % platform,
    )


def youtube_token(channel):
    """Hub YouTube grant for the routed channel. None is an auth gate, not missing code."""
    try:
        import youtube_label_step as yls
        if yls.needs_oauth(channel):
            return None
        token, err = yls.refresh_access(channel, persist=False)
        return token or None
    except Exception:
        return None


def _armed(key, channel):
    runners = external_runners() or {}
    if callable(runners.get(key)):
        return True
    if key == "youtube":
        return bool(youtube_token(channel))
    return False


def _youtube_row(item, platform, route, account, artifact, artifact_err, caption, restrictions, disc):
    target = str((route or {}).get("target") or "")
    if artifact_err:
        return _blocked(
            platform, "youtube", reason=artifact_err, transport="youtube_resumable_upload",
            account=account, artifact=artifact, caption=caption,
            restrictions=restrictions, disclosures=disc,
            line="Not a public post. The local file is not available (%s)." % artifact_err,
        )
    import publish_adapters as adapters
    bound_id = str((account or {}).get("external_id") or "").strip()
    if not adapters.youtube_channel_id_ok(bound_id):
        return _blocked(
            platform, "youtube", reason="youtube_channel_unbound",
            transport="youtube_resumable_upload", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions + ["youtube_channel_unbound"],
            disclosures=disc,
            line=(
                "Not sent. This YouTube account has no usable bound channel id. "
                "No resumable session is opened."
            ),
        )
    if disc.get("paid") and not VERIFIED["youtube_has_paid_product_placement"]:
        return _blocked(
            platform, "youtube", reason="youtube_paid_label_unverified",
            transport="youtube_resumable_upload", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions + ["youtube_paid_label_unverified"],
            disclosures=disc,
            line=(
                "Not sent. YouTube hasPaidProductPlacement is not a verified writable "
                "videos.insert field. No resumable session is opened. #ad is not a substitute."
            ),
        )
    existing = _existing_youtube(item, artifact, bound_id)
    if existing and existing.get("corrupt"):
        return _blocked(
            platform, "youtube", reason=existing.get("reason") or "private_ledger_corrupt",
            transport="youtube_resumable_upload", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line="Not sent. A ledger could not be read, so no second YouTube object is created and nothing is promoted.",
        )
    sha = str((artifact or {}).get("sha256") or "")
    vid = str((existing or {}).get("video_id") or "")
    hit_sha = str((existing or {}).get("sha256") or "")
    hit_channel = str((existing or {}).get("channel_id") or "")
    exact = bool(existing and vid and sha and hit_sha == sha and hit_channel == bound_id)
    if existing and not exact:
        reason = existing.get("reason") or "existing_video_reconcile"
        if vid and hit_sha == sha and hit_channel and hit_channel != bound_id:
            reason = "youtube_channel_mismatch"
        return _blocked(
            platform, "youtube", reason=reason,
            transport="youtube_resumable_upload", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line=(
                "Not sent. An existing YouTube object is on the ledger"
                + ((" (" + vid + ")") if vid else "")
                + ". It is not uploaded again, and it is not promoted without an exact channel, file hash, and named id."
            ),
        )
    armed = _armed("youtube", target)
    if exact:
        if not armed:
            return _blocked(
                platform, "youtube", reason="youtube_grant_absent",
                transport="youtube_videos_update", account=account, artifact=artifact,
                caption=caption, restrictions=restrictions, disclosures=disc,
                line="Not sent. Existing video %s is not promoted until the %s grant is present." % (vid, target or "routed"),
            )
        return {
            "platform": platform,
            "key": "youtube",
            "public_action": "promote_existing",
            "will_dispatch": True,
            "reason": None,
            "transport": "youtube_videos_update",
            "account_name": account.get("account_name") or "",
            "account_id": account.get("account_id") or "",
            "external_id": account.get("external_id") or "",
            "existing_video_id": vid,
            "provider": "youtube_data_api",
            "artifact_sha256": sha,
            "artifact_name": (artifact or {}).get("name") or "",
            "caption": caption,
            "restrictions": restrictions,
            "disclosures": disc,
            "grant_channel": target,
            "bound_channel_id": bound_id,
            "line": (
                "PROMOTE existing YouTube video %s on %s. videos.update part=status only, "
                "after confirmation. No second upload, no snippet, no paid field. "
                "A ledger hit alone does not publish."
            ) % (vid, bound_id),
        }
    line_ready = (
        "PRIVATE upload to YouTube · %s (%s). Resumable videos.insert of this exact file "
        "with privacyStatus private and containsSyntheticMedia. Not a public post. "
        "A later public change is a separate confirmed promote. The returned channelId "
        "must match this grant. If the upload is interrupted, a later approval "
        "sends one status query to that session and does not insert the file again."
        % (
            account.get("account_name") or target or "YouTube",
            account.get("external_id") or account.get("account_id") or "",
        )
    )
    if not armed:
        return _blocked(
            platform, "youtube", reason="youtube_grant_absent",
            transport="youtube_resumable_upload", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line=(
                "Not sent. This local file would be a private resumable upload. "
                "Opus project and clip ids are not required. "
                "The %s hub grant is the readiness gate."
            ) % (target or "routed"),
        )
    return {
        "platform": platform,
        "key": "youtube",
        "public_action": "private_upload",
        "will_dispatch": True,
        "reason": None,
        "transport": "youtube_resumable_upload",
        "account_name": account.get("account_name") or "",
        "account_id": account.get("account_id") or "",
        "external_id": account.get("external_id") or "",
        "provider": "youtube_data_api",
        "artifact_sha256": (artifact or {}).get("sha256") or "",
        "artifact_name": (artifact or {}).get("name") or "",
        "caption": caption,
        "restrictions": restrictions,
        "disclosures": disc,
        "line": line_ready,
        "grant_channel": target,
        "bound_channel_id": bound_id,
    }


def _cred(platform):
    raw = credentials() or {}
    row = raw.get(platform) if isinstance(raw, dict) else None
    return row if isinstance(row, dict) else {}


def _tiktok_row(platform, account, artifact, caption, restrictions, disc):
    import publish_adapters as adapters
    cred = _cred("tiktok")
    armed = bool(cred.get("api_key") and cred.get("integration_id")) or callable((external_runners() or {}).get("tiktok"))
    restrictions = restrictions + ["postiz_not_mcp", "tiktok_upload_is_not_publish"]
    if not armed:
        return _blocked(
            platform, "tiktok", reason="postiz_integration_absent",
            transport="postiz_direct_post", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line=(
                "Not sent. TikTok goes through Postiz DIRECT_POST (video_made_with_ai and "
                "brand_content_toggle). UPLOAD is the inbox and is not a publish. "
                + adapters.POSTIZ_BOUNDARY
            ),
        )
    return _blocked(
        platform, "tiktok", reason="disclosure_readback_unverified",
        transport="postiz_direct_post", account=account, artifact=artifact,
        caption=caption, restrictions=restrictions + ["disclosure_readback_unverified"],
        disclosures=disc,
        line=(
            "Not sent. Postiz DIRECT_POST has no documented pre-publish read of "
            "video_made_with_ai or brand_content_toggle. The hub will not publish "
            "publicly to check the label. " + adapters.POSTIZ_BOUNDARY
        ),
    )


def _instagram_row(platform, account, artifact, caption, restrictions, disc):
    cred = _cred("instagram")
    if disc.get("paid") and cred and not cred.get("sponsor_eligible"):
        return _blocked(
            platform, "instagram", reason="instagram_sponsor_eligibility_unverified",
            transport="instagram_resumable_reel", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line=(
                "Not a public post. Paid Instagram needs verified sponsor eligibility. "
                "is_paid_partnership is the toggle. #ad is not."
            ),
        )
    armed = bool(cred.get("access_token") and cred.get("ig_user_id")) or callable((external_runners() or {}).get("instagram"))
    if not armed:
        return _blocked(
            platform, "instagram", reason="instagram_auth_identity_sponsor_unverified",
            transport="instagram_resumable_reel", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line=(
                "Not sent. Adapter is the documented Reel path: media_type=REELS, "
                "upload_type=resumable, rupload of the local file, then media_publish creation_id, "
                "with is_ai_generated and is_paid_partnership. The readiness gate is the Instagram "
                "token, ig user id, and sponsor eligibility. #ad is not the paid toggle."
            ),
        )
    return _blocked(
        platform, "instagram", reason="disclosure_readback_unverified",
        transport="instagram_resumable_reel", account=account, artifact=artifact,
        caption=caption, restrictions=restrictions + ["disclosure_readback_unverified"],
        disclosures=disc,
        line=(
            "Not sent. Instagram has no documented pre-publish read of is_ai_generated "
            "or is_paid_partnership. The hub will not call media_publish to check the label."
        ),
    )


def _facebook_row(platform, account, artifact, caption, restrictions, disc):
    import publish_adapters as adapters
    if disc.get("paid") or not VERIFIED["fb_reels_paid_field"]:
        if disc.get("paid"):
            return _blocked(
                platform, "facebook", reason="facebook_reels_paid_disclosure_not_in_official_schema",
                transport="facebook_video_reels_v27", account=account, artifact=artifact,
                caption=caption, restrictions=restrictions, disclosures=disc,
                line=(
                    "Not a public post. " + adapters.FB_AI_SOURCE +
                    " No paid field is on that reference. Instagram paid fields are not copied. #ad is not a toggle."
                ),
            )
    cred = _cred("facebook")
    armed = bool(cred.get("access_token") and cred.get("page_id")) or callable((external_runners() or {}).get("facebook"))
    if not armed:
        return _blocked(
            platform, "facebook", reason="facebook_reels_auth_absent",
            transport="facebook_video_reels_v27", account=account, artifact=artifact,
            caption=caption, restrictions=restrictions, disclosures=disc,
            line=(
                "Not sent. Adapter is Page Reels v27.0: upload_phase start, rupload of the local file, "
                "finish with video_state PUBLISHED and is_ai_generated. The readiness gate is a Page token. "
                + adapters.FB_AI_SOURCE
            ),
        )
    return _blocked(
        platform, "facebook", reason="disclosure_readback_unverified",
        transport="facebook_video_reels_v27", account=account, artifact=artifact,
        caption=caption, restrictions=restrictions + ["disclosure_readback_unverified"],
        disclosures=disc,
        line=(
            "Not sent. Facebook Reels has no documented pre-publish read of is_ai_generated. "
            "The hub will not finish video_state PUBLISHED to check the label. "
            + adapters.FB_AI_SOURCE
        ),
    )


def _ready_row(platform, key, transport, account, artifact, caption, restrictions, disc):
    return {
        "platform": platform,
        "key": key,
        "public_action": "public_publish",
        "will_dispatch": True,
        "reason": None,
        "transport": transport,
        "account_name": (account or {}).get("account_name") or "",
        "account_id": (account or {}).get("account_id") or "",
        "external_id": (account or {}).get("external_id") or "",
        "provider": (account or {}).get("provider") or transport,
        "artifact_sha256": (artifact or {}).get("sha256") or "",
        "artifact_name": (artifact or {}).get("name") or "",
        "caption": caption,
        "restrictions": restrictions,
        "disclosures": disc,
        "line": "PUBLIC publish to %s · %s (%s) via %s." % (
            platform, (account or {}).get("account_name") or "", (account or {}).get("account_id") or "", transport,
        ),
    }


def build_manifest(item, *, targets=None, root=None, channels=None):
    """Immutable preview. Hash excludes built_at so the same inputs stay stable."""
    if not isinstance(item, dict):
        return {"manifest_hash": "", "platforms": [], "held": False, "record_kind": "refuse",
                "will_dispatch_any": False, "refuse_reason": "bad_item", "summary": "Not a public post."}
    cfg = targets if isinstance(targets, dict) and "targets" in targets else sched.load_targets()
    route = sched.route_for_item(item, targets=cfg, channels=channels) or {}
    artifact, artifact_err = resolve_artifact(item.get("video"), root=root)
    plats = list(item.get("platforms") or [])
    rows = [decide_platform(item, p, route, cfg, artifact, artifact_err) for p in plats]
    held = bool(route.get("held"))
    if route.get("campaign_config") == "absent":
        for r in rows:
            if "campaign_config_absent" not in (r.get("restrictions") or []):
                r["restrictions"] = list(r.get("restrictions") or []) + ["campaign_config_absent"]
            if r.get("will_dispatch") or r.get("public_action") == "not_public":
                r["will_dispatch"] = False
                r["public_action"] = "blocked"
                r["reason"] = "campaign_config_absent"
                r["line"] = (
                    "Not a public post. No campaign_rules entry is configured. "
                    "The hub will not guess a hold or an allow."
                )
    if held:
        for r in rows:
            was_promote = r.get("public_action") == "promote_existing"
            r["will_dispatch"] = False
            if r.get("public_action") in ("public_publish", "private_upload", "promote_existing"):
                r["public_action"] = "blocked"
            r["reason"] = r.get("reason") or route.get("block_reason") or "campaign_held"
            if was_promote:
                vid = str(r.get("existing_video_id") or "")
                r["line"] = (
                    "Not a public post. Promote existing%s is blocked because this campaign is held."
                    % ((" " + vid) if vid else "")
                )
            else:
                r["line"] = "Not a public post. Held campaign is excluded from Approve."
    for r in rows:
        r["row_hash"] = _sha256_bytes(_canon(_row_core(r)).encode())
    manual = (
        not held and not route.get("blocked") and item.get("ai_disclosure") is False
        and bool(rows) and all(
            r.get("public_action") == "not_public" and r.get("reason") == "manual" for r in rows
        )
    )
    will_any = any(r.get("will_dispatch") for r in rows)
    if held:
        record_kind = "held"
        refuse = route.get("block_reason") or "campaign_held"
        summary = "Not a public post. Held campaign is excluded from Approve."
    elif route.get("blocked") and not rows:
        record_kind = "blocked"
        refuse = route.get("block_reason") or "route_blocked"
        summary = "Not a public post. " + str(refuse)
    elif will_any:
        record_kind = "dispatch"
        refuse = None
        summary = " ".join(r["line"] for r in rows if r.get("will_dispatch"))
    elif manual:
        record_kind = "manual"
        refuse = None
        summary = "Not a public post. Marks ready · you post manually."
    else:
        record_kind = "blocked"
        reasons = [r["reason"] for r in rows if r.get("reason")]
        refuse = reasons[0] if reasons else (route.get("block_reason") or "nothing_to_publish")
        summary = " ".join(r["line"] for r in rows) if rows else "Not a public post. Nothing to publish."
    core = {
        "id": str(item.get("id") or "")[:64],
        "target": route.get("target") or "",
        "held": held,
        "campaign_config": route.get("campaign_config") or "",
        "record_kind": record_kind,
        "artifact_sha256": (artifact or {}).get("sha256") or "",
        "platforms": [
            {
                "platform": r["platform"],
                "key": r["key"],
                "public_action": r["public_action"],
                "will_dispatch": r["will_dispatch"],
                "reason": r["reason"],
                "transport": r["transport"],
                "account_name": r["account_name"],
                "account_id": r["account_id"],
                "external_id": r.get("external_id") or "",
                "provider": r["provider"],
                "artifact_sha256": r["artifact_sha256"],
                "caption": r["caption"],
                "restrictions": r["restrictions"],
                "disclosures": r["disclosures"],
                "row_hash": r["row_hash"],
            }
            for r in rows
        ],
    }
    out = {
        "manifest_hash": _sha256_bytes(_canon(core).encode()),
        "held": held,
        "record_kind": record_kind,
        "refuse_reason": refuse,
        "will_dispatch_any": will_any,
        "summary": summary[:900],
        "route_target": route.get("target") or "",
        "route_blocked": bool(route.get("blocked")),
        "block_reason": route.get("block_reason") or "",
        "campaign_config": route.get("campaign_config") or "",
        "platforms": rows,
        "ui_kind": "held" if held else ("public" if will_any else ("manual" if record_kind == "manual" else "blocked")),
    }
    return out


def _row_core(r):
    return {
        "platform": r.get("platform"),
        "key": r.get("key"),
        "account_id": r.get("account_id"),
        "external_id": r.get("external_id") or "",
        "existing_video_id": r.get("existing_video_id") or "",
        "artifact_sha256": r.get("artifact_sha256"),
        "caption": r.get("caption"),
        "public_action": r.get("public_action"),
        "will_dispatch": r.get("will_dispatch"),
        "transport": r.get("transport"),
        "reason": r.get("reason"),
        "disclosures": r.get("disclosures"),
        "restrictions": r.get("restrictions"),
    }


def _rows_authorized(manifest, platform_rows):
    if not isinstance(platform_rows, list):
        return False
    got = {}
    for entry in platform_rows:
        if isinstance(entry, dict):
            got[str(entry.get("key") or "")] = str(entry.get("row_hash") or "")
    for row in manifest.get("platforms") or []:
        if got.get(str(row.get("key") or "")) != str(row.get("row_hash") or ""):
            return False
    return True


POLICY_TERMINAL = frozenset({
    "youtube_paid_not_confirmed",
    "youtube_synthetic_not_confirmed",
    "youtube_privacy_not_public",
    "youtube_channel_mismatch",
    "youtube_video_missing_channel_id",
    "youtube_privacy_not_private",
    "youtube_promote_incomplete",
})


def _existing_youtube(item, artifact, channel_id):
    """Read-only cross-ledger check. Never writes approvals or the public ledger."""
    try:
        from tools.private_proof import find_existing_youtube
    except Exception:
        return {"corrupt": True, "reason": "private_ledger_corrupt"}
    return find_existing_youtube(
        item_id=str((item or {}).get("id") or ""),
        sha256=str((artifact or {}).get("sha256") or ""),
        channel_id=str(channel_id or ""),
    )


def record_disclosure_evidence(evidence, *, path):
    """Store an explicit human disclosure note. It does not confirm an API echo.

    source must be human_studio_confirmation plus a statement, video id, and
    item id. ai_disclosure on a queue item is not evidence and is not inferred.
    """
    refused = {"ok": False, "confirms_echo": False, "public_success": False, "reason": "evidence_not_explicit"}
    if not isinstance(evidence, dict) or evidence.get("source") != "human_studio_confirmation":
        return refused
    statement = str(evidence.get("statement") or "").strip()
    video_id = str(evidence.get("video_id") or "").strip()
    item_id = str(evidence.get("item_id") or "").strip()
    if not statement or not video_id or not item_id:
        return refused
    dest = Path(path)
    if dest.name != "disclosure_evidence.jsonl" or dest.is_symlink():
        return dict(refused, reason="evidence_path_rejected")
    row = {
        "video_id": video_id[:64],
        "item_id": item_id[:64],
        "source": "human_studio_confirmation",
        "statement": statement[:300],
        "confirms_echo": False,
        "public_success": False,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return {"ok": True, "confirms_echo": False, "public_success": False, "recorded": row}


def summary_line(item, **kwargs) -> str:
    return build_manifest(item, **kwargs).get("summary") or "Not a public post."


def _classify_runner(res, exc):
    """Return status, reason, permalink, remote_id.

    A policy error on an accepted create keeps that error and the remote id.
    create_error is terminal: begin() will not retry it. Timeout without a
    policy error stays unknown and must be reconciled.
    """
    if exc is not None:
        text = str(exc)
        if isinstance(exc, URLError) and not isinstance(exc, HTTPError):
            return "unknown", "transport_uncertain", None, None
        if isinstance(exc, TimeoutError) or "timeout" in text.lower():
            return "unknown", "timeout", None, None
        return "failed", text[:200], None, None
    if not isinstance(res, dict):
        return "unknown", "bad_response", None, None
    err = str(res.get("error") or res.get("reason") or "")
    permalink = str(res.get("permalink") or "")[:300]
    video_id = str(res.get("video_id") or "")[:64]
    remote = idem.stored_remote(video_id or res.get("remote_id"))
    if not permalink and video_id and res.get("ok") and res.get("youtube_label"):
        permalink = "https://www.youtube.com/watch?v=" + video_id
    if err == "youtube_synthetic_echo_omitted":
        return "unknown", err[:200], None, remote
    if err in POLICY_TERMINAL:
        return "create_error", err[:200], None, remote
    if err in ("transport_uncertain", "youtube_channel_unproven", "upload_incomplete") or "timeout" in err.lower():
        return "unknown", err[:200], None, remote
    if res.get("private_uploaded") and remote:
        return "private_uploaded", None, None, remote
    if res.get("accepted") and not permalink:
        return "unknown", "accepted_without_permalink", None, remote
    if res.get("ok") and permalink:
        return "done", None, permalink, remote
    if res.get("ok") and not permalink:
        return "unknown", "accepted_without_permalink", None, remote
    return "failed", (err or "dispatch_failed")[:200], None, remote


def _call_adapter(item, row):
    import publish_adapters as adapters
    runners = external_runners() or {}
    fn = runners.get(row.get("key"))
    if callable(fn):
        return fn(item, row)
    data = adapters.read_local(row.get("artifact_name") or "", ROOT)
    if data is None:
        return {"ok": False, "called": False, "reason": "media_missing", "error": "media_missing"}
    key = row.get("key")
    cred = _cred(key if key != "tiktok" else "tiktok")
    if key == "youtube":
        return adapters.youtube_upload(
            item, row, token=youtube_token(row.get("grant_channel") or ""),
            http=adapters._http(), file_bytes=data,
            expected_channel_id=row.get("bound_channel_id") or "",
        )
    if key == "instagram":
        return adapters.instagram_reel(
            item, row, ig_user_id=cred.get("ig_user_id"), token=cred.get("access_token"),
            sponsor_eligible=bool(cred.get("sponsor_eligible")), http=adapters._http(), file_bytes=data,
        )
    if key == "facebook":
        return adapters.facebook_reel(
            item, row, page_id=cred.get("page_id"), token=cred.get("access_token"),
            http=adapters._http(), file_bytes=data,
        )
    if key == "tiktok":
        return adapters.postiz_tiktok(
            item, row, api_key=cred.get("api_key"), integration_id=cred.get("integration_id"),
            http=adapters._http(), file_bytes=data, filename=row.get("artifact_name") or "clip.mp4",
        )
    return {"ok": False, "called": False, "reason": "no_adapter", "error": "no_adapter"}


def _visible_remote_id(value):
    """Video ids may be shown. Session URLs stay in the private ledger only."""
    text = str(value or "").strip()
    if not text or text.startswith("http://") or text.startswith("https://") or "upload_id" in text:
        return None
    return text[:128]


def _reconcile_private_upload(item, row, existing, *, ledger_path, job_id, key):
    """One status query of a stored session. Never starts a new upload or a promotion."""
    import publish_adapters as adapters
    hidden = {
        "key": row.get("key"),
        "platform": row.get("platform"),
        "status": "unknown",
        "reason": "reconcile_required",
        "reposted": False,
        "called": False,
        "remote_id": None,
        "skipped_idempotent": True,
        "public_action": "private_upload",
    }
    session = idem.session_of(existing)
    if not adapters.youtube_put_location_ok(session):
        return hidden
    token = youtube_token(row.get("grant_channel") or "")
    if not token:
        return hidden
    http = adapters._http() or adapters.youtube_insert_http
    res = adapters.youtube_session_status(
        session,
        token=token,
        http=http,
        file_size=(existing or {}).get("upload_length"),
        expected_channel_id=row.get("bound_channel_id") or "",
        ai=bool((row.get("disclosures") or {}).get("ai")),
    )
    status, reason, _permalink, remote_id = _classify_runner(res, None)
    visible = _visible_remote_id(remote_id)
    sha = row.get("artifact_sha256") or ""
    acct = row.get("account_id") or ""
    base = {
        "key": row.get("key"),
        "platform": row.get("platform"),
        "status": status,
        "reason": reason,
        "reposted": False,
        "called": bool((res or {}).get("called")),
        "remote_id": visible,
        "public_action": "private_upload",
    }
    if status == "private_uploaded" and visible:
        recorded = {
            "key": idem.make_key(job_id, key),
            "job_id": str(job_id)[:64],
            "platform": key,
            "status": "private_uploaded",
            "action": "private_upload",
            "remote_id": visible,
            "video_id": visible,
            "item_id": str(item.get("id") or "")[:64],
            "artifact_sha256": sha or None,
            "account_id": acct or None,
            "channel_id": str(row.get("bound_channel_id") or "")[:64],
            "privacy_to": "private",
            "synthetic_write": bool((row.get("disclosures") or {}).get("ai")),
            "echo": "present" if (res or {}).get("youtube_label") else "unconfirmed",
            "error": None,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        if idem.is_session_url(session):
            recorded["session_url"] = session
        idem.append_row(recorded, path=ledger_path)
        return dict(base, status_query=True)
    if status == "create_error" and visible:
        idem.mark_create_error(
            job_id, key, error=reason, path=ledger_path, remote_id=visible,
            artifact_sha=sha, account_id=acct,
        )
        return dict(base, status_query=True)
    if reason == "upload_incomplete":
        length = (existing or {}).get("upload_length")
        idem.mark_unknown(
            job_id, key, error="upload_incomplete", path=ledger_path,
            remote_id=session, artifact_sha=sha, account_id=acct,
            upload_length=length if isinstance(length, int) and not isinstance(length, bool) else None,
            session_observation="upload_incomplete",
        )
        return dict(
            hidden, reason="upload_incomplete", called=True, status_query=True,
        )
    if status == "unknown" and visible:
        idem.mark_unknown(
            job_id, key, error=reason, path=ledger_path, video_id=visible,
            session_url=session, artifact_sha=sha, account_id=acct,
        )
        return dict(base, status_query=True)
    queried = bool((res or {}).get("called"))
    return dict(hidden, reason=reason or "reconcile_required", called=queried, status_query=queried)


def dispatch_platform(item, row, *, ledger_path=None, runner=None):
    """One platform. A done artifact is not posted again without repost permission.

    An unknown row stays in reconcile even if the caption, and therefore the
    manifest hash, changed. The public flag gates this entry: calling it
    directly does not upload while the flag is off.
    """
    if not enabled():
        return {
            "key": row.get("key") if isinstance(row, dict) else None,
            "platform": (row or {}).get("platform") if isinstance(row, dict) else None,
            "status": "blocked",
            "reason": "public_publish_off",
            "called": False,
            "reposted": False,
        }
    key = LEDGER_KEY.get(row.get("key") or "", "")
    job_id = str(item.get("id") or "")
    if not key or not idem.validate_job_id(job_id):
        return {"key": row.get("key"), "status": "blocked", "reason": "bad_job_id", "reposted": False}
    promote = row.get("public_action") == "promote_existing"
    if row.get("public_action") not in ("public_publish", "private_upload", "promote_existing") or not row.get("will_dispatch"):
        return {
            "key": row.get("key"),
            "platform": row.get("platform"),
            "status": row.get("public_action") or "blocked",
            "reason": row.get("reason"),
            "reposted": False,
            "called": False,
        }
    obj_lock = None
    if row.get("key") == "youtube":
        from tools.private_proof import _lock_objects, _unlock_objects
        obj_lock, obj_err = _lock_objects()
        if obj_err or obj_lock is None:
            return {
                "key": row.get("key"), "platform": row.get("platform"),
                "status": "blocked", "reason": obj_err or "youtube_object_lock_unavailable",
                "called": False, "reposted": False,
            }
        if not promote:
            import ledger_dedupe as _dedupe
            gate = _dedupe.check_upload(
                item, sha256=str(row.get("artifact_sha256") or ""),
                channel_id=str(row.get("bound_channel_id") or ""),
            )
            if gate.get("action") != "proceed":
                _unlock_objects(obj_lock)
                obj_lock = None
                failed = gate.get("action") == "fail"
                return {
                    "key": row.get("key"), "platform": row.get("platform"),
                    "status": "blocked" if failed else "skipped",
                    "reason": gate.get("reason") or ("ledger_unreadable" if failed else ""),
                    "remote_id": None if failed else gate.get("video_id"),
                    "called": False, "reposted": False,
                }
        hit = _existing_youtube(item, {"sha256": row.get("artifact_sha256") or ""}, row.get("bound_channel_id"))
        named = str(row.get("existing_video_id") or "")
        sha = str(row.get("artifact_sha256") or "")
        bound = str(row.get("bound_channel_id") or "")
        exact = bool(
            hit and hit.get("video_id") and named and hit.get("video_id") == named
            and hit.get("sha256") == sha and hit.get("channel_id") == bound
        )
        if hit and hit.get("corrupt"):
            _unlock_objects(obj_lock)
            return {
                "key": row.get("key"), "platform": row.get("platform"),
                "status": "blocked", "reason": hit.get("reason") or "private_ledger_corrupt",
                "called": False, "reposted": False,
            }
        if promote and not exact:
            _unlock_objects(obj_lock)
            mismatch = bool(hit and hit.get("sha256") == sha and hit.get("channel_id") and hit.get("channel_id") != bound)
            return {
                "key": row.get("key"),
                "platform": row.get("platform"),
                "status": "blocked",
                "reason": "youtube_channel_mismatch" if mismatch else "existing_video_reconcile",
                "remote_id": (hit or {}).get("video_id"),
                "called": False,
                "reposted": False,
            }
        if not promote and hit and (hit.get("video_id") or hit.get("blocked")):
            _unlock_objects(obj_lock)
            return {
                "key": row.get("key"),
                "platform": row.get("platform"),
                "status": "unknown" if hit.get("video_id") else "blocked",
                "reason": "youtube_channel_mismatch" if (
                    hit.get("video_id") and hit.get("sha256") == sha and hit.get("channel_id") and hit.get("channel_id") != bound
                ) else (hit.get("reason") or "existing_video_reconcile"),
                "remote_id": hit.get("video_id"),
                "called": False,
                "reposted": False,
            }
        if promote:
            key = PROMOTE_LEDGER_KEY
    try:
        repost = item.get("repost") is True
        acquired, existing = idem.begin(
            job_id, key, path=ledger_path, repost=repost,
            artifact_sha=row.get("artifact_sha256") or "",
            account_id=row.get("account_id") or "",
        )
        if not acquired:
            st = (existing or {}).get("status")
            if (existing or {}).get("ledger_corrupt") or st == "ledger_corrupt":
                return {
                    "key": row.get("key"),
                    "platform": row.get("platform"),
                    "status": "blocked",
                    "reason": "public_ledger_corrupt",
                    "reposted": False,
                    "called": False,
                }
            if st in ("unknown", "timeout_pending") and not promote:
                import publish_adapters as adapters
                if adapters.youtube_put_location_ok(idem.session_of(existing)):
                    return _reconcile_private_upload(
                        item, row, existing, ledger_path=ledger_path, job_id=job_id, key=key,
                    )
            if (existing or {}).get("reconcile_required") or st in ("unknown", "timeout_pending", "in_flight"):
                reason = "reconcile_required"
            elif (existing or {}).get("duplicate_artifact") or st == "done":
                reason = "duplicate_publication_repost_required"
            elif st == "create_error":
                reason = "create_error_terminal"
            else:
                reason = "idempotent"
            out = {
                "key": row.get("key"),
                "platform": row.get("platform"),
                "status": st or "blocked",
                "reason": reason,
                "reposted": False,
                "called": False,
                "permalink": (existing or {}).get("permalink") or (existing or {}).get("opus_post_id"),
                "remote_id": _visible_remote_id((existing or {}).get("video_id") or (existing or {}).get("remote_id")),
                "skipped_idempotent": True,
            }
            if promote or (existing or {}).get("action") == "promote_existing":
                out["public_action"] = "promote_existing"
            return out
        if promote:
            import publish_adapters as adapters

            def fn(item, row):
                # The test double wins when a test installed one. Production
                # leaves HTTP unset and uses the stdlib YouTube client.
                http = adapters._http() or adapters.youtube_promote_http
                return adapters.youtube_promote_existing(
                    item, row, token=youtube_token(row.get("grant_channel") or ""),
                    http=http, expected_channel_id=row.get("bound_channel_id") or "",
                    video_id=row.get("existing_video_id") or "",
                )
        else:
            fn = runner if runner is not None else _call_adapter
        exc = None
        res = None
        try:
            res = fn(item, row)
        except Exception as e:
            exc = e
        if isinstance(res, dict) and res.get("called") is False:
            idem.mark_failed(job_id, key, error=res.get("reason") or "not_called", path=ledger_path)
            return {
                "key": row.get("key"), "platform": row.get("platform"), "status": "blocked",
                "reason": res.get("reason"), "called": False, "reposted": False,
            }
        status, reason, permalink, remote_id = _classify_runner(res, exc)
        sha = row.get("artifact_sha256") or ""
        acct = row.get("account_id") or ""
        if promote and isinstance(res, dict) and res.get("called"):
            idem.append_row({
                "key": idem.make_key(job_id, key),
                "job_id": str(job_id)[:64],
                "platform": key,
                "status": status,
                "action": "promote_existing",
                "remote_id": remote_id,
                "video_id": str((res or {}).get("video_id") or remote_id or "")[:64],
                "item_id": str(item.get("id") or "")[:64],
                "artifact_sha256": sha or None,
                "account_id": acct or None,
                "channel_id": str(row.get("bound_channel_id") or "")[:64],
                "privacy_from": str((res or {}).get("privacy_from") or "")[:16],
                "privacy_to": "public",
                "mutation": bool((res or {}).get("mutation")),
                "synthetic_write": bool(((row.get("disclosures") or {}).get("ai"))),
                "echo": "absent" if (res or {}).get("echo_omitted") else ("present" if status == "done" else "unconfirmed"),
                "http_status": (res or {}).get("http_status"),
                "permalink": permalink,
                "error": reason,
                "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }, path=ledger_path)
        elif status == "unknown":
            length = (res or {}).get("upload_length") if isinstance(res, dict) else None
            idem.mark_unknown(
                job_id, key, error=reason, path=ledger_path,
                remote_id=remote_id, artifact_sha=sha, account_id=acct,
                upload_length=length if isinstance(length, int) else None,
                session_observation="upload_incomplete" if reason == "upload_incomplete" else None,
                video_id=(res or {}).get("video_id") if isinstance(res, dict) else None,
                session_url=(res or {}).get("session_url") if isinstance(res, dict) else None,
            )
        elif status == "private_uploaded":
            uploaded = {
                "key": idem.make_key(job_id, key),
                "job_id": str(job_id)[:64],
                "platform": key,
                "status": "private_uploaded",
                "action": "private_upload",
                "remote_id": remote_id,
                "video_id": remote_id,
                "item_id": str(item.get("id") or "")[:64],
                "artifact_sha256": sha or None,
                "account_id": acct or None,
                "channel_id": str(row.get("bound_channel_id") or "")[:64],
                "privacy_to": "private",
                "synthetic_write": bool((row.get("disclosures") or {}).get("ai")),
                "echo": "present" if (res or {}).get("youtube_label") else "unconfirmed",
                "error": None,
                "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            session_kept = (res or {}).get("session_url") if isinstance(res, dict) else None
            if idem.is_session_url(session_kept):
                uploaded["session_url"] = session_kept
            idem.append_row(uploaded, path=ledger_path)
        elif status == "done":
            idem.mark_done(job_id, key, opus_post_id=permalink, path=ledger_path, artifact_sha=sha, account_id=acct)
        elif status == "create_error":
            idem.mark_create_error(
                job_id, key, error=reason, path=ledger_path, remote_id=remote_id,
                artifact_sha=sha, account_id=acct,
                video_id=(res or {}).get("video_id") if isinstance(res, dict) else None,
                session_url=(res or {}).get("session_url") if isinstance(res, dict) else None,
            )
        else:
            idem.mark_failed(job_id, key, error=reason, path=ledger_path)
        return {
            "key": row.get("key"),
            "platform": row.get("platform"),
            "status": status,
            "reason": reason,
            "permalink": permalink,
            "remote_id": _visible_remote_id(remote_id),
            "called": True,
            "reposted": False,
            "status_query": False,
            "later_status_query": isinstance(remote_id, str) and remote_id.startswith("https://"),
            "public_action": (
                "promote_existing" if promote else (
                    "private_upload" if status == "private_uploaded" or row.get("public_action") == "private_upload"
                    else ("public_publish" if status == "done" else status)
                )
            ),
        }
    finally:
        if obj_lock is not None:
            from tools.private_proof import _unlock_objects
            _unlock_objects(obj_lock)


def dispatch_item(item, manifest_hash, *, platform_rows=None, targets=None, ledger_path=None, root=None, channels=None):
    """Confirm the item hash and each platform row hash, then dispatch armed rows.

    One item hash does not authorize every platform. The flag gates this entry
    the same way it gates dispatch_platform.
    """
    if not enabled():
        return {
            "ok": False, "error": "public_publish_off", "dispatched": False,
            "called": False, "platforms": [],
        }
    manifest = build_manifest(item, targets=targets, root=root, channels=channels)
    if str(manifest_hash or "") != manifest.get("manifest_hash"):
        return {
            "ok": False,
            "error": "manifest_stale",
            "dispatched": False,
            "platforms": [],
            "manifest_hash": manifest.get("manifest_hash"),
        }
    if not _rows_authorized(manifest, platform_rows):
        return {
            "ok": False, "error": "platform_not_confirmed", "dispatched": False,
            "called": False, "platforms": [],
        }
    if manifest.get("route_blocked"):
        return {
            "ok": False,
            "error": "route_blocked:" + str(manifest.get("block_reason") or ""),
            "dispatched": False,
            "called": False,
            "platforms": [
                {"platform": r["platform"], "status": "blocked", "reason": r.get("reason"), "called": False}
                for r in manifest["platforms"]
            ],
        }
    if manifest.get("held"):
        return {"ok": False, "error": "campaign_held", "dispatched": False, "platforms": []}
    if manifest.get("record_kind") == "manual":
        return {
            "ok": True,
            "dispatched": False,
            "kind": "manual",
            "error": None,
            "platforms": [{"platform": r["platform"], "status": "not_public", "reason": "manual", "called": False} for r in manifest["platforms"]],
        }
    if not manifest.get("will_dispatch_any"):
        return {
            "ok": False,
            "error": "nothing_to_publish:" + str(manifest.get("refuse_reason") or ""),
            "dispatched": False,
            "platforms": [
                {"platform": r["platform"], "status": r["public_action"], "reason": r["reason"], "called": False}
                for r in manifest["platforms"]
            ],
        }
    results = []
    for row in manifest["platforms"]:
        results.append(dispatch_platform(item, row, ledger_path=ledger_path))
    unknown = [r for r in results if r.get("status") == "unknown"]
    failed = [r for r in results if r.get("status") in ("failed", "create_error")]
    done = [r for r in results if r.get("status") == "done"]
    blocked = [r for r in results if r.get("status") in ("blocked", "not_public")]
    return {
        "ok": bool(done) and not unknown and not failed,
        "dispatched": True,
        "partial": bool(done) and bool(unknown or failed or blocked),
        "error": None if done and not unknown and not failed else (
            "pending_reconcile" if unknown else (failed[0].get("reason") if failed else None)
        ),
        "platforms": results,
        "permalinks": [r.get("permalink") for r in done if r.get("permalink")],
    }
