"""Non-publishing readiness report. Reads config and prints counts. Writes nothing."""
from __future__ import annotations

import json
import os
import sys

import public_publish as pub
import publish_runtime as runtime
import schedule_hook as sched


def _grant_line(channel):
    status = pub.youtube_grant_status(channel)
    if status.get("present") and status.get("bound"):
        return "hub grant for %s is on file and matches the legacy channel id" % channel
    if status.get("present"):
        return "hub grant for %s is on file but is not bound to the legacy channel id" % channel
    return "hub grant for %s is not on file" % channel


def accounts_diagnostic(cfg, target, key):
    """Explain a missing accounts map without copying a legacy binding into it."""
    bucket = ((cfg or {}).get("targets") or {}).get(target) or {}
    yt = str(bucket.get("yt") or "")
    parts = [
        "Public accounts map is not configured for %s." % (target or "?"),
        "The legacy target binding was not copied.",
    ]
    if key == "youtube" and yt:
        parts.append("Legacy YouTube channel id on that target is %s." % yt)
        parts.append(_grant_line(target) + ".")
    parts.append("Add the accounts row explicitly. This report does not write it.")
    return " ".join(parts)


def campaign_policy_view(item, cfg):
    """Policy from campaign_rules. Status does not create or clear a hold."""
    if not isinstance(item, dict):
        return {"state": "not_campaign"}
    cid = str(item.get("campaign_id") or "").strip()
    is_ad = item.get("is_ad") is True or str(item.get("is_ad") or "").strip().lower() in ("1", "true", "yes", "on")
    if not cid and not is_ad:
        return {"state": "not_campaign"}
    rule = sched.campaign_rule_for(item, cfg)
    if not isinstance(rule, dict):
        return {"state": "absent", "campaign_id": cid}
    if rule.get("hold"):
        return {"state": "held", "campaign_id": cid, "reason": rule.get("reason") or "campaign_held"}
    return {
        "state": "configured",
        "campaign_id": cid,
        "deny_platforms": list(rule.get("deny_platforms") or []),
        "reason": rule.get("reason") or "",
    }


def _platform_status():
    names = set(runtime.configured_platform_names())
    problems = list(runtime._STATE.get("problems") or [])
    def one(name, blocked):
        if name in names:
            return {"configured": True, "automatic_public": False, "blocker": blocked}
        hit = [p["problem"] for p in problems if p.get("platform") == name]
        return {"configured": False, "automatic_public": False, "blocker": hit[0] if hit else "config_absent"}
    return {
        "youtube": {
            "automatic_public": False,
            "blocker": "paid_field_unverified_and_accounts_map_required",
        },
        "instagram": one("instagram", "disclosure_readback_unverified"),
        "facebook": one("facebook", "paid_field_absent_and_disclosure_readback_unverified"),
        "tiktok": one("tiktok", "disclosure_readback_unverified_and_postiz_not_automatic"),
    }


def report(items, *, targets=None, channels=None, public_enabled=None):
    """Counts and next steps. Does not approve, post, or certify rights."""
    cfg = targets if isinstance(targets, dict) and "targets" in targets else sched.load_targets()
    flag = pub.enabled() if public_enabled is None else bool(public_enabled)
    rows = []
    reasons = {}
    held_ids = []
    absent_ids = []
    blocked_ids = []
    manual_ids = []
    dispatch_ids = []
    change_requested = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        policy = campaign_policy_view(item, cfg)
        manifest = pub.build_manifest(item, targets=cfg, channels=channels) if flag else None
        status = str(item.get("status") or "")
        entry = {
            "id": str(item.get("id") or "")[:64],
            "status": status,
            "campaign_policy": policy,
            "rights_ok": item.get("rights_ok") is True,
            "campaign_terms_ok": item.get("campaign_terms_ok") is True,
        }
        if status == "change_requested":
            change_requested.append(entry["id"])
        if policy.get("state") == "held":
            held_ids.append(entry["id"])
        if policy.get("state") == "absent":
            absent_ids.append(entry["id"])
        if manifest:
            entry["record_kind"] = manifest.get("record_kind")
            entry["ui_kind"] = manifest.get("ui_kind")
            entry["will_dispatch_any"] = bool(manifest.get("will_dispatch_any"))
            entry["platforms"] = [
                {"key": r.get("key"), "reason": r.get("reason"), "will_dispatch": r.get("will_dispatch"),
                 "public_action": r.get("public_action"), "restrictions": r.get("restrictions") or []}
                for r in manifest.get("platforms") or []
            ]
            kind = manifest.get("record_kind")
            if kind == "manual" and manifest.get("ui_kind") == "manual":
                manual_ids.append(entry["id"])
            elif kind == "dispatch" and manifest.get("will_dispatch_any") and manifest.get("ui_kind") == "public":
                dispatch_ids.append(entry["id"])
            else:
                blocked_ids.append(entry["id"])
            for plat in entry["platforms"]:
                reason = plat.get("reason") or "none"
                reasons[reason] = reasons.get(reason, 0) + 1
        rows.append(entry)
    accounts_present = isinstance(cfg.get("accounts"), dict) and bool(cfg.get("accounts"))
    steps = []
    if not accounts_present:
        steps.append("Accounts map is absent. Legacy channel bindings were not migrated. Add accounts explicitly before any public YouTube row can be ready.")
    if absent_ids:
        steps.append("Campaign policy is absent for: %s. The hub will not guess a hold or an allow." % ", ".join(absent_ids))
    if any(not r.get("rights_ok") for r in rows):
        steps.append("rights_ok is not set on every clip. It is not certified automatically.")
    if any(r.get("campaign_policy", {}).get("state") != "not_campaign" and not r.get("campaign_terms_ok") for r in rows):
        steps.append("campaign_terms_ok is not set on every campaign clip. It is not certified automatically.")
    steps.append("Instagram, Facebook, and TikTok are not automatic public publishers. A configured identity still waits on disclosure readback. Manual native labeling is not readiness.")
    steps.append("YouTube paid placement stays unverified and is not sent.")
    if not flag:
        steps.append("CLIP_PUBLIC_PUBLISH is off. This report did not approve or post.")
    return {
        "publishes": False,
        "public_flag": flag,
        "accounts_map": "present" if accounts_present else "absent",
        "counts": {
            "items": len(rows),
            "would_dispatch": len(dispatch_ids),
            "manual_ready": len(manual_ids),
            "blocked": len(blocked_ids),
            "policy_held": len(held_ids),
            "campaign_config_absent": len(absent_ids),
            "change_requested": len(change_requested),
        },
        "reasons": reasons,
        "would_dispatch": dispatch_ids,
        "manual_ready": manual_ids,
        "blocked": blocked_ids,
        "policy_held": held_ids,
        "campaign_config_absent": absent_ids,
        "change_requested": change_requested,
        "platforms": _platform_status(),
        "next_steps": steps,
        "items": rows,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv:
        print("Usage: python3 publish_readiness.py")
        print("Reads approvals and targets. Writes nothing and posts nothing.")
        return 0
    path = os.environ.get("CLIPPING_HUB_APPROVALS", "")
    items = []
    if path:
        try:
            data = json.loads(open(path, encoding="utf-8").read())
            items = data.get("items") if isinstance(data, dict) else []
        except (OSError, ValueError):
            items = []
    json.dump(report(items or []), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
