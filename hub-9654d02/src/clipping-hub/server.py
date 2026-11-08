#!/usr/bin/env python3
"""Clipping Hub SHELL: stdlib server on 127.0.0.1:8505.

Serves static/ and a tiny local-state API. Writes only under data/:
  state.json (theme + local clip-approval marks),
  approvals.json (Frankie scheduling inbox decisions),
  events.json (read by the hub; Frankie/jobs append),
  hub-token (per-install POST token).
No outbound network calls, nothing is posted to any platform.
Run: python3 server.py
"""
import hmac
import html
import json
import secrets
import os
import sys
import tempfile
import time
import threading
import contextlib
import random
import fcntl
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
STATE_PATH = Path(os.environ.get("CLIPPING_HUB_STATE", ROOT / "data" / "state.json"))
APPROVALS_PATH = Path(os.environ.get("CLIPPING_HUB_APPROVALS", ROOT / "data" / "approvals.json"))
EVENTS_PATH = Path(os.environ.get("CLIPPING_HUB_EVENTS", ROOT / "data" / "events.json"))
HOST, PORT = "127.0.0.1", int(os.environ.get("CLIPPING_HUB_PORT", "8505"))
PAGES = ("/", "/home", "/queue", "/approvals", "/channels", "/revenue", "/trends")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json", ".webmanifest": "application/manifest+json", ".png": "image/png", ".svg": "image/svg+xml",
         ".mp4": "video/mp4", ".webm": "video/webm"}
THEMES = ("light", "dark")
STATUSES = ("pending", "approved", "skipped", "edit")
ACTIONS = {"approve": "approved", "skip": "skipped", "edit": "edit", "undo": "pending"}
APPROVAL_STATUSES = (
    "pending", "approved", "rejected", "change_requested", "scheduled", "label_pending",
    "readback_ok", "readback_mismatch", "readback_failed", "echo_unconfirmed",
)
APPROVAL_DECISIONS = ("approved", "rejected", "change_requested")
PLATFORMS = ("Clipped Motions YouTube", "TikTok Business", "IG Business", "FB Page")
EVENT_TYPES = ("approval_waiting", "post_sent", "post_scheduled", "job_failed", "payout")
MAX_CLIPS = 5
MAX_BODY = 8192
TOKEN_HEADER = "X-Hub-Token"
TOKEN_META = '<meta name="hub-token" content="">'
CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; worker-src 'self'"


def parse_bytes_range(header, size):
    """Parse a single HTTP Range: bytes=… header.

    Returns (start, end_inclusive) for a satisfiable range, or raises ValueError
    for malformed / unsatisfiable ranges (caller should answer 416).
    Only the first range of a multi-range request is accepted; others raise.
    """
    if size < 0:
        raise ValueError("size")
    if not isinstance(header, str) or not header.strip():
        raise ValueError("empty")
    h = header.strip()
    if not h.lower().startswith("bytes="):
        raise ValueError("unit")
    spec = h.split("=", 1)[1].strip()
    if "," in spec:
        # multi-range: refuse (bounded single-range only)
        raise ValueError("multi")
    if "-" not in spec:
        raise ValueError("form")
    start_s, end_s = spec.split("-", 1)
    start_s, end_s = start_s.strip(), end_s.strip()
    if start_s == "" and end_s == "":
        raise ValueError("empty_spec")
    if start_s == "":
        # suffix: bytes=-N → last N bytes
        try:
            suffix = int(end_s)
        except ValueError as e:
            raise ValueError("suffix") from e
        if suffix <= 0:
            raise ValueError("suffix")
        if size == 0:
            raise ValueError("unsatisfiable")
        length = min(suffix, size)
        return size - length, size - 1
    try:
        start = int(start_s)
    except ValueError as e:
        raise ValueError("start") from e
    if start < 0:
        raise ValueError("start")
    if end_s == "":
        # open-ended: bytes=N-
        if start >= size:
            raise ValueError("unsatisfiable")
        return start, size - 1
    try:
        end = int(end_s)
    except ValueError as e:
        raise ValueError("end") from e
    if end < start:
        raise ValueError("order")
    if start >= size:
        raise ValueError("unsatisfiable")
    end = min(end, size - 1)
    return start, end




def load_token(path):
    """Per-install secret for state-changing calls: data/hub-token, mode 600, created on first start. Never logged.
    A symlink at that path is refused (never followed), and creation uses O_EXCL so a planted file is not reused blindly."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("refusing symlinked token file: %s" % path)
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        fd = None
    if fd is not None:
        with os.fdopen(fd, "r") as f:
            os.fchmod(f.fileno(), 0o600)
            tok = f.read().strip()
        if tok:
            return tok
        os.unlink(str(path))
    tok = secrets.token_urlsafe(32)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(tok)
    return tok


CHECKLIST = (
    ("rights", "I have the rights to use this source footage or it is my own"),
    ("source_credit", "Source and credit are noted"),
    ("audio", "No third-party music or audio I don't have rights to"),
    ("platform_rules", "Meets the platform's content and spam rules (Luis checked the current rules)"),
    ("disclosure", "Any required AI or sponsorship disclosure is added"),
    ("earnings_claims", "No claims about earnings or guaranteed results"),
)
CHECK_IDS = tuple(i for i, _ in CHECKLIST)
FINISH_CHECKLIST = "Finish the checklist first"


def payload(state):
    try:
        import schedule_hook as _sched
        autopost = bool(_sched.enabled())
    except Exception:
        autopost = False
    yt_grants = None
    label_step = False
    try:
        import youtube_label_step as _yls
        label_step = bool(_yls.enabled())   # read-only: lets the UI describe what Approve does
        # Read-only metadata for the chip. Expiry push runs on authorized tick only — never on GET.
        if label_step:
            yt_grants = _yls.grants_summary()
    except Exception:
        yt_grants = None
    return dict(
        state,
        checklist=[{"id": i, "text": t} for i, t in CHECKLIST],
        autopost_enabled=autopost,
        youtube_grants=yt_grants,
        label_step_enabled=label_step,
        public_publish_enabled=_public_publish_enabled(),
    )


def _public_publish_enabled():
    try:
        import public_publish as _pp
        return bool(_pp.enabled())
    except Exception:
        return False


def approve_copy(item, *, label_step=None, grants=None):
    """Truthful Approve sentence. A valid grant is not described as waiting for one."""
    if not isinstance(item, dict):
        return ""
    if _public_publish_enabled():
        try:
            import public_publish as _pp
            return _pp.summary_line(item)
        except Exception:
            return "Not a public post."
    tgt = item.get("route_target") or ("PAID" if (item.get("is_ad") or item.get("campaign_id")) else "MAIN")
    if item.get("needs_destination") is True:
        return "Approve = unavailable · needs destination"
    if item.get("route_blocked"):
        return "Approve = blocked for %s (%s); it will be rejected, nothing uploads" % (
            tgt, item.get("route_block_reason") or "route blocked",
        )
    if item.get("ai_disclosure") is False:
        return "Approve = marks ready · you post manually"
    if label_step is None:
        try:
            import youtube_label_step as _yls
            label_step = bool(_yls.enabled())
        except Exception:
            label_step = False
    if not label_step:
        return "Approve = marks PRIVATE + label-pending · no upload (label step off)"
    if tgt in ("MAIN", "PAID", "GAMING"):
        if grants is None:
            try:
                import youtube_label_step as _yls
                grants = _yls.grants_summary() if label_step else {}
            except Exception:
                grants = {}
        g = (grants or {}).get(tgt) or {}
        if g.get("present") and not g.get("expired") and not g.get("needs_regrant"):
            return "Approve = uploads PRIVATE to %s · hub YouTube grant for %s is on file" % (tgt, tgt)
        return "Approve = uploads PRIVATE to %s when the hub YouTube grant exists; otherwise waits for the grant" % tgt
    return "Approve = marks PRIVATE + label-pending · no upload (no hub YouTube grant for %s)" % tgt


def default_state():
    return {"version": 1, "theme": None, "clips": [], "updated": None}


def load_state(path=None):
    try:
        d = json.loads(Path(path or STATE_PATH).read_text())
    except (OSError, ValueError):
        return default_state()
    if not isinstance(d, dict):
        return default_state()
    out = default_state()
    if d.get("theme") in THEMES:
        out["theme"] = d["theme"]
    for c in d.get("clips") or []:
        if isinstance(c, dict) and isinstance(c.get("id"), str) and c.get("status") in STATUSES:
            raw = c.get("checks") if isinstance(c.get("checks"), list) else []
            checks = [i for i in CHECK_IDS if i in raw]
            status = c["status"]
            if status == "approved" and len(checks) != len(CHECK_IDS):
                status = "pending"
            out["clips"].append({"id": c["id"][:40], "title": str(c.get("title", ""))[:80], "platform": str(c.get("platform", ""))[:40],
                                 "sample": bool(c.get("sample")), "status": status, "checks": checks})
    out["clips"] = out["clips"][:MAX_CLIPS]
    out["updated"] = d.get("updated") if isinstance(d.get("updated"), str) else None
    return out


def atomic_write_json(path, obj, prefix=".tmp-"):
    """Atomic write: temp file in the same dir, fsync, then rename. Never leaves the target empty or half-written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(obj, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return obj


def save_state(state, path=None):
    state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return atomic_write_json(path or STATE_PATH, state, prefix=".state-")


class BadRequest(ValueError):
    pass


class NotFound(ValueError):
    pass


def apply_op(state, req):
    if not isinstance(req, dict):
        raise BadRequest("body must be an object")
    op = req.get("op")
    if op == "theme":
        if req.get("value") not in THEMES:
            raise BadRequest("theme must be light or dark")
        state["theme"] = req["value"]
    elif op == "add_sample":
        if len(state["clips"]) >= MAX_CLIPS:
            raise BadRequest("sample limit reached")
        n = 1 + max([int(c["id"].split("-")[-1]) for c in state["clips"] if c["id"].startswith("sample-") and c["id"].split("-")[-1].isdigit()] or [0])
        state["clips"].append({"id": "sample-%d" % n, "title": "Sample clip %d" % n, "platform": "YouTube Shorts", "sample": True, "status": "pending", "checks": []})
    elif op == "clear_samples":
        state["clips"] = [c for c in state["clips"] if not c["sample"]]
    elif op == "clip":
        status = ACTIONS.get(req.get("action"))
        if status is None:
            raise BadRequest("unknown action")
        for c in state["clips"]:
            if c["id"] == req.get("id"):
                if status == "approved" and len(c["checks"]) != len(CHECK_IDS):
                    raise BadRequest(FINISH_CHECKLIST)
                c["status"] = status
                break
        else:
            raise BadRequest("unknown clip")
    elif op == "check":
        if req.get("item") not in CHECK_IDS or not isinstance(req.get("value"), bool):
            raise BadRequest("bad checklist item")
        for c in state["clips"]:
            if c["id"] == req.get("id"):
                have = set(c["checks"])
                (have.add if req["value"] else have.discard)(req["item"])
                c["checks"] = [i for i in CHECK_IDS if i in have]
                if c["status"] == "approved" and len(c["checks"]) != len(CHECK_IDS):
                    c["status"] = "pending"
                break
        else:
            raise BadRequest("unknown clip")
    else:
        raise BadRequest("unknown op")
    return state


# ---- Approvals inbox (Frankie writes items; hub only records Luis's decision) ----

def default_approvals():
    return {"version": 1, "items": []}


def _clean_platforms(raw):
    out = []
    if not isinstance(raw, list):
        return out
    for p in raw:
        if isinstance(p, str) and p in PLATFORMS and p not in out:
            out.append(p)
    return out


def _clean_item(c):
    if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"]:
        return None
    status = c.get("status") if c.get("status") in APPROVAL_STATUSES else "pending"
    note = str(c.get("note") or "")[:500]
    decided = c.get("decided_at") if isinstance(c.get("decided_at"), str) else None
    if status == "pending":
        decided = None
    tags = []
    raw_tags = c.get("hashtags")
    if isinstance(raw_tags, list):
        for h in raw_tags:
            if isinstance(h, str) and h.strip() and h.strip() not in tags:
                tags.append(h.strip()[:64])
    is_ad = c.get("is_ad") is True or (isinstance(c.get("is_ad"), str) and c.get("is_ad").strip().lower() in ("1", "true", "yes", "on"))
    campaign_id = str(c.get("campaign_id") or "")[:64]
    # ai_disclosure defaults True; explicit false stays false. Never touch caption/title.
    try:
        import schedule_hook as _sched0
        ai_disclosure = _sched0.parse_ai_disclosure(c, default=True)
    except Exception:
        ai_disclosure = True if "ai_disclosure" not in c else bool(c.get("ai_disclosure"))
    item = {
        "id": c["id"][:64],
        "video": str(c.get("video") or c.get("video_url") or c.get("video_path") or "")[:400],
        "caption": str(c.get("caption") or "")[:500],
        "title": str(c.get("title") or "")[:200],
        "platforms": _clean_platforms(c.get("platforms")),
        "hashtags": tags,
        "is_ad": is_ad,
        "campaign_id": campaign_id,
        "ai_disclosure": ai_disclosure,
        "scheduled_at": str(c.get("scheduled_at") or "")[:64],
        "status": status,
        "note": note,
        "decided_at": decided,
        "privacy": str(c.get("privacy") or ("private" if ai_disclosure else ""))[:16],
        "youtube_label_set": bool(c.get("youtube_label_set")),
        "tiktok_label_set": bool(c.get("tiktok_label_set")),
        "instagram_label_set": bool(c.get("instagram_label_set")),
        "youtube_video_id": str(c.get("youtube_video_id") or "")[:64],
        "label_error": str(c.get("label_error") or "")[:200],
        "license": c.get("license") if isinstance(c.get("license"), dict) else None,
        "licenses": c.get("licenses") if isinstance(c.get("licenses"), (list, dict)) else [],
        "projectId": str(c.get("projectId") or c.get("project_id") or c.get("opus_project_id") or "")[:64],
        "clipId": str(c.get("clipId") or c.get("clip_id") or c.get("opus_clip_id") or "")[:64],
        "opus_post_account_id": str(c.get("opus_post_account_id") or "")[:64],
        "opus_sub_account_id": str(c.get("opus_sub_account_id") or c.get("subAccountId") or "")[:64],
        "rights_ok": c.get("rights_ok") is True,
        "campaign_terms_ok": c.get("campaign_terms_ok") is True,
    }
    # Disclosure facts from reconcile. A string echo is not a label switched off,
    # and a user confirmation is not an API echo.
    echo = c.get("label_api_echo")
    if isinstance(echo, str) and echo.strip():
        item["label_api_echo"] = echo.strip()[:32]
    if c.get("label_user_confirmed") is True:
        item["label_user_confirmed"] = True
    source = c.get("label_confirm_source")
    if isinstance(source, str) and source.strip():
        item["label_confirm_source"] = source.strip()[:80]
    confirmed_at = c.get("label_confirmed_at")
    if isinstance(confirmed_at, str) and confirmed_at.strip():
        item["label_confirmed_at"] = confirmed_at.strip()[:40]
    try:
        import destination_routing as _dr
        item.update(_dr.clean_stamp(c))     # creation-time destination stamp (read-only here; never reassigned)
    except Exception:
        if "clip_type" in c:
            item["clip_type"] = str(c.get("clip_type") or "")[:40]
            item["destination_error"] = "stamp_unreadable"
    try:
        import schedule_hook as _sched
        r = _sched.route_for_item(item)
        if r:
            item["route_target"] = r.get("target")
            item["route_handle"] = r.get("handle") or ""
            item["route_name"] = r.get("name") or ""
            item["paid_promotion"] = bool(r.get("paid_promotion"))
            item["storyblocks"] = bool(r.get("storyblocks"))
            item["route_blocked"] = bool(r.get("blocked"))
            item["route_block_reason"] = str(r.get("block_reason") or "")[:120]
            item["route_channel_id"] = str(r.get("channel_id") or "")[:64]
            item["route_opus_post_account_id"] = str(r.get("opus_post_account_id") or "")[:64]
            item["needs_destination"] = bool(r.get("needs_destination"))
            item["destination_reason"] = str(r.get("destination_reason") or "")[:120]
            item["held"] = bool(r.get("held"))
            item["deny_platforms"] = list(r.get("deny_platforms") or [])
        item["ai_platform"] = _sched.ai_platform_map(ai_disclosure)
    except Exception:
        if "clip_type" in item or "destination" in item or "destination_error" in item:
            # Typed clip but routing failed to load: fail closed, never fall back to MAIN/PAID.
            item.update(route_target="", route_handle="", route_name="", paid_promotion=bool(is_ad or campaign_id),
                        storyblocks=False, route_blocked=True, route_block_reason="needs_destination:routing_error",
                        needs_destination=True, destination_reason="routing_error", route_channel_id="", route_opus_post_account_id="")
            item["ai_platform"] = {"youtube": {"altered_synthetic": ai_disclosure}, "tiktok": {"ai_generated": ai_disclosure}, "instagram": {"ai_info_label": ai_disclosure}}
            return item
        item["route_target"] = "PAID" if (is_ad or campaign_id) else "MAIN"
        item["paid_promotion"] = bool(is_ad or campaign_id)
        item["storyblocks"] = False
        item["route_blocked"] = False
        item["route_block_reason"] = ""
        item["ai_platform"] = {
            "youtube": {"altered_synthetic": ai_disclosure},
            "tiktok": {"ai_generated": ai_disclosure},
            "instagram": {"ai_info_label": ai_disclosure},
        }
    item["approve_line"] = approve_copy(item)
    if _public_publish_enabled():
        try:
            import public_publish as _pp
            item["public_preview"] = _pp.build_manifest(item)
        except Exception:
            item["public_preview"] = None
    return item


def load_approvals(path=None):
    try:
        d = json.loads(Path(path or APPROVALS_PATH).read_text())
    except (OSError, ValueError):
        return default_approvals()
    if not isinstance(d, dict):
        return default_approvals()
    items = []
    for c in d.get("items") or []:
        cleaned = _clean_item(c)
        if cleaned:
            items.append(cleaned)
    return {"version": 1, "items": items}


def save_approvals(data, path=None):
    return atomic_write_json(path or APPROVALS_PATH, data, prefix=".approvals-")


def _approvals_lock_path(path=None):
    p = Path(path or APPROVALS_PATH)
    return Path(str(p) + ".lock")


@contextlib.contextmanager
def approvals_lock(path=None):
    """Exclusive flock for approvals.json RMW (Approve + tick share this)."""
    lp = _approvals_lock_path(path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lp), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def parse_tick_force(raw) -> bool:
    """Strict force: only True / 'true' / '1'. 'false', 0, other → False."""
    if raw is True:
        return True
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw) == 1
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1")
    return False


def ledger_upload_gate(item):
    """Skip or fail closed before any upload. Does not write a ledger or approvals."""
    try:
        import ledger_dedupe as _dedupe
    except Exception:
        return {"action": "fail", "reason": "ledger_unreadable", "video_id": ""}
    try:
        return _dedupe.check_upload(item if isinstance(item, dict) else {})
    except Exception:
        return {"action": "fail", "reason": "ledger_unreadable", "video_id": ""}


def _annotate_ledger_gate(item):
    if not isinstance(item, dict) or item.get("status") != "pending":
        if isinstance(item, dict):
            item.pop("ledger_upload_reason", None)
        return
    gate = ledger_upload_gate(item)
    if gate.get("action") == "proceed":
        item.pop("ledger_upload_reason", None)
    else:
        item["ledger_upload_reason"] = str(gate.get("reason") or "ledger_unreadable")[:80]


def approvals_payload(data):
    for item in data.get("items") or []:
        _annotate_ledger_gate(item)
    pending = sum(1 for i in data["items"] if i["status"] == "pending")
    return dict(data, pending=pending)


def decide_approval(data, req):
    """Apply one decision. Unknown id → NotFound. Already-decided → idempotent (no rewrite of fields)."""
    if not isinstance(req, dict) or req.get("op") != "decide":
        raise BadRequest("unknown op")
    status = req.get("status")
    if status not in APPROVAL_DECISIONS:
        raise BadRequest("status must be approved, rejected, or change_requested")
    note = str(req.get("note") or "")[:500]
    if status == "change_requested" and not note.strip():
        raise BadRequest("note required for change_requested")
    iid = req.get("id")
    for item in data["items"]:
        if item["id"] == iid:
            # Re-entrant Approve on label_pending: reconcile / finish labels only (no field rewrite).
            if item["status"] == "label_pending" and status == "approved":
                return data, item, True
            if item["status"] != "pending":
                return data, item, False   # idempotent: leave as-is
            # Typed clip with no verified destination: refuse Approve, leave the item untouched (no reject, no fallback).
            if status == "approved" and item.get("needs_destination"):
                raise BadRequest("needs destination: " + str(item.get("destination_reason") or "unassigned"))
            # Held campaigns stay pending and out of Approve. They are not rejected and not submitted.
            if status == "approved" and item.get("held"):
                raise BadRequest("campaign_held")
            if status == "approved" and _public_publish_enabled():
                if req.get("confirm_public") is not True:
                    raise BadRequest("public_confirm_required")
                preview = item.get("public_preview") if isinstance(item.get("public_preview"), dict) else None
                if preview is None:
                    import public_publish as _pp
                    preview = _pp.build_manifest(item)
                if str(req.get("manifest_hash") or "") != str(preview.get("manifest_hash") or ""):
                    raise BadRequest("manifest_stale")
                rows_in = req.get("platform_rows")
                if not isinstance(rows_in, list):
                    raise BadRequest("platform_rows_required")
                got_rows = {}
                for entry in rows_in:
                    if isinstance(entry, dict):
                        got_rows[str(entry.get("key") or "")] = str(entry.get("row_hash") or "")
                for prow in preview.get("platforms") or []:
                    if got_rows.get(str(prow.get("key") or "")) != str(prow.get("row_hash") or ""):
                        raise BadRequest("platform_not_confirmed")
                if preview.get("record_kind") not in ("dispatch", "manual"):
                    raise BadRequest(("nothing_to_publish:" + str(preview.get("refuse_reason") or ""))[:120])
            # Storyblocks fail-closed: never approve/schedule a blocked target (no silent MAIN reroute).
            if status == "approved" and item.get("route_blocked"):
                item["status"] = "rejected"
                item["note"] = (note or item.get("route_block_reason") or "storyblocks_main_only").strip()[:500]
                item["decided_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                return data, item, True
            item["status"] = status
            item["note"] = note if status == "change_requested" else (note or item.get("note") or "")
            item["decided_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            # Interim AI rule: approved + ai_disclosure → label_pending + private
            if status == "approved" and item.get("ai_disclosure") is not False:
                item["status"] = "label_pending"
                item["privacy"] = "private"
                item["youtube_label_set"] = False
                item["tiktok_label_set"] = False
                item["instagram_label_set"] = False
            return data, item, True
    raise NotFound("unknown id")


def _apply_decision(data, body):
    """Single per-item decide path (validation, gates, post-Approve hooks). Caller holds approvals_lock and saves.
    Shared by POST {op:decide} and POST {op:approve_batch}. Returns (item, changed, extra)."""
    extra = {}
    if isinstance(body, dict) and body.get("status") == "approved":
        iid = body.get("id")
        current = next((i for i in data.get("items") or [] if i.get("id") == iid), None)
        if current is not None and current.get("status") == "pending":
            gate = ledger_upload_gate(current)
            if gate.get("action") == "fail":
                raise BadRequest(str(gate.get("reason") or "ledger_unreadable")[:80])
            if gate.get("action") == "skip":
                return current, False, {
                    "skipped": True,
                    "reason": gate.get("reason"),
                    "outcome": "skipped",
                }
    data, item, changed = decide_approval(data, body)
    if changed:
        # Stub only: CLIP_AUTOPOST_ENABLED default off. Marks scheduled +
        # queues a local job file; never calls any external poster.
        if item.get("status") in ("approved", "label_pending") and body.get("status") == "approved":
            try:
                import schedule_hook as _sched
                # Temporarily treat as approved for job append, then restore label_pending.
                prev = item.get("status")
                item["status"] = "approved"
                _sched.on_approved(item)
                if prev == "label_pending":
                    item["status"] = "label_pending"
                    item["privacy"] = item.get("privacy") or "private"
            except Exception:
                pass
            if _public_publish_enabled():
                # Public flag replaces the private multi-platform upload. No second post.
                try:
                    import public_publish as _pp
                    res = _pp.dispatch_item(
                        item, body.get("manifest_hash"), platform_rows=body.get("platform_rows"),
                    )
                    extra["public_publish"] = {
                        "ok": bool(res.get("ok")),
                        "dispatched": bool(res.get("dispatched")),
                        "partial": bool(res.get("partial")),
                        "error": res.get("error"),
                        "kind": res.get("kind"),
                        "platforms": [
                            {
                                "platform": p.get("platform"),
                                "key": p.get("key"),
                                "status": p.get("status"),
                                "reason": p.get("reason"),
                                "permalink": p.get("permalink"),
                                "remote_id": _pp._visible_remote_id(p.get("remote_id")),
                                "status_query": bool(p.get("status_query")),
                                "later_status_query": bool(p.get("later_status_query")),
                            }
                            for p in (res.get("platforms") or [])
                            if isinstance(p, dict)
                        ],
                    }
                    if res.get("error"):
                        item["label_error"] = str(res.get("error"))[:200]
                    platforms = [p for p in (res.get("platforms") or []) if isinstance(p, dict)]
                    posted = any(p.get("status") == "done" for p in platforms)
                    kept = any(
                        p.get("remote_id") or p.get("status") in ("done", "unknown", "create_error")
                        for p in platforms
                    )
                    # A recorded id stays. Do not copy it onto youtube_video_id and do not revert it.
                    if res.get("kind") != "manual" and not posted and not kept:
                        item["status"] = "pending"
                        item["decided_at"] = None
                        item["label_error"] = str(res.get("error") or "not_posted")[:200]
                        extra["reverted"] = True
                except Exception as e:
                    extra["public_publish"] = {"ok": False, "error": type(e).__name__, "dispatched": False}
                    item["status"] = "pending"
                    item["decided_at"] = None
                    extra["reverted"] = True
            # Multi-platform Approve (CLIP_YOUTUBE_LABEL_STEP, default OFF). Mocked in tests.
            try:
                import multi_platform_publish as _mpp
                if (not _public_publish_enabled()) and _mpp.enabled() and item.get("ai_disclosure") is not False:
                    res = _mpp.publish_after_approve(item)
                    extra["multi_platform"] = res
                    if res.get("oauth_url"):
                        extra["oauth_url"] = res["oauth_url"]
                    for prow in res.get("platforms") or []:
                        if prow.get("key") == "youtube" and prow.get("status") == "done":
                            item["youtube_label_set"] = True
                            item["youtube_video_id"] = str(prow.get("opus_post_id") or "")[:64]
                        if prow.get("status") == "needs_manual_label":
                            item.setdefault("manual_label_platforms", [])
                            if isinstance(item["manual_label_platforms"], list):
                                item["manual_label_platforms"].append(prow.get("platform"))
                    if res.get("error"):
                        item["label_error"] = str(res.get("error") or "")[:200]
            except Exception as e:
                extra["multi_platform"] = {"ok": False, "error": type(e).__name__}
            # Manual-label / TT+IG pushes live inside multi_platform_publish only (one push).
    return item, changed, extra


# ---- Approve All: loops the SAME per-item path; never a new publish path ----
BATCH_MAX = 50
_BATCH_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def approve_action(item, label_step=None):
    """What a single Approve does for this item (mirrors decide_approval + publish_after_approve). '' = not eligible."""
    if not isinstance(item, dict) or item.get("status") != "pending":
        return ""
    if item.get("needs_destination") or item.get("route_blocked") or item.get("held"):
        return ""
    gate = ledger_upload_gate(item)
    if gate.get("action") != "proceed":
        return ""
    if _public_publish_enabled():
        preview = item.get("public_preview") if isinstance(item.get("public_preview"), dict) else {}
        if preview.get("record_kind") == "dispatch" and preview.get("will_dispatch_any") and preview.get("ui_kind") == "public":
            return "public_review"
        if preview.get("record_kind") == "manual" and preview.get("ui_kind") == "manual":
            return "manual"
        return ""
    if item.get("ai_disclosure") is False:
        return "manual"
    if label_step is None:
        try:
            import youtube_label_step as _yls
            label_step = bool(_yls.enabled())
        except Exception:
            label_step = False
    return "private_upload" if label_step else "private_no_upload"


def _batches_path(ap):
    return Path(ap).parent / "approve_batches.json"


def approve_batch(ap, req):
    """Caller holds approvals_lock. Idempotent per batch_id: a repeat returns the stored result, approves nothing.
    Each entry must name the action the user confirmed; if the server now computes a different action the item is
    refused ('action_changed'), so nothing the sheet did not show can upload."""
    bid = str(req.get("batch_id") or "")
    if not _BATCH_ID.match(bid):
        raise BadRequest("batch_id required")
    entries = req.get("items")
    if not isinstance(entries, list) or not entries or len(entries) > BATCH_MAX:
        raise BadRequest("items must be 1..%d" % BATCH_MAX)
    bp = _batches_path(ap)
    try:
        store = json.loads(bp.read_text())
        if not isinstance(store, dict) or not isinstance(store.get("batches"), dict):
            store = {"batches": {}}
    except (OSError, ValueError):
        store = {"batches": {}}
    if bid in store["batches"]:
        return dict(store["batches"][bid], replayed=True)
    seen, results = set(), []
    for e in entries:
        iid = str((e or {}).get("id") or "")[:64] if isinstance(e, dict) else ""
        want = str((e or {}).get("action") or "") if isinstance(e, dict) else ""
        if not iid or iid in seen:
            results.append({"id": iid, "ok": False, "error": "duplicate_or_missing_id"}); continue
        seen.add(iid)
        data = load_approvals(ap)
        item = next((i for i in data["items"] if i["id"] == iid), None)
        if item is None:
            results.append({"id": iid, "ok": False, "error": "unknown id"}); continue
        if item.get("status") != "pending":
            results.append({"id": iid, "ok": False, "error": "not_pending:" + str(item.get("status"))}); continue
        gate = ledger_upload_gate(item)
        if gate.get("action") == "fail":
            results.append({
                "id": iid, "ok": False, "posted": False, "outcome": "failed",
                "status": item.get("status"), "error": str(gate.get("reason") or "ledger_unreadable")[:120],
            })
            continue
        if gate.get("action") == "skip":
            results.append({
                "id": iid, "ok": False, "posted": False, "outcome": "skipped",
                "status": item.get("status"), "reason": gate.get("reason"),
                "error": str(gate.get("reason") or "")[:120],
            })
            continue
        act = approve_action(item)
        if not act:
            results.append({"id": iid, "ok": False, "error": "not_eligible:" + str(item.get("destination_reason") or item.get("route_block_reason") or "")[:80]}); continue
        if act != want:
            results.append({"id": iid, "ok": False, "error": "action_changed:%s->%s" % (want, act)}); continue
        try:
            decision = {"op": "decide", "id": iid, "status": "approved", "note": ""}
            if want in ("public_review", "manual") and _public_publish_enabled():
                decision["confirm_public"] = True
                decision["manifest_hash"] = (e or {}).get("manifest_hash") if isinstance(e, dict) else None
                decision["platform_rows"] = (e or {}).get("platform_rows") if isinstance(e, dict) else None
            it, changed, extra = _apply_decision(data, decision)
            if changed:
                save_approvals(data, ap)
            r = {"id": iid, "ok": bool(changed), "status": it.get("status"), "action": act, "posted": False}
            pub = extra.get("public_publish") if isinstance(extra, dict) else None
            if isinstance(pub, dict):
                r["public_publish"] = {
                    "ok": pub.get("ok"),
                    "dispatched": pub.get("dispatched"),
                    "partial": bool(pub.get("partial")),
                    "error": pub.get("error"),
                    "kind": pub.get("kind"),
                    "platforms": pub.get("platforms"),
                }
                plats = [p for p in (pub.get("platforms") or []) if isinstance(p, dict)]
                posted = any(p.get("status") == "done" for p in plats)
                unknown = any(p.get("status") == "unknown" for p in plats)
                failed = any(p.get("status") in ("failed", "create_error") for p in plats)
                blocked = any(p.get("status") in ("blocked", "not_public") for p in plats)
                r["posted"] = bool(posted)
                if extra.get("reverted"):
                    r["ok"] = False
                    r["status"] = "pending"
                    r["posted"] = False
                    r["error"] = str(pub.get("error") or "not_posted")[:120]
                    r["outcome"] = "blocked" if blocked and not failed and not unknown else "failed"
                elif pub.get("kind") == "manual":
                    r["posted"] = False
                    r["outcome"] = "manual"
                elif posted and (unknown or failed or blocked or pub.get("partial")):
                    r["ok"] = False
                    r["outcome"] = "partial"
                    r["error"] = "partial"
                elif any(p.get("status") == "private_uploaded" for p in plats) and not unknown and not failed and not posted:
                    r["ok"] = False
                    r["posted"] = False
                    r["outcome"] = "private_uploaded"
                elif unknown:
                    r["ok"] = False
                    r["outcome"] = "unknown"
                    r["error"] = str(pub.get("error") or "unconfirmed")[:120]
                elif posted and r.get("ok"):
                    r["outcome"] = "success"
                elif blocked and not failed:
                    r["ok"] = False
                    r["outcome"] = "blocked"
                    r["error"] = str(pub.get("error") or "blocked")[:120]
                else:
                    r["ok"] = False
                    r["outcome"] = "failed"
                    r["error"] = str(pub.get("error") or r.get("error") or "failed")[:120]
            mp = extra.get("multi_platform") if isinstance(extra, dict) else None
            if isinstance(mp, dict) and mp.get("error"):
                r["warning"] = str(mp.get("error"))[:120]
            if not changed:
                r["error"] = "unchanged"
            results.append(r)
        except (BadRequest, NotFound) as ex:
            results.append({"id": iid, "ok": False, "error": str(ex)[:120]})
        except Exception as ex:
            results.append({"id": iid, "ok": False, "error": type(ex).__name__})
    def _bucket(r):
        name = r.get("outcome")
        if name in ("success", "partial", "blocked", "failed", "unknown", "manual", "private_uploaded", "skipped"):
            return name
        return "success" if r.get("ok") and r.get("posted") else ("approved" if r.get("ok") else "failed")

    out = {
        "batch_id": bid,
        "approved": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if _bucket(r) == "failed"),
        "success": sum(1 for r in results if _bucket(r) == "success"),
        "partial": sum(1 for r in results if _bucket(r) == "partial"),
        "blocked": sum(1 for r in results if _bucket(r) == "blocked"),
        "unknown": sum(1 for r in results if _bucket(r) == "unknown"),
        "manual": sum(1 for r in results if _bucket(r) == "manual"),
        "private_uploaded": sum(1 for r in results if _bucket(r) == "private_uploaded"),
        "skipped": sum(1 for r in results if _bucket(r) == "skipped"),
        "results": results,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    store["batches"][bid] = out
    if len(store["batches"]) > 100:
        for k in sorted(store["batches"], key=lambda k: store["batches"][k].get("at", ""))[:-100]:
            store["batches"].pop(k, None)
    atomic_write_json(bp, store, prefix=".batches-")
    return out


# ---- Events (Frankie/jobs append; hub reads only) ----

def default_events():
    return {"version": 1, "events": []}


def load_events(path=None):
    try:
        d = json.loads(Path(path or EVENTS_PATH).read_text())
    except (OSError, ValueError):
        return default_events()
    if not isinstance(d, dict):
        return default_events()
    events = []
    for e in d.get("events") or []:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str):
            continue
        et = e.get("type")
        if et not in EVENT_TYPES:
            continue
        events.append({
            "id": e["id"][:64],
            "type": et,
            "at": str(e.get("at") or "")[:64],
            "title": str(e.get("title") or "")[:120],
            "body": str(e.get("body") or "")[:400],
            "ref": str(e.get("ref") or "")[:64],
        })
    return {"version": 1, "events": events}



def append_event(data, req):
    """Append one event (Frankie/jobs). Raises BadRequest on bad shape."""
    if not isinstance(req, dict) or req.get("op") != "append":
        raise BadRequest("unknown op")
    e = req.get("event") if isinstance(req.get("event"), dict) else req
    if not isinstance(e.get("id"), str) or not e["id"]:
        raise BadRequest("id required")
    et = e.get("type")
    if et not in EVENT_TYPES:
        raise BadRequest("bad type")
    # idempotent if id already present
    for existing in data["events"]:
        if existing["id"] == e["id"]:
            return data, existing, False
    item = {
        "id": e["id"][:64],
        "type": et,
        "at": str(e.get("at") or time.strftime("%Y-%m-%dT%H:%M:%S%z"))[:64],
        "title": str(e.get("title") or "")[:120],
        "body": str(e.get("body") or "")[:400],
        "ref": str(e.get("ref") or "")[:64],
    }
    data["events"].append(item)
    return data, item, True


def save_events(data, path=None):
    return atomic_write_json(path or EVENTS_PATH, data, prefix=".events-")



# ---- YouTube label tick (authorized HTTP + in-process daemon when flag ON) ----
TICK_INTERVAL_S = int(os.environ.get("CLIP_YT_TICK_INTERVAL_S", str(10 * 60)))
TICK_JITTER_S = int(os.environ.get("CLIP_YT_TICK_JITTER_S", "60"))
TICK_MIN_GAP_S = int(os.environ.get("CLIP_YT_TICK_MIN_GAP_S", str(5 * 60)))
_TICK_STATE_PATH = Path(os.environ.get(
    "CLIP_YT_TICK_STATE",
    str(Path(__file__).resolve().parent / "data" / "youtube_label_tick.json"),
))
_tick_thread = None
_tick_stop = threading.Event()


def _tick_lock_path():
    return Path(str(_TICK_STATE_PATH) + ".lock")


def _tick_rate_ok_and_stamp(*, force=False, now=None):
    """Shared rate limit (min TICK_MIN_GAP_S) under flock. force does not bypass."""
    now_e = float(now) if isinstance(now, (int, float)) else time.time()
    _TICK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lp = _tick_lock_path()
    fd = os.open(str(lp), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        last = 0.0
        try:
            if _TICK_STATE_PATH.is_file():
                import json as _json
                last = float((_json.loads(_TICK_STATE_PATH.read_text()) or {}).get("last_ts") or 0)
        except Exception:
            last = 0.0
        # force does NOT bypass the 5-minute cap — always enforce.
        if last and (now_e - last) < TICK_MIN_GAP_S:
            return False
        import json as _json
        tmp = _TICK_STATE_PATH.with_suffix(".tmp")
        tmp.write_text(_json.dumps({"last_ts": now_e}))
        os.replace(str(tmp), str(_TICK_STATE_PATH))
        try:
            os.chmod(_TICK_STATE_PATH, 0o600)
        except OSError:
            pass
        return True
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def run_youtube_label_tick(*, force=False, approvals_path=None, push_fn=None, http_post=None):
    """Expiry warn (testing mode) + token alive check + reconcile timeout_pending. No creates.
    Always rate-limited (min TICK_MIN_GAP_S); force does not bypass. Returns dict summary.
    """
    import youtube_label_step as _yls
    import post_idempotency as _idem
    out = {"ok": True, "skipped": False, "warns": [], "revoked": [], "reconciled": []}
    if not _yls.enabled():
        out["ok"] = False
        out["error"] = "label_step_off"
        return out
    if not _tick_rate_ok_and_stamp(force=force):
        out["skipped"] = True
        out["error"] = "rate_limited"
        return out
    for ch in _yls.GRANT_CHANNELS:
        try:
            if _yls.maybe_warn_grant_expiry(ch, push_fn=push_fn):
                out["warns"].append(ch)
        except Exception:
            pass
        try:
            alive, err = _yls.check_grant_alive(ch, http_post=http_post)
            # Alert only when a grant existed and is now bad — not "never connected".
            if not alive and err in ("invalid_grant", "grant_expired", "no_access"):
                if _yls.maybe_alert_revoked(ch, err or "revoked", push_fn=push_fn):
                    out["revoked"].append(ch)
        except Exception:
            pass
    try:
        ap = Path(approvals_path) if approvals_path else APPROVALS_PATH
        with approvals_lock(ap):
            data = load_approvals(ap)
            for item in data.get("items") or []:
                if item.get("status") != "label_pending":
                    continue
                job_id = str(item.get("id") or "")
                row = _idem.lookup(job_id, _yls.CREATE_IDEMPOTENCY_PLATFORM) if job_id else None
                st_row = (row or {}).get("status")
                if st_row == "timeout_pending":
                    pass
                elif st_row == "in_flight" and _idem.is_in_flight_stale(row or {}):
                    pass
                else:
                    continue
                res = _yls.try_reconcile_label_item(item)
                out["reconciled"].append({"id": item.get("id"), "ok": res.get("ok"), "error": res.get("error")})
                if res.get("ok") and res.get("youtube_label"):
                    item["youtube_label_set"] = True
                    item["youtube_video_id"] = str(res.get("video_id") or "")[:64]
            save_approvals(data, ap)
    except Exception as e:
        out["ok"] = False
        out["error"] = type(e).__name__
    return out


def _tick_daemon_loop():
    import youtube_label_step as _yls
    while not _tick_stop.is_set():
        # 10 min + jitter; skip work when flag OFF
        delay = TICK_INTERVAL_S + random.uniform(0, max(0, TICK_JITTER_S))
        if _tick_stop.wait(delay):
            break
        if not _yls.enabled():
            continue
        try:
            run_youtube_label_tick(force=False)
        except Exception:
            pass


def start_youtube_label_tick_daemon():
    """Start daemon only when CLIP_YOUTUBE_LABEL_STEP is ON. Returns thread or None."""
    global _tick_thread
    import youtube_label_step as _yls
    if not _yls.enabled():
        return None
    if _tick_thread is not None and _tick_thread.is_alive():
        return _tick_thread
    _tick_stop.clear()
    _tick_thread = threading.Thread(target=_tick_daemon_loop, name="yt-label-tick", daemon=True)
    _tick_thread.start()
    return _tick_thread


def stop_youtube_label_tick_daemon():
    global _tick_thread
    _tick_stop.set()
    t = _tick_thread
    _tick_thread = None
    return t

def make_handler(state_path=None, static_dir=None, token_path=None, approvals_path=None, events_path=None):
    sp = Path(state_path) if state_path else STATE_PATH
    st = Path(static_dir) if static_dir else STATIC
    ap = Path(approvals_path) if approvals_path else (sp.parent / "approvals.json")
    ep = Path(events_path) if events_path else (sp.parent / "events.json")
    token = load_token(Path(token_path) if token_path else sp.parent / "hub-token")

    class H(BaseHTTPRequestHandler):
        server_version = "ClippingHub"

        def log_message(self, fmt, *args):
            try:
                msg = fmt % args
            except Exception:
                msg = str(fmt)
            import re as _re
            # Redact query strings on /oauth/ paths (code + state must never hit logs).
            msg = _re.sub(r"(/oauth/[^?\s\"]*)\?[^\s\"]*", r"\1?redacted", msg)
            msg = _re.sub(r"https://www\.googleapis\.com/\S*", "[redacted]", msg)
            msg = _re.sub(r"upload_id=[^\s&\"]*", "upload_id=[redacted]", msg)
            sys.stderr.write("%s - %s\n" % (self.address_string(), msg))

        def _send(self, body, ctype, code=200, cache="no-cache", extra_headers=None, content_length=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body) if content_length is None else content_length))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            if extra_headers:
                for k, v in extra_headers:
                    self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD" and body:
                self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj).encode(), TYPES[".json"], code, "no-store")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/state":
                return self._json(payload(load_state(sp)))
            if path == "/api/approvals":
                return self._json(approvals_payload(load_approvals(ap)))
            if path == "/api/events":
                return self._json(load_events(ep))
            if path == "/api/shorts":
                import clipper_data as _cd
                return self._json(_cd.load_shorts())
            if path == "/api/credits":
                import clipper_data as _cd
                return self._json(_cd.load_credits())
            if path == "/api/campaigns":
                import clipper_data as _cd
                return self._json(_cd.load_campaigns())
            if path == "/api/channels":
                import clipper_data as _cd
                return self._json(_cd.load_channels())
            if path == "/api/revenue":
                import clipper_data as _cd
                return self._json(_cd.load_revenue())
            if path == "/api/script-queue":
                import clipper_data as _cd
                return self._json(_cd.load_script_queue())
            if path == "/oauth/youtube/callback":
                # 404 unless a grant is in progress: flag ON + unexpired authorized state.
                # Never bind a name that shadows the static-dir Path `st`.
                # Never delete files outside STATE_DIR (load_oauth_state enforces that).
                from urllib.parse import parse_qs, urlparse
                import youtube_label_step as _yls
                qs = parse_qs(urlparse(self.path).query)
                code = (qs.get("code") or [None])[0]
                state_tok = (qs.get("state") or [None])[0]
                err = (qs.get("error") or [None])[0]
                if not _yls.enabled() or not _yls.grant_in_progress(state_tok or ""):
                    return self._send(b"not found", "text/plain", 404)
                oauth_grant = _yls.load_oauth_state(state_tok) if state_tok else None
                if not oauth_grant:
                    return self._send(b"not found", "text/plain", 404)
                msg = "OAuth cancelled." if err else "OAuth failed."
                connected_ok = False
                try:
                    if code and not err:
                        tok, xerr = _yls.exchange_code(
                            code, code_verifier=oauth_grant.get("code_verifier"),
                        )
                        ch_grant = oauth_grant.get("channel") or "MAIN"
                        exp_name, exp_yt, exp_handle = _yls.expected_yt_for_hub_channel(ch_grant)
                        verify = None
                        if not tok:
                            msg = "OAuth token exchange failed (%s)." % (xerr or "unknown")
                            _yls.discard_grant_tokens({}, ch_grant)
                        elif not tok.get("access_token"):
                            msg = "OAuth failed: no access_token from Google. Token not saved."
                            _yls.discard_grant_tokens(tok, ch_grant)
                        elif not exp_yt:
                            msg = "OAuth failed: missing expected YouTube channel id in post_targets. Token not saved."
                            _yls.discard_grant_tokens(tok, ch_grant)
                        else:
                            try:
                                verify = _yls.verify_grant_matches_channel(
                                    ch_grant, tok.get("access_token"),
                                )
                            except Exception:
                                verify = {
                                    "ok": False,
                                    "mismatch": False,
                                    "error": "verify_exception",
                                    "granted": [],
                                }
                            if not isinstance(verify, dict) or not verify.get("ok"):
                                err_code = (verify or {}).get("error") or "verify_failed"
                                granted_txt = ", ".join(
                                    "%s (%s)" % (g.get("title") or "?", g.get("id") or "?")
                                    for g in ((verify or {}).get("granted") or [])
                                ) or "(none)"
                                if (verify or {}).get("mismatch") or err_code == "channel_mismatch":
                                    msg = (
                                        "YouTube grant failed: signed-in account does not own the expected channel. "
                                        "Hub channel %s expects %s (%s). Google returned: %s. "
                                        "Token was NOT saved. Re-open the grant link and pick the correct account."
                                    ) % (ch_grant, exp_name, exp_yt, granted_txt)
                                else:
                                    msg = (
                                        "YouTube grant failed (%s). Expected %s (%s) for hub channel %s. "
                                        "Token was NOT saved."
                                    ) % (err_code, exp_name, exp_yt, ch_grant)
                                _yls.discard_grant_tokens(tok, ch_grant)
                            else:
                                import time as _time
                                tok = dict(tok)
                                tok["granted_at"] = _time.strftime("%Y-%m-%dT%H:%M:%S%z")
                                tok["expiry_warn_for_granted_at"] = ""
                                tok["bound_channel_id"] = exp_yt
                                tok["bound_channel_title"] = exp_name
                                tok["granted_channel_ids"] = [
                                    g.get("id") for g in (verify.get("granted") or []) if g.get("id")
                                ][:8]
                                if _yls.save_token(ch_grant, tok):
                                    connected_ok = True
                                    msg = (
                                        "YouTube connected for %s — %s (%s)%s. "
                                        "Return to Approvals and tap Approve again."
                                    ) % (
                                        ch_grant,
                                        exp_name,
                                        exp_yt,
                                        (" · " + exp_handle) if exp_handle else "",
                                    )
                                else:
                                    msg = "OAuth token save failed. Token was NOT kept."
                                    _yls.discard_grant_tokens(tok, ch_grant)
                except Exception:
                    msg = "OAuth handler error. Token was NOT saved."
                    try:
                        _yls.discard_grant_tokens(
                            {}, (oauth_grant or {}).get("channel") or "MAIN",
                        )
                    except Exception:
                        pass
                try:
                    _ch = (oauth_grant or {}).get("channel") or "MAIN"
                    _en, _ey, _eh = _yls.expected_yt_for_hub_channel(_ch)
                    channel_line = "Hub channel: <b>%s</b> · YouTube: <b>%s</b> (%s)%s" % (
                        html.escape(str(_ch)),
                        html.escape(str(_en or "")),
                        html.escape(str(_ey or "")),
                        (" · " + html.escape(str(_eh))) if _eh else "",
                    )
                except Exception:
                    channel_line = ""
                # Never claim connected unless verify+save succeeded.
                if not connected_ok and "connected" in msg.lower() and "not" not in msg.lower():
                    msg = "YouTube grant failed. Token was NOT saved."
                safe_msg = html.escape(msg)
                html_out = (
                    "<!doctype html><meta name=viewport content=\"width=device-width,initial-scale=1\">"
                    "<title>YouTube OAuth</title><body style=\"font-family:system-ui;padding:2rem\">"
                    "<h1>Clipping Hub</h1>"
                    + (("<p>%s</p>" % channel_line) if channel_line else "")
                    + ("<p>%s</p>" % safe_msg)
                    + "<p><a href=\"/approvals\">Back to Approvals</a></p></body>"
                )
                return self._send(html_out.encode(), "text/html; charset=utf-8", cache="no-store")
            if path in PAGES:
                path = "/index.html"
            # Decode %2e%2e etc before resolve; still fail-closed via relative_to(st).
            from urllib.parse import unquote as _unquote
            raw_path = _unquote(path)
            if raw_path.startswith("/") and not raw_path.startswith("//"):
                rel = raw_path.lstrip("/")
            else:
                return self._send(b"not found", "text/plain", 404)
            # Refuse if ANY path component under static is a symlink (lstat before resolve).
            # Stops symlink-escape that resolve() would otherwise follow.
            cur = st.resolve()
            parts = Path(rel).parts
            for part in parts:
                if part in ("", ".", ".."):
                    return self._send(b"not found", "text/plain", 404)
                cur = cur / part
                try:
                    st_mode = cur.lstat()
                except OSError:
                    return self._send(b"not found", "text/plain", 404)
                import stat as _stat
                if _stat.S_ISLNK(st_mode.st_mode):
                    return self._send(b"not found", "text/plain", 404)
            f = cur.resolve()
            try:
                f.relative_to(st.resolve())
            except ValueError:
                return self._send(b"not found", "text/plain", 404)
            if not f.is_file() or f.is_symlink():
                return self._send(b"not found", "text/plain", 404)
            ctype = TYPES.get(f.suffix, "application/octet-stream")
            cache = "no-store" if f.name == "index.html" else "no-cache"
            # Bounded Range support for /samples/* media (stdlib; not Starlette).
            under_samples = rel == "samples" or rel.startswith("samples/")
            if under_samples:
                size = f.stat().st_size
                rng = self.headers.get("Range")
                accept = [("Accept-Ranges", "bytes")]
                if rng:
                    try:
                        start, end = parse_bytes_range(rng, size)
                    except ValueError:
                        return self._send(
                            b"", ctype, 416, cache,
                            extra_headers=accept + [("Content-Range", "bytes */%d" % size)],
                            content_length=0,
                        )
                    length = end - start + 1
                    chunk = b""
                    if self.command != "HEAD":
                        with open(f, "rb") as fh:
                            fh.seek(start)
                            chunk = fh.read(length)
                    return self._send(
                        chunk, ctype, 206, cache,
                        extra_headers=accept + [("Content-Range", "bytes %d-%d/%d" % (start, end, size))],
                        content_length=length,
                    )
                body = b"" if self.command == "HEAD" else f.read_bytes()
                return self._send(body, ctype, 200, cache, extra_headers=accept, content_length=size)
            body = f.read_bytes()
            if f.name == "index.html":
                body = body.replace(TOKEN_META.encode(), ('<meta name="hub-token" content="%s">' % token).encode())
                return self._send(body, TYPES[".html"], cache="no-store")
            return self._send(body, ctype, cache=cache)

        def _authorized(self):
            origin = self.headers.get("Origin")
            if origin is not None:
                host = self.headers.get("Host") or ""
                if origin.split("://", 1)[-1].rstrip("/") != host:
                    return False
            if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                return False
            got = self.headers.get(TOKEN_HEADER) or ""
            return hmac.compare_digest(got.encode(), token.encode())

        do_HEAD = do_GET

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path not in ("/api/state", "/api/approvals", "/api/events", "/api/post-ledger/unstick", "/api/youtube-oauth/start", "/api/youtube-label/tick"):
                return self._send(b"read-only", "text/plain", 405)
            if not self._authorized():
                return self._json({"ok": False, "error": "Forbidden"}, 403)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 < n <= MAX_BODY:
                    raise BadRequest("size")
                body = json.loads(self.rfile.read(n))
            except BadRequest as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            except (ValueError, TypeError):
                return self._json({"ok": False, "error": "Bad request"}, 400)

            if path == "/api/state":
                try:
                    state = apply_op(load_state(sp), body)
                except BadRequest as e:
                    return self._json({"ok": False, "error": str(e)}, 400)
                save_state(state, sp)
                return self._json(dict(payload(state), ok=True))

            if path == "/api/approvals":
                if isinstance(body, dict) and body.get("op") == "approve_batch":
                    try:
                        with approvals_lock(ap):
                            result = approve_batch(ap, body)
                    except BadRequest as e:
                        return self._json({"ok": False, "error": str(e)}, 400)
                    return self._json(dict(approvals_payload(load_approvals(ap)), ok=True, batch=result))
                try:
                    with approvals_lock(ap):
                        data = load_approvals(ap)
                        item, changed, extra = _apply_decision(data, body)
                        if changed:
                            save_approvals(data, ap)
                except NotFound as e:
                    return self._json({"ok": False, "error": str(e)}, 404)
                except BadRequest as e:
                    return self._json({"ok": False, "error": str(e)}, 400)
                return self._json(dict(approvals_payload(data), ok=True, item=item, changed=changed, **extra))

            if path == "/api/youtube-oauth/start":
                # Flag ON + _authorized() (gated above). PKCE/state via build_auth_url.
                import youtube_label_step as _yls
                if not _yls.enabled():
                    return self._json({"ok": False, "error": "label_step_off"}, 404)
                if not isinstance(body, dict):
                    return self._json({"ok": False, "error": "Bad request"}, 400)
                raw = str(body.get("channel") or "MAIN").upper()
                ch = raw if raw in _yls.GRANT_CHANNELS else "MAIN"
                approval_id = str(body.get("approval_id") or body.get("id") or "regrant")[:64]
                url, err = _yls.build_auth_url(channel=ch, approval_id=approval_id)
                if not url:
                    return self._json({"ok": False, "error": err or "auth_url_failed"}, 400)
                return self._json({
                    "ok": True,
                    "oauth_url": url,
                    "channel": ch,
                    "regrant_url": _yls.regrant_hub_url(ch),
                })

            if path == "/api/post-ledger/unstick":
                # Flag ON + _authorized(). Validate ids; stale in_flight / timeout_pending / create_error / failed.
                import youtube_label_step as _yls
                import post_idempotency as _idem
                if not _yls.enabled():
                    return self._json({"ok": False, "error": "label_step_off"}, 404)
                if not isinstance(body, dict):
                    return self._json({"ok": False, "error": "Bad request"}, 400)
                job_id = str(body.get("job_id") or body.get("id") or "").strip()
                platform_key = str(body.get("platform") or body.get("platform_key") or "youtube:create").strip()[:32]
                if not _idem.validate_job_id(job_id):
                    return self._json({"ok": False, "error": "bad_job_id"}, 400)
                if not _idem.validate_platform_key(platform_key):
                    return self._json({"ok": False, "error": "bad_platform"}, 400)
                ok, row = _idem.unstick(
                    job_id, platform_key,
                    reason=str(body.get("reason") or "operator_unstick")[:200],
                )
                if not ok:
                    err = "unstick_failed"
                    if isinstance(row, dict):
                        err = str(row.get("error") or err)
                    return self._json({"ok": False, "error": _idem.redact_capability_urls(err)}, 400)
                public = {}
                if isinstance(row, dict):
                    for key in ("key", "job_id", "platform", "status", "error", "video_id"):
                        if row.get(key) is not None:
                            value = row.get(key)
                            public[key] = _idem.redact_capability_urls(value) if isinstance(value, str) else value
                return self._json({"ok": True, "row": public})

            if path == "/api/youtube-label/tick":
                # Authorized tick (same logic as daemon). Rate-limited; never creates.
                force = parse_tick_force(body.get("force") if isinstance(body, dict) else None)
                result = run_youtube_label_tick(force=force, approvals_path=ap)
                code = 200 if result.get("ok") or result.get("skipped") else (
                    404 if result.get("error") == "label_step_off" else 500
                )
                return self._json(result, code)

            # /api/events (append only; same _authorized gate as state/approvals)
            try:
                data, item, changed = append_event(load_events(ep), body)
            except BadRequest as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            if changed:
                save_events(data, ep)
                try:
                    import push_alerts as _push
                    _push.notify_event(item)
                except Exception:
                    pass
            return self._json(dict(data, ok=True, item=item, changed=changed))

        do_PUT = do_DELETE = do_PATCH = lambda self: self._send(b"read-only", "text/plain", 405)

    return H


def main():
    # Daemon tick only when label-step flag ON (no LaunchAgent). HTTP tick stays authorized.
    th = start_youtube_label_tick_daemon()
    srv = ThreadingHTTPServer((HOST, PORT), make_handler())
    print("Clipping Hub shell on http://%s:%d (local only, nothing posts)" % (HOST, PORT), flush=True)
    if th:
        print("YouTube label tick daemon started (flag ON)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_youtube_label_tick_daemon()


if __name__ == "__main__":
    sys.exit(main())
