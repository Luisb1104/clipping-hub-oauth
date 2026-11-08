"""One Approve → each designated platform once (idempotent). Flag: CLIP_YOUTUBE_LABEL_STEP.

YouTube: existing private → label → public via youtube_label_step.
TikTok/IG/FB when AI disclosure: needs_manual_label (no Opus private+label API) — push, do not auto-post.
Postiz: not connected — never called.
"""
from __future__ import annotations

import os
import time

import platform_capabilities as caps
import post_idempotency as idem
import schedule_hook as sched
import youtube_label_step as yls

FLAG = yls.FLAG


def enabled(env=None):
    return yls.enabled(env)


def notify_manual_label(item, platforms, *, push_fn=None):
    try:
        name = (item.get("title") or item.get("id") or "clip")[:60]
        plats = ", ".join(platforms) or "platforms"
        title = "Manual AI label needed"
        body = (
            f"{name}: {plats} cannot be auto-posted private+labeled via Opus. "
            f"Set the AI label in-app, then publish. "
            f"TikTok: {yls.TIKTOK_LABEL_HELP} · IG: {yls.IG_LABEL_HELP}"
        )
        if push_fn:
            return bool(push_fn(title, body, key=f"manual-label:{item.get('id')}"))
        import push_alerts as _push
        return bool(_push.send_ntfy(title, body, key=f"manual-label:{item.get('id')}", tags="label", priority="high"))
    except Exception:
        return False


def publish_after_approve(
    item,
    *,
    env=None,
    ledger_path=None,
    youtube_runner=None,
    push_fn=None,
    targets=None,
):
    """Run multi-platform plan. Returns dict with per-platform results.
    Never double-posts: ledger key job_id::platform.
    """
    out = {
        "ok": False,
        "skipped": False,
        "platforms": [],
        "error": None,
        "oauth_url": None,
    }
    if not enabled(env):
        out["skipped"] = True
        out["ok"] = True
        return out
    if not isinstance(item, dict):
        out["error"] = "bad_item"
        return out

    route = sched.route_for_item(item, targets=targets) or {}
    if route.get("blocked"):
        out["error"] = "route_blocked:" + str(route.get("block_reason") or "")
        yls.notify_fail(item, out["error"], push_fn=push_fn)
        return out
    if (route.get("target") or "MAIN") not in yls.GRANT_CHANNELS:
        # MAIN, PAID, and GAMING are the hub grant channels. Any other target stays manual.
        out["error"] = "no_hub_grant_for_target:" + str(route.get("target"))[:16]
        yls.notify_fail(item, out["error"], push_fn=push_fn)
        return out

    job_id = str(item.get("id") or "").strip()
    if not job_id:
        out["error"] = "missing_id"
        return out

    ai_on = sched.parse_ai_disclosure(item, default=True)
    plan = caps.plan_platforms(item, ai_disclosure=ai_on)
    # Storyblocks non-MAIN YouTube is already route_blocked above, including
    # when CLIP_YOUTUBE_LABEL_STEP is the caller. Facebook is not stripped here.

    manual = []
    any_fail = False
    youtube_ok = False

    for step in plan:
        prow = {
            "platform": step["platform"],
            "key": step["key"],
            "action": step["action"],
            "status": None,
            "opus_post_id": None,
            "skipped_idempotent": False,
            "error": None,
        }
        action = step["action"]

        if action == "skip":
            prow["status"] = "skipped"
            prow["error"] = step.get("reason")
            out["platforms"].append(prow)
            continue

        if action == "needs_manual_label":
            acquired, existing = idem.begin(job_id, step["key"] + ":manual", path=ledger_path)
            if not acquired and existing and existing.get("status") == "done":
                prow["status"] = "needs_manual_label"
                prow["skipped_idempotent"] = True
            else:
                manual.append(step["platform"])
                prow["status"] = "needs_manual_label"
                if acquired:
                    idem.mark_done(job_id, step["key"] + ":manual", opus_post_id=None, path=ledger_path)
            out["platforms"].append(prow)
            continue

        # youtube_flow or opus_post — idempotent lock
        acquired, existing = idem.begin(job_id, step["key"], path=ledger_path)
        if not acquired:
            prow["skipped_idempotent"] = True
            prow["status"] = existing.get("status") if existing else "blocked"
            prow["opus_post_id"] = (existing or {}).get("opus_post_id")
            out["platforms"].append(prow)
            if existing and existing.get("status") == "done" and step["key"] == "youtube":
                youtube_ok = True
            continue

        try:
            if action == "youtube_flow":
                runner = youtube_runner or yls.run_after_approve
                # Avoid nested multi-plan: call YT path only (runner is full run_after_approve —
                # pass a thin wrapper in tests). Production: run_after_approve does YT+opus.
                res = runner(item, env=env or os.environ, push_fn=push_fn)
                if res.get("skipped"):
                    prow["status"] = "skipped"
                elif res.get("need_oauth"):
                    prow["status"] = "need_oauth"
                    prow["error"] = res.get("error")
                    oauth = res.get("oauth_url") or res.get("auth_url")
                    if oauth:
                        out["oauth_url"] = oauth
                        prow["oauth_url"] = oauth
                    any_fail = True
                    # Soft-fail ledger so a post-grant Approve can retry (never leave fresh in_flight).
                    idem.mark_failed(job_id, step["key"], error=prow["error"] or "need_oauth", path=ledger_path)
                elif res.get("ok") and res.get("youtube_label"):
                    prow["status"] = "done"
                    prow["opus_post_id"] = res.get("video_id")  # YT id recorded
                    youtube_ok = True
                    idem.mark_done(job_id, step["key"], opus_post_id=prow["opus_post_id"], path=ledger_path)
                else:
                    prow["status"] = "failed"
                    prow["error"] = res.get("error") or "youtube_failed"
                    any_fail = True
                    idem.mark_failed(job_id, step["key"], error=prow["error"], path=ledger_path)
            else:
                # Non-YouTube auto opus_post (only when AI off / future private modes)
                prow["status"] = "failed"
                prow["error"] = "opus_auto_post_not_enabled_for_platform"
                any_fail = True
                idem.mark_failed(job_id, step["key"], error=prow["error"], path=ledger_path)
        except Exception as e:
            prow["status"] = "failed"
            prow["error"] = str(e)[:200]
            any_fail = True
            idem.mark_failed(job_id, step["key"], error=prow["error"], path=ledger_path)

        out["platforms"].append(prow)

    if manual:
        notify_manual_label(item, manual, push_fn=push_fn)

    out["ok"] = not any_fail
    # Partial: some platforms done, some failed — ok False but ledger allows retry on failed only
    return out
