"""Per-job+platform post keys: prevent double posts on retry/double-tap.

begin() takes an exclusive fcntl.flock on a sibling lockfile around check+append
so only one thread/process can acquire in_flight for a key.
Stuck in_flight rows older than IN_FLIGHT_TTL_S are marked stale for reconcile
(caller must look up Opus — never blind-repost).

Create-ledger state machine (job_id::platform):

| status           | begin()      | new POST? | next action                                      |
|------------------|--------------|-----------|--------------------------------------------------|
| (absent)         | ok True      | yes       | acquire in_flight, POST once                     |
| in_flight        | ok False     | no        | wait; if stale → reconcile only                  |
| timeout_pending  | ok False     | no        | reconcile only (exact match); never re-POST      |
| create_error     | ok False     | no        | terminal fail-closed; authorized unstick → failed|
| done             | ok False     | no        | terminal success                                 |
| failed           | ok True      | yes       | only after authorized unstick (or explicit fail) |

create_error: non-timeout create failure or missing postId. One deduped alert;
operator must unstick before any new POST.
timeout_pending: create timed out; reconcile only, never re-POST.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
LEDGER_PATH = Path(os.environ.get(
    "CLIPPING_HUB_POST_LEDGER",
    ROOT / "data" / "post_ledger.jsonl",
))
IN_FLIGHT_TTL_S = int(os.environ.get("CLIPPING_HUB_IN_FLIGHT_TTL_S", str(15 * 60)))

JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PLATFORM_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# A failed row may be retried only when every earlier row is one of these
# pre-request failures. Anything else may already have been accepted.
_PRE_REQUEST_FAILURES = frozenset({
    "youtube_channel_preflight_failed",
    "youtube_paid_label_unverified",
    "artifact_hash_mismatch",
    "youtube_grant_absent",
    "youtube_channel_unbound",
    "media_missing",
    "not_called",
    "no_adapter",
})
_UPLOAD_PLATFORM_KEYS = frozenset({"pub:youtube", "pub:youtube:promote"})


def validate_job_id(job_id: str) -> bool:
    return bool(isinstance(job_id, str) and JOB_ID_RE.fullmatch(job_id))


def validate_platform_key(platform_key: str) -> bool:
    return bool(isinstance(platform_key, str) and PLATFORM_KEY_RE.fullmatch(platform_key))


def make_key(job_id: str, platform_key: str) -> str:
    return f"{str(job_id)[:64]}::{str(platform_key)[:32]}"


def _lock_path(path=None) -> Path:
    p = Path(path) if path else LEDGER_PATH
    return Path(str(p) + ".lock")


@contextmanager
def ledger_lock(path=None):
    """Exclusive lock across threads and processes for ledger check+append."""
    lp = _lock_path(path)
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


class LedgerCorrupt(ValueError):
    """A public ledger line is not a usable row. Callers must not post."""


def parse_ledger_text(text):
    """Parse JSONL. Blank lines are ignored. A bad line fails the whole file.

    A valid legacy failure row (status failed, no remote id) is a normal row.
    It is not corrupt and it is not an existing video.
    """
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise LedgerCorrupt("ledger_corrupt") from exc
        if not isinstance(row, dict) or "key" not in row or "status" not in row:
            raise LedgerCorrupt("ledger_corrupt")
        rows.append(row)
    return rows


def _iter_rows(path=None):
    p = Path(path) if path else LEDGER_PATH
    if not p.is_file():
        return
    try:
        text = p.read_text()
    except OSError:
        return
    yield from parse_ledger_text(text)


def lookup(job_id: str, platform_key: str, path=None):
    key = make_key(job_id, platform_key)
    found = None
    for row in _iter_rows(path):
        if row.get("key") == key:
            found = row
    return found


def is_video_id(value):
    """True for an 11-character YouTube video id. A session URL is not an id."""
    text = str(value or "").strip()
    if not text or "://" in text or "upload_id" in text:
        return False
    return bool(_VIDEO_ID_RE.fullmatch(text))


def is_session_url(value):
    text = stored_remote(value)
    return bool(text and text.startswith("https://"))


def stored_remote(remote_id):
    """Persist a video id, or one https Google session URL. Other URLs are dropped.

    The session URL is how a later status query finds the upload. It is not a
    video id and must not be shown to the operator.
    """
    text = str(remote_id or "").strip()
    if not text or any(ch in text for ch in "\n\r\t "):
        return None
    if text.startswith("https://"):
        parts = urlsplit(text)
        host = (parts.hostname or "").rstrip(".").lower()
        if host != "www.googleapis.com" or parts.scheme != "https":
            return None
        if parts.port not in (None, 443) or parts.username or parts.password:
            return None
        if len(text) > 2048:
            return None
        return text
    if text.startswith("http://"):
        return None
    return text[:128] or None


def session_of(row):
    """Resumable session URL, if this row still has one. Never a video id."""
    if not isinstance(row, dict):
        return ""
    for key in ("session_url", "remote_id"):
        if is_session_url(row.get(key)):
            return stored_remote(row.get(key))
    return ""


def video_of(row):
    """Resolved video id. A session URL stored in remote_id is not a video id."""
    if not isinstance(row, dict):
        return ""
    for key in ("video_id", "remote_id"):
        text = str(row.get(key) or "").strip()
        if not text or "://" in text or "upload_id" in text:
            continue
        if key == "remote_id" and is_session_url(text):
            continue
        return text[:128]
    return ""


def _evidence(row):
    if not isinstance(row, dict):
        return {"session_url": "", "video_id": "", "upload_length": None, "session_observation": None}
    length = row.get("upload_length")
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        length = None
    observation = row.get("session_observation")
    if observation != "upload_incomplete":
        observation = None
    return {
        "session_url": session_of(row),
        "video_id": video_of(row),
        "upload_length": length,
        "session_observation": observation,
    }


def _merged_evidence(rows):
    found = {"session_url": "", "video_id": "", "upload_length": None, "session_observation": None}
    for row in rows or []:
        ev = _evidence(row)
        if ev["session_url"]:
            found["session_url"] = ev["session_url"]
        if ev["video_id"]:
            found["video_id"] = ev["video_id"]
        if ev["upload_length"] is not None:
            found["upload_length"] = ev["upload_length"]
        if ev["session_observation"]:
            found["session_observation"] = ev["session_observation"]
    return found


def _has_upload_evidence(row):
    ev = _evidence(row)
    return bool(ev["session_url"] or ev["video_id"] or ev["upload_length"] is not None or ev["session_observation"])


def _rows_for_key(path, key):
    return [row for row in _iter_rows(path) if row.get("key") == key]


def _rows_for_artifact(path, sha, account_id, platform_key):
    if not sha or not account_id:
        return []
    return [
        row for row in _iter_rows(path)
        if row.get("artifact_sha256") == sha
        and row.get("account_id") == account_id
        and row.get("platform") == platform_key
    ]


def history_blocks_insert(rows, platform_key):
    """True when any earlier attempt may already have created an upload.

    A later failed row does not erase that history. A channel-list failure
    before any session is the one retry that stays open.
    """
    rows = [row for row in (rows or []) if isinstance(row, dict)]
    if any(_has_upload_evidence(row) for row in rows):
        return True
    if platform_key not in _UPLOAD_PLATFORM_KEYS:
        return False
    for index, row in enumerate(rows):
        status = row.get("status")
        if status in ("unknown", "timeout_pending", "create_error", "private_uploaded", "done"):
            return True
        if status != "in_flight":
            continue
        closed = any(
            later.get("status") == "failed" and later.get("error") in _PRE_REQUEST_FAILURES
            for later in rows[index + 1:]
        )
        if not closed:
            return True
    return False


def _write_evidence(row, prior_rows, *, remote_id=None, video_id=None, session_url=None,
                    upload_length=None, session_observation=None):
    """Copy session, video id, and length forward. A video id does not replace the session."""
    ev = _merged_evidence(prior_rows)
    if is_session_url(session_url):
        ev["session_url"] = stored_remote(session_url)
    if is_session_url(remote_id):
        ev["session_url"] = stored_remote(remote_id)
    if video_of({"video_id": video_id}):
        ev["video_id"] = video_of({"video_id": video_id})
    elif video_of({"remote_id": remote_id}):
        ev["video_id"] = video_of({"remote_id": remote_id})
    if isinstance(upload_length, int) and not isinstance(upload_length, bool) and upload_length >= 0:
        ev["upload_length"] = upload_length
    if session_observation == "upload_incomplete":
        ev["session_observation"] = "upload_incomplete"
    if ev["session_url"]:
        row["session_url"] = ev["session_url"]
    if ev["video_id"]:
        row["video_id"] = ev["video_id"]
    if ev["video_id"]:
        row["remote_id"] = ev["video_id"]
    elif ev["session_url"]:
        row["remote_id"] = ev["session_url"]
    if ev["upload_length"] is not None:
        row["upload_length"] = ev["upload_length"]
    if ev["session_observation"]:
        row["session_observation"] = ev["session_observation"]
    return row


def redact_capability_urls(value):
    """Remove resumable session URLs from text that might reach a client or a log."""
    text = str(value or "")
    text = re.sub(r"https://www\.googleapis\.com/\S*", "[redacted]", text)
    text = re.sub(r"http://\S+", "[redacted]", text)
    text = re.sub(r"upload_id=[^\s&\"']*", "upload_id=[redacted]", text)
    return text


def append_row(row: dict, path=None):
    p = Path(path) if path else LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(p), flags, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(p, 0o600)
    return True


def _now_epoch(now=None) -> float:
    if isinstance(now, (int, float)):
        return float(now)
    if isinstance(now, str) and now.strip():
        try:
            s = now.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            if len(s) >= 5 and (s[-5] in "+-") and s[-3] != ":":
                s = s[:-2] + ":" + s[-2:]
            return datetime.fromisoformat(s).timestamp()
        except ValueError:
            pass
    return time.time()


def in_flight_age_s(row, *, now=None):
    if not isinstance(row, dict) or row.get("status") != "in_flight":
        return None
    at = row.get("at")
    if not at:
        return None
    try:
        return max(0.0, _now_epoch(now) - _now_epoch(at))
    except Exception:
        return None


def is_in_flight_stale(row, *, now=None, ttl_s=None) -> bool:
    age = in_flight_age_s(row, now=now)
    if age is None:
        return False
    limit = IN_FLIGHT_TTL_S if ttl_s is None else int(ttl_s)
    return age >= limit


def _find_artifact_locked(sha, account_id, platform_key, path):
    found = None
    if not sha or not account_id:
        return None
    for row in _iter_rows(path):
        if (row.get("artifact_sha256") == sha and row.get("account_id") == account_id
                and row.get("platform") == platform_key):
            found = row
    return found


def begin(job_id: str, platform_key: str, *, path=None, now=None, ttl_s=None,
          artifact_sha=None, account_id=None, repost=False):
    """Acquire in-flight lock under exclusive flock. Returns (ok, existing_or_new_row).

    ok False if done, create_error, in_flight (fresh or stale), or timeout_pending — NEVER retryable.
    create_error is terminal fail-closed until authorized unstick → failed.
    stale_in_flight / timeout_pending: reconcile only (still ok False — no new POST).
    ok True only when fresh/never-attempted or after explicit failed (post-unstick).
    """
    ts = now if isinstance(now, str) and now else time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with ledger_lock(path):
        try:
            existing = lookup(job_id, platform_key, path=path)
        except LedgerCorrupt:
            return False, {"status": "ledger_corrupt", "error": "ledger_corrupt", "ledger_corrupt": True}
        if existing:
            st = existing.get("status")
            if st == "private_uploaded":
                out = dict(existing)
                out["duplicate_artifact"] = True
                return False, out
            if st == "done" and not repost:
                out = dict(existing)
                out["duplicate_artifact"] = True
                return False, out
            if st == "done" and repost:
                existing = None
            if st == "create_error":
                out = dict(existing)
                out["create_error"] = True
                return False, out
            if st in ("timeout_pending", "unknown"):
                out = dict(existing)
                out["timeout_pending"] = st == "timeout_pending"
                out["unknown"] = True
                return False, out
            if st == "in_flight":
                if is_in_flight_stale(existing, now=now, ttl_s=ttl_s):
                    out = dict(existing)
                    out["stale_in_flight"] = True
                    return False, out
                return False, existing
            if st == "failed":
                # A new failed row must not hide an earlier session or video id.
                try:
                    key_rows = _rows_for_key(path, make_key(job_id, platform_key))
                except LedgerCorrupt:
                    return False, {"status": "ledger_corrupt", "error": "ledger_corrupt", "ledger_corrupt": True}
                if history_blocks_insert(key_rows, platform_key):
                    ev = _merged_evidence(key_rows)
                    return False, {
                        "status": "unknown",
                        "reconcile_required": True,
                        "unknown": True,
                        "video_id": ev["video_id"] or None,
                        "error": "upload_evidence_retained",
                    }
            # failed with no upload evidence → allow retry
        if artifact_sha and account_id:
            try:
                art_rows = _rows_for_artifact(path, artifact_sha, account_id, platform_key)
            except LedgerCorrupt:
                return False, {"status": "ledger_corrupt", "error": "ledger_corrupt", "ledger_corrupt": True}
            prior_art = art_rows[-1] if art_rows else None
            if prior_art and prior_art.get("status") in ("done", "private_uploaded"):
                if not repost or prior_art.get("status") == "private_uploaded":
                    out = dict(prior_art)
                    out["duplicate_artifact"] = True
                    out["video_id"] = video_of(prior_art) or None
                    if is_session_url(out.get("remote_id")):
                        out["remote_id"] = out.get("video_id")
                    out.pop("session_url", None)
                    return False, out
            if history_blocks_insert(art_rows, platform_key):
                ev = _merged_evidence(art_rows)
                return False, {
                    "status": "unknown",
                    "reconcile_required": True,
                    "unknown": True,
                    "video_id": ev["video_id"] or None,
                    "error": "upload_evidence_retained",
                }
            if prior_art:
                st_art = prior_art.get("status")
                if st_art in ("unknown", "timeout_pending", "in_flight"):
                    out = dict(prior_art)
                    out["reconcile_required"] = True
                    out["unknown"] = st_art in ("unknown", "timeout_pending")
                    return False, out
                if st_art in ("done", "private_uploaded") and not repost:
                    out = dict(prior_art)
                    out["duplicate_artifact"] = True
                    return False, out
                if st_art == "private_uploaded" and repost:
                    out = dict(prior_art)
                    out["duplicate_artifact"] = True
                    return False, out
        row = {
            "key": make_key(job_id, platform_key),
            "job_id": str(job_id)[:64],
            "platform": str(platform_key)[:32],
            "status": "in_flight",
            "opus_post_id": None,
            "artifact_sha256": str(artifact_sha or "")[:64] or None,
            "account_id": str(account_id or "")[:64] or None,
            "at": ts,
        }
        append_row(row, path=path)
        return True, row


def mark_done(job_id: str, platform_key: str, *, opus_post_id=None, path=None, now=None,
              artifact_sha=None, account_id=None):
    ts = now if isinstance(now, str) and now else time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with ledger_lock(path):
        prior = lookup(job_id, platform_key, path=path) or {}
        row = {
            "key": make_key(job_id, platform_key),
            "job_id": str(job_id)[:64],
            "platform": str(platform_key)[:32],
            "status": "done",
            "opus_post_id": str(opus_post_id or "")[:128] or None,
            "artifact_sha256": str(artifact_sha or prior.get("artifact_sha256") or "")[:64] or None,
            "account_id": str(account_id or prior.get("account_id") or "")[:64] or None,
            "at": ts,
        }
        _write_evidence(row, [prior])
        append_row(row, path=path)


def mark_failed(job_id: str, platform_key: str, *, error=None, path=None, now=None):
    ts = now if isinstance(now, str) and now else time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with ledger_lock(path):
        prior_rows = _rows_for_key(path, make_key(job_id, platform_key))
        prior = prior_rows[-1] if prior_rows else {}
        row = {
            "key": make_key(job_id, platform_key),
            "job_id": str(job_id)[:64],
            "platform": str(platform_key)[:32],
            "status": "failed",
            "opus_post_id": None,
            "artifact_sha256": str(prior.get("artifact_sha256") or "")[:64] or None,
            "account_id": str(prior.get("account_id") or "")[:64] or None,
            "error": redact_capability_urls(error or "")[:200],
            "at": ts,
        }
        _write_evidence(row, prior_rows)
        append_row(row, path=path)


def mark_create_error(
    job_id: str,
    platform_key: str,
    *,
    error=None,
    path=None,
    now=None,
    alerted=None,
    remote_id=None,
    artifact_sha=None,
    account_id=None,
    session_url=None,
    video_id=None,
):
    """Terminal fail-closed after non-timeout create error / missing postId. begin() refuses."""
    ts = now if isinstance(now, str) and now else time.strftime("%Y-%m-%dT%H:%M:%S%z")
    prior = lookup(job_id, platform_key, path=path) or {}
    already = prior.get("create_error_alerted")
    if alerted is not None:
        already = bool(alerted)
    with ledger_lock(path):
        prior_rows = _rows_for_key(path, make_key(job_id, platform_key))
        prior = prior_rows[-1] if prior_rows else prior
        row = {
            "key": make_key(job_id, platform_key),
            "job_id": str(job_id)[:64],
            "platform": str(platform_key)[:32],
            "status": "create_error",
            "opus_post_id": None,
            "error": redact_capability_urls(error or "create_error")[:200],
            "at": ts,
        }
        if artifact_sha or prior.get("artifact_sha256"):
            row["artifact_sha256"] = str(artifact_sha or prior.get("artifact_sha256") or "")[:64]
        if account_id or prior.get("account_id"):
            row["account_id"] = str(account_id or prior.get("account_id") or "")[:64]
        _write_evidence(row, prior_rows, remote_id=remote_id, video_id=video_id, session_url=session_url)
        if already:
            row["create_error_alerted"] = True
        append_row(row, path=path)
    return already


def mark_timeout_pending(

    job_id: str,
    platform_key: str,
    *,
    error=None,
    path=None,
    now=None,
    reconcile_alerted=None,
):
    """Create timed out / reconcile waiting: never blind re-POST. begin() will not retry."""
    ts = now if isinstance(now, str) and now else time.strftime("%Y-%m-%dT%H:%M:%S%z")
    # Preserve prior reconcile_alerted unless explicitly set
    prior = lookup(job_id, platform_key, path=path) or {}
    alerted = prior.get("reconcile_alerted")
    if reconcile_alerted is not None:
        alerted = bool(reconcile_alerted)
    with ledger_lock(path):
        prior_rows = _rows_for_key(path, make_key(job_id, platform_key))
        row = {
            "key": make_key(job_id, platform_key),
            "job_id": str(job_id)[:64],
            "platform": str(platform_key)[:32],
            "status": "timeout_pending",
            "opus_post_id": None,
            "error": redact_capability_urls(error or "create_timeout")[:200],
            "at": ts,
        }
        if prior_rows:
            row["artifact_sha256"] = str(prior_rows[-1].get("artifact_sha256") or "")[:64] or None
            row["account_id"] = str(prior_rows[-1].get("account_id") or "")[:64] or None
        _write_evidence(row, prior_rows)
        if alerted:
            row["reconcile_alerted"] = True
        append_row(row, path=path)


def mark_unknown(
    job_id: str,
    platform_key: str,
    *,
    error=None,
    path=None,
    now=None,
    remote_id=None,
    artifact_sha=None,
    account_id=None,
    upload_length=None,
    session_observation=None,
    video_id=None,
    session_url=None,
):
    """Timeout or accept without a permalink. begin() will not post again.

    session_observation records that a status query saw an unfinished session.
    It does not prove the session can never complete and does not allow a new insert.
    """
    ts = now if isinstance(now, str) and now else time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with ledger_lock(path):
        prior_rows = _rows_for_key(path, make_key(job_id, platform_key))
        prior = prior_rows[-1] if prior_rows else {}
        row = {
            "key": make_key(job_id, platform_key),
            "job_id": str(job_id)[:64],
            "platform": str(platform_key)[:32],
            "status": "unknown",
            "opus_post_id": None,
            "permalink": None,
            "artifact_sha256": str(artifact_sha or prior.get("artifact_sha256") or "")[:64] or None,
            "account_id": str(account_id or prior.get("account_id") or "")[:64] or None,
            "error": redact_capability_urls(error or "pending_reconcile")[:200],
            "at": ts,
        }
        _write_evidence(
            row, prior_rows, remote_id=remote_id, video_id=video_id, session_url=session_url,
            upload_length=upload_length, session_observation=session_observation,
        )
        append_row(row, path=path)
    return row


def unstick(job_id: str, platform_key: str, *, path=None, reason="operator_unstick", now=None):
    """Operator reset. Refuses any row that may already be an upload.

    A video id, a resumable session, or an unfinished YouTube insert is not
    conclusive. 308 is not conclusive. The refusal does not include the row.
    A proven pre-insert channel-list failure stays failed and can be retried
    through begin(); unstick is not required for that retry.
    """
    if not validate_job_id(job_id):
        return False, {"error": "bad_job_id"}
    if not validate_platform_key(platform_key):
        return False, {"error": "bad_platform"}
    key = make_key(job_id, platform_key)
    rows = _rows_for_key(path, key)
    existing = rows[-1] if rows else None
    if not existing:
        return False, {"error": "unknown_job"}
    if any(_has_upload_evidence(row) for row in rows):
        return False, {"error": "refuse_upload_evidence"}
    st = existing.get("status")
    if st == "done":
        return False, {"error": "refuse_done"}
    if platform_key in _UPLOAD_PLATFORM_KEYS and st in (
        "unknown", "timeout_pending", "in_flight", "create_error", "private_uploaded",
    ):
        return False, {"error": "refuse_unresolved_youtube_object"}
    if st == "in_flight" and not is_in_flight_stale(existing, now=now):
        return False, {"error": "refuse_fresh_in_flight"}
    if st not in ("in_flight", "timeout_pending", "unknown", "create_error", "failed"):
        return False, {"error": "refuse_status"}
    mark_failed(job_id, platform_key, error=str(reason or "operator_unstick")[:200], path=path, now=now)
    latest = lookup(job_id, platform_key, path=path) or {}
    public = {
        "key": latest.get("key"),
        "job_id": latest.get("job_id"),
        "platform": latest.get("platform"),
        "status": latest.get("status"),
        "error": redact_capability_urls(latest.get("error") or ""),
    }
    if video_of(latest):
        public["video_id"] = video_of(latest)
    return True, public
