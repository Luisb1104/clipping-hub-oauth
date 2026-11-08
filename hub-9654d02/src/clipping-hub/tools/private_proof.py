"""Private YouTube proof for one named local sample on the pinned MAIN channel.

Default is a dry-run and does not touch the network. --execute uploads only
after a durable ledger intent is fsynced. Tests inject HTTP and the refresh
callable. This session does not run --execute.

The real clip for a future proof is item sample-07 and file sample-07.mp4
(26.2s, 1080x1920, AI disclosure true, MAIN, Storyblocks Individual plus owned
audio). rights_ok is false and this tool does not certify it. sample07.mp4 in
the test fixtures is not that file.

The upload body is privacyStatus=private and containsSyntheticMedia=true.
public and unlisted are never sent. The result is not a public publish: it
does not approve the queue, does not write accounts, rights, or terms, and
does not use the public post ledger.

Token policy: youtube_label_step.refresh_access persists the new access token
when persist is true. This proof calls it with persist=False, so a future
live refresh would not write the token file. No token write is authorized here.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import publish_adapters as adapters
import publish_runtime as runtime
import schedule_hook as sched

# Future proof identity. Not a certification and not a bundled media file.
PROOF_ITEM_ID = "sample-07"
PROOF_SAMPLE = "sample-07.mp4"

PUBLIC_LEDGER_NAMES = {"post_ledger.jsonl"}
_BLOCKING = frozenset({
    "uploading", "uploaded", "interrupted", "readback_ok", "readback_failed",
    "readback_mismatch", "echo_unconfirmed",
})
_PUBLIC_KEEP = frozenset({"done", "unknown", "create_error", "timeout_pending", "in_flight"})
_PRIVATE_INIT = (
    "https://www.googleapis.com/upload/youtube/v3/videos"
    "?uploadType=resumable&part=snippet,status"
)
_READ_URL = "https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id="

_io_write = os.write
_io_fsync = os.fsync


class LedgerError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def app_data_dir():
    raw = os.environ.get("CLIPPING_HUB_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data"


def _public_ledger_paths():
    raw = os.environ.get("CLIPPING_HUB_POST_LEDGER", "").strip()
    paths = [app_data_dir() / "post_ledger.jsonl"]
    if raw:
        paths.append(Path(raw).expanduser())
    paths.append(Path("data") / "post_ledger.jsonl")
    return paths


def _same_inode(path, other):
    try:
        a = os.stat(path, follow_symlinks=False)
        b = os.stat(other, follow_symlinks=False)
    except OSError:
        return False
    return a.st_dev == b.st_dev and a.st_ino == b.st_ino


def ledger_is_public(path):
    candidate = Path(path).expanduser()
    if candidate.name in PUBLIC_LEDGER_NAMES:
        return True
    for pub in _public_ledger_paths():
        pub_path = pub.expanduser()
        try:
            if candidate.resolve() == pub_path.resolve():
                return True
        except OSError:
            if str(candidate) == str(pub_path):
                return True
        if candidate.exists() and pub_path.exists() and _same_inode(candidate, pub_path):
            return True
    return False


def ledger_location_error(path):
    """Ledger must be one regular name inside the app data directory."""
    data = app_data_dir()
    try:
        dst = os.lstat(data)
    except OSError:
        return "data_dir_missing"
    if stat.S_ISLNK(dst.st_mode) or not stat.S_ISDIR(dst.st_mode):
        return "data_dir_symlink"
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = data / candidate
    if candidate.name in PUBLIC_LEDGER_NAMES or candidate.name.startswith("."):
        return "ledger_is_public"
    if candidate.parent != data and candidate.parent.resolve() != data.resolve():
        return "ledger_outside_data_dir"
    try:
        if candidate.parent.resolve() != data.resolve():
            return "ledger_outside_data_dir"
    except OSError:
        return "ledger_outside_data_dir"
    if ".." in Path(path).parts:
        return "ledger_outside_data_dir"
    if candidate.exists() or candidate.is_symlink():
        try:
            st = os.lstat(candidate)
        except OSError:
            return "ledger_symlink"
        if stat.S_ISLNK(st.st_mode):
            return "ledger_symlink"
    if ledger_is_public(candidate):
        return "ledger_is_public"
    return None


def _read_nofollow(path):
    """Read a regular file without following a symlink. Missing is empty."""
    dest = Path(path)
    if not dest.exists() and not dest.is_symlink():
        return "", None
    try:
        fd = os.open(str(dest), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        reason = "ledger_symlink" if exc.errno == errno.ELOOP else "ledger_unreadable"
        return None, reason
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, "ledger_symlink"
        chunks = []
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
            chunks.append(buf)
        return b"".join(chunks).decode(), None
    except UnicodeError:
        return None, "ledger_corrupt"
    finally:
        os.close(fd)


def _video_id_of(row):
    if not isinstance(row, dict):
        return ""
    import post_idempotency as idem
    found = idem.video_of(row)
    if found:
        return found[:64]
    opus = str(row.get("opus_post_id") or "").strip()
    if opus and opus.lower() != "null" and "://" not in opus and "upload_id" not in opus:
        return opus[:64]
    return ""


def _parse_proof_key(key):
    """Identity stored in private-proof:MAIN:{channel}:{sha}.

    None means the key is not a private-proof key. A private-proof key that
    does not carry a MAIN channel id and a sha is malformed.
    """
    text = str(key or "")
    if not text.startswith("private-proof:"):
        return None
    parts = text.split(":")
    if len(parts) != 4 or parts[0] != "private-proof" or parts[1] != "MAIN":
        return {"malformed": True}
    channel, sha = parts[2], parts[3]
    if not adapters.youtube_channel_id_ok(channel) or not sha:
        return {"malformed": True}
    return {"channel": channel, "sha": sha}


def _reconcile_proof_identity(row):
    """Fill a missing channel or sha from the legacy proof key. Conflicts fail closed."""
    if not isinstance(row, dict):
        return {"malformed": True}
    parsed = _parse_proof_key(row.get("key"))
    field_channel = str(row.get("channel_id") or "").strip()
    field_sha = str(row.get("sha256") or row.get("artifact_sha256") or "").strip()
    if parsed is None:
        return {"channel_id": field_channel[:64], "sha256": field_sha[:64]}
    if parsed.get("malformed"):
        return {"malformed": True}
    if field_channel and field_channel != parsed["channel"]:
        return {"conflict": True}
    if field_sha and field_sha != parsed["sha"]:
        return {"conflict": True}
    return {
        "channel_id": (field_channel or parsed["channel"])[:64],
        "sha256": (field_sha or parsed["sha"])[:64],
    }


def _row_matches_object(row, item_id, sha256, channel_id):
    """A video id matches in any status. A failed row with no video id is not a video."""
    if not isinstance(row, dict):
        return False
    status = str(row.get("status") or "")
    item_hit = bool(item_id) and (
        str(row.get("item_id") or "") == item_id or str(row.get("job_id") or "") == item_id
    )
    sha_hit = bool(sha256) and (
        str(row.get("sha256") or "") == sha256
        or str(row.get("artifact_sha256") or "") == sha256
        or (sha256 in str(row.get("key") or ""))
    )
    if not item_hit and not sha_hit:
        return False
    key = str(row.get("key") or "")
    platform = str(row.get("platform") or "")
    proof = key.startswith("private-proof:")
    youtube = proof or platform in ("youtube", "pub:youtube") or "youtube" in key
    if not youtube:
        return False
    if _video_id_of(row):
        return True
    if status == "failed":
        return False
    if proof and status in _BLOCKING:
        return True
    return status in _PUBLIC_KEEP


def find_existing_youtube(*, item_id="", sha256="", channel_id="", data_dir=None, exclude=None):
    """Scan private-proof ledgers and the public ledger. Does not write the queue.

    A corrupt private-proof file fails closed. Public rows whose latest status
    is failed are ignored, including oauth_required rows with no video id.
    Symlinks are not followed.
    """
    data = Path(data_dir) if data_dir else app_data_dir()
    try:
        dst = os.lstat(data)
    except OSError:
        return None
    if stat.S_ISLNK(dst.st_mode) or not stat.S_ISDIR(dst.st_mode):
        return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
    hits = []
    try:
        names = sorted(os.listdir(data))
    except OSError:
        return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
    for name in names:
        if name.startswith(".") or name.endswith(".lock") or name in PUBLIC_LEDGER_NAMES:
            continue
        if not name.endswith(".jsonl"):
            continue
        path = data / name
        try:
            st = os.lstat(path)
        except OSError:
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        if stat.S_ISLNK(st.st_mode):
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        if not stat.S_ISREG(st.st_mode):
            continue
        if exclude and (_same_inode(path, exclude) or os.path.abspath(str(path)) == os.path.abspath(str(exclude))):
            continue
        if ledger_is_public(path):
            continue
        text, err = _read_nofollow(path)
        if err or text is None:
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        if "private-proof:" not in text:
            continue
        try:
            rows = _parse_ledger(text)
        except LedgerError:
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        for row in rows:
            if not str(row.get("key") or "").startswith("private-proof:"):
                continue
            ident = _reconcile_proof_identity(row)
            if ident.get("malformed") or ident.get("conflict"):
                return {
                    "corrupt": True, "blocked": True,
                    "reason": "proof_identity_malformed" if ident.get("malformed") else "proof_identity_conflict",
                    "video_id": _video_id_of(row) or None,
                }
        latest = {}
        for row in rows:
            latest[str(row.get("key") or "")] = row
        seen_rows = list(latest.values())
        for row in rows:
            if _video_id_of(row) and row not in seen_rows:
                seen_rows.append(row)
        for row in seen_rows:
            if _row_matches_object(row, item_id, sha256, channel_id):
                hits.append((row, "private_proof", _reconcile_proof_identity(row)))
    public_paths = []
    raw_public = os.environ.get("CLIPPING_HUB_POST_LEDGER", "").strip()
    if raw_public:
        public_paths.append(Path(raw_public).expanduser())
    public_paths.append(data / "post_ledger.jsonl")
    seen = set()
    for path in public_paths:
        try:
            key = str(path)
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if not path.exists() and not path.is_symlink():
            continue
        try:
            st = os.lstat(path)
        except OSError:
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        text, err = _read_nofollow(path)
        if err or text is None:
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        if "private-proof:" in text:
            return {"corrupt": True, "reason": "private_ledger_corrupt", "video_id": None}
        try:
            import post_idempotency as idem
            parsed = idem.parse_ledger_text(text)
        except Exception:
            return {"corrupt": True, "reason": "public_ledger_corrupt", "video_id": None}
        latest = {}
        for row in parsed:
            latest[str(row.get("key"))] = row
        seen_rows = list(latest.values())
        for row in parsed:
            if _video_id_of(row) and row not in seen_rows:
                seen_rows.append(row)
        for row in seen_rows:
            if _row_matches_object(row, item_id, sha256, channel_id):
                hits.append((row, "public_ledger", _reconcile_proof_identity(row)))
    if not hits:
        return None
    ids = []
    channels = []
    shas = []
    for row, source, ident in hits:
        vid = _video_id_of(row)
        if vid and vid not in ids:
            ids.append(vid)
        ch = str((ident or {}).get("channel_id") or "")
        digest = str((ident or {}).get("sha256") or "")
        if ch and ch not in channels:
            channels.append(ch)
        if digest and digest not in shas:
            shas.append(digest)
    if len(ids) > 1:
        return {
            "corrupt": False, "blocked": True, "reason": "existing_video_conflict",
            "video_id": None, "status": "conflict", "source": "cross_ledger",
        }
    if len(channels) > 1 or len(shas) > 1:
        return {
            "corrupt": True, "blocked": True, "reason": "proof_identity_conflict",
            "video_id": ids[0] if ids else None,
        }
    row, source, ident = hits[-1]
    for candidate in hits:
        if (candidate[2] or {}).get("channel_id"):
            row, source, ident = candidate
            break
    vid = ids[0] if ids else None
    return {
        "corrupt": False,
        "blocked": True,
        "reason": "existing_video_reconcile",
        "video_id": vid,
        "status": str(row.get("status") or ""),
        "source": source,
        "item_id": str(row.get("item_id") or row.get("job_id") or "")[:64],
        "sha256": str((ident or {}).get("sha256") or row.get("sha256") or row.get("artifact_sha256") or "")[:64],
        "channel_id": str((ident or {}).get("channel_id") or row.get("channel_id") or "")[:64],
    }


def plan_private_proof(*, item_id, channel, ledger, sample=None, channel_id=None):
    if not item_id or not channel or not ledger:
        raise ValueError("item, channel, and ledger are required")
    loc = ledger_location_error(ledger)
    if loc:
        raise ValueError(loc)
    if str(channel).strip().upper() != "MAIN":
        raise ValueError("channel_not_main")
    return {
        "mode": "private_proof_plan",
        "executes_network": False,
        "public_success": False,
        "marks_public_posted": False,
        "rights_certified": False,
        "item_id": str(item_id)[:64],
        "channel": "MAIN",
        "channel_id": str(channel_id or "")[:64],
        "sample": str(sample or "")[:80],
        "proof_item_id": PROOF_ITEM_ID,
        "proof_sample": PROOF_SAMPLE,
        "ai_label": True,
        "privacy": "private",
        "contains_synthetic_media": True,
        "readback_required": ["privacyStatus", "containsSyntheticMedia", "channelId"],
        "ledger": str(ledger),
        "ledger_key_prefix": "private-proof:",
        "distinct_from_public_ledger": True,
        "token_write": False,
    }


def _private_body(title):
    body = {
        "snippet": {"title": (title or "private proof")[:100], "description": "", "categoryId": "22"},
        "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
    }
    privacy = body["status"]["privacyStatus"]
    if privacy != "private" or privacy in ("public", "unlisted"):
        raise RuntimeError("refusing_non_private_status")
    raw = json.dumps(body).encode()
    if b'"public"' in raw or b'"unlisted"' in raw:
        raise RuntimeError("refusing_non_private_status")
    return raw


def _parse_ledger(text):
    if text and not text.endswith("\n"):
        raise LedgerError("ledger_corrupt")
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise LedgerError("ledger_corrupt") from exc
        if not isinstance(row, dict) or "key" not in row or "status" not in row:
            raise LedgerError("ledger_corrupt")
        rows.append(row)
    return rows


def _read_ledger(path):
    dest = Path(path)
    if not dest.exists() and not dest.is_symlink():
        return []
    try:
        fd = os.open(str(dest), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise LedgerError("ledger_symlink" if exc.errno == errno.ELOOP else "ledger_unreadable") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LedgerError("ledger_symlink")
        chunks = []
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
            chunks.append(buf)
        text = b"".join(chunks).decode()
    finally:
        os.close(fd)
    return _parse_ledger(text)


def _commit(path, rows):
    """Atomically replace the ledger, then fsync the file and its directory."""
    dest = Path(path)
    directory = dest.parent
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    tmp = directory / (dest.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        fd = os.open(str(tmp), flags, 0o600)
    except FileExistsError:
        try:
            probe = os.open(str(tmp), os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise LedgerError("ledger_tmp_symlink") from exc
        os.close(probe)
        os.unlink(tmp)
        fd = os.open(str(tmp), flags, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LedgerError("ledger_not_regular")
        written = _io_write(fd, payload)
        if written != len(payload):
            raise LedgerError("ledger_short_write")
        _io_fsync(fd)
    except LedgerError:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    except OSError as exc:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise LedgerError("ledger_fsync_failed") from exc
    else:
        os.close(fd)
    os.replace(tmp, dest)
    dirfd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
    try:
        _io_fsync(dirfd)
    except OSError as exc:
        raise LedgerError("ledger_fsync_failed") from exc
    finally:
        os.close(dirfd)
    checked = _read_ledger(dest)
    if [json.dumps(r, sort_keys=True) for r in checked] != [json.dumps(r, sort_keys=True) for r in rows]:
        raise LedgerError("ledger_verify_failed")


def _lock(path):
    dest = Path(path)
    lock_path = dest.parent / (dest.name + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LedgerError("ledger_lock_symlink")
        fcntl.flock(fd, fcntl.LOCK_EX)
    except LedgerError:
        os.close(fd)
        raise
    return fd


def _unlock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _key(channel_id, sha):
    return "private-proof:MAIN:%s:%s" % (channel_id, sha)


def _latest(rows, key):
    found = None
    for row in rows:
        if row.get("key") == key:
            found = row
    return found


def _result(status, *, reason=None, video_id=None, called=False, channel_id=""):
    return {
        "mode": "private_proof_execute",
        "executes_network": bool(called),
        "public_success": False,
        "marks_public_posted": False,
        "rights_certified": False,
        "token_write": False,
        "ok": status == "readback_ok",
        "status": status,
        "reason": reason,
        "video_id": video_id or None,
        "privacy": "private",
        "contains_synthetic_media": True,
        "channel": "MAIN",
        "channel_id": channel_id,
    }


def _pinned_channel_id(channel_id, targets):
    pinned = str(channel_id or "").strip()
    main = str((((targets or {}).get("targets") or {}).get("MAIN") or {}).get("yt") or "").strip()
    known = sched.MAIN_YOUTUBE_CHANNEL_ID
    if not adapters.youtube_channel_id_ok(pinned) or not adapters.youtube_channel_id_ok(main):
        return None, "channel_id_missing"
    if pinned != known or main != known or pinned != main:
        return None, "channel_id_mismatch"
    return pinned, None


def _sample_bytes(sample):
    name = str(sample or "")
    if not name or name != Path(name).name:
        return None, None, "sample_not_basename"
    path = adapters.open_sample(name)
    if path is None:
        return None, None, "sample_missing"
    data = path.read_bytes()
    if not data:
        return None, None, "sample_empty"
    return data, hashlib.sha256(data).hexdigest(), None


def _token_shape(token, channel_id):
    if not isinstance(token, dict):
        return "token_missing"
    refresh = str(token.get("refresh_token") or "")
    bound = str(token.get("bound_channel_id") or "").strip()
    if not refresh or any(c.isspace() or ord(c) < 32 for c in refresh):
        return "token_missing"
    if not bound or bound != channel_id:
        return "token_channel_mismatch"
    return None


def _read_video(payload):
    if not isinstance(payload, dict):
        return {}
    items = payload.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return payload


def nonpersisting_refresh(channel, token, http_post):
    """Refresh in memory. Does not call save_token."""
    import youtube_label_step as yls
    return yls.refresh_access(channel, token=token, persist=False, http_post=http_post)


def _lock_objects():
    """One lock for every YouTube create, so two ledgers cannot both upload.

    A missing data directory is created mode 0700 and then locked. If the
    directory cannot be created or the lock cannot be held, the error is
    returned and the caller must not upload.
    """
    data = app_data_dir()
    try:
        st = os.lstat(data)
    except OSError:
        try:
            data.mkdir(parents=True, mode=0o700)
        except OSError:
            return None, "data_dir_missing"
        try:
            st = os.lstat(data)
        except OSError:
            return None, "data_dir_missing"
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return None, "private_ledger_corrupt"
    try:
        fd = os.open(str(data / ".youtube-object.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    except OSError:
        return None, "private_ledger_corrupt"
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            return None, "private_ledger_corrupt"
        fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        os.close(fd)
        return None, "private_ledger_corrupt"
    return fd, None


def _unlock_objects(fd):
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def execute_private_proof(*, item_id, channel, channel_id, sample, ledger, token, http, refresh, targets=None):
    """Upload one sample privately, then read it back.

    refresh(channel, token) must return (access_token, error) and must not
    write the token file. The raw access_token on the token dict is not used.
    """
    if str(channel or "").strip().upper() != "MAIN":
        return _result("refused", reason="channel_not_main")
    loc = ledger_location_error(ledger)
    if loc:
        return _result("refused", reason=loc)
    cfg = targets if isinstance(targets, dict) else sched.load_targets()
    pinned, err = _pinned_channel_id(channel_id, cfg)
    if err:
        return _result("refused", reason=err, channel_id=str(channel_id or ""))
    data, sha, serr = _sample_bytes(sample)
    if serr:
        return _result("refused", reason=serr, channel_id=pinned)
    terr = _token_shape(token, pinned)
    if terr:
        return _result("refused", reason=terr, channel_id=pinned)
    if not callable(refresh):
        return _result("refused", reason="refresh_required", channel_id=pinned)
    if http is None:
        return _result("refused", reason="live_network_disabled", channel_id=pinned)
    key = _key(pinned, sha)
    dest = Path(ledger).expanduser()
    if not dest.is_absolute():
        dest = app_data_dir() / dest
    obj_lock, obj_err = _lock_objects()
    if obj_err or obj_lock is None:
        return _result("refused", reason=obj_err or "youtube_object_lock_unavailable", channel_id=pinned)
    lock = _lock(dest)
    called = False
    try:
        hit = find_existing_youtube(
            item_id=str(item_id or ""), sha256=sha, channel_id=pinned, exclude=dest,
        )
        if hit and hit.get("corrupt"):
            return _result(
                "refused", reason=str(hit.get("reason") or "private_ledger_corrupt")[:80],
                channel_id=pinned,
            )
        if hit:
            return _result(
                "duplicate", reason=hit.get("reason") or "existing_video_reconcile",
                video_id=hit.get("video_id"), called=False, channel_id=pinned,
            )
        try:
            rows = _read_ledger(dest)
        except LedgerError as exc:
            return _result("refused", reason=exc.reason, channel_id=pinned)
        prior = _latest(rows, key)
        if prior and (prior.get("video_id") or prior.get("status") in _BLOCKING):
            return _result(
                "duplicate", reason="private_proof_already_attempted",
                video_id=prior.get("video_id") or None, channel_id=pinned,
            )
        access, rerr = refresh("MAIN", token)
        if rerr or not access:
            return _result("refused", reason=rerr or "refresh_failed", channel_id=pinned)
        intent = {
            "key": key, "status": "uploading", "video_id": None, "item_id": str(item_id)[:64],
            "sample": Path(sample).name, "sha256": sha, "channel_id": pinned,
            "public_success": False, "token_write": False,
        }
        rows.append(intent)
        try:
            _commit(dest, rows)
        except LedgerError as exc:
            return _result("refused", reason=exc.reason, channel_id=pinned)
        raw = _private_body(str(item_id or sample))
        headers = {
            "Authorization": "Bearer " + str(access),
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(len(data)),
            "X-Upload-Content-Type": "video/mp4",
        }
        called = True
        try:
            init = http("POST", _PRIVATE_INIT, headers, raw)
        except TimeoutError:
            _record(dest, rows, key, "interrupted", None, sha)
            return _result("interrupted", reason="upload_timeout", called=True, channel_id=pinned)
        status = int((init or {}).get("status") or 0)
        location = ((init or {}).get("headers") or {}).get("Location") or ((init or {}).get("headers") or {}).get("location")
        if status != 200 or not adapters.youtube_put_location_ok(location):
            _record(dest, rows, key, "interrupted", None, sha)
            return _result("interrupted", reason="youtube_session_failed", called=True, channel_id=pinned)
        try:
            put = http("PUT", location, {
                "Authorization": "Bearer " + str(access),
                "Content-Type": "video/mp4",
                "Content-Length": str(len(data)),
            }, data)
        except TimeoutError:
            _record(dest, rows, key, "interrupted", None, sha)
            return _result("interrupted", reason="upload_timeout", called=True, channel_id=pinned)
        put_status = int((put or {}).get("status") or 0)
        video = (put or {}).get("json") or {}
        video_id = str(video.get("id") or "")
        if put_status not in (200, 201) or not video_id:
            _record(dest, rows, key, "interrupted", video_id or None, sha)
            return _result(
                "interrupted", reason="youtube_upload_incomplete",
                video_id=video_id or None, called=True, channel_id=pinned,
            )
        _record(dest, rows, key, "uploaded", video_id, sha)
        try:
            got = http("GET", _READ_URL + video_id, {"Authorization": "Bearer " + str(access)}, None)
        except TimeoutError:
            _record(dest, rows, key, "readback_failed", video_id, sha)
            return _result("readback_failed", reason="readback_timeout", video_id=video_id, called=True, channel_id=pinned)
        item = _read_video((got or {}).get("json") or {})
        status_obj = item.get("status") if isinstance(item.get("status"), dict) else {}
        privacy = str((status_obj.get("privacyStatus") or "")).lower()
        got_channel = str(((item.get("snippet") or {}).get("channelId") or status_obj.get("channelId") or ""))
        if privacy != "private" or got_channel != pinned:
            reason = "channel_mismatch" if got_channel != pinned else "private_label_not_confirmed"
            _record(dest, rows, key, "readback_mismatch", video_id, sha, reason=reason)
            return _result("readback_mismatch", reason=reason, video_id=video_id, called=True, channel_id=pinned)
        if "containsSyntheticMedia" not in status_obj:
            _record(dest, rows, key, "echo_unconfirmed", video_id, sha, reason="youtube_synthetic_echo_omitted")
            return _result(
                "echo_unconfirmed", reason="youtube_synthetic_echo_omitted",
                video_id=video_id, called=True, channel_id=pinned,
            )
        if status_obj.get("containsSyntheticMedia") is not True:
            _record(dest, rows, key, "readback_mismatch", video_id, sha, reason="private_label_not_confirmed")
            return _result(
                "readback_mismatch", reason="private_label_not_confirmed",
                video_id=video_id, called=True, channel_id=pinned,
            )
        _record(dest, rows, key, "readback_ok", video_id, sha)
        return _result("readback_ok", video_id=video_id, called=True, channel_id=pinned)
    finally:
        _unlock(lock)
        _unlock_objects(obj_lock)
        if not called:
            pass


def _prior_identity(rows, key):
    item_id = channel_id = sample = ""
    for row in rows:
        if str(row.get("key") or "") != str(key):
            continue
        if row.get("item_id"):
            item_id = str(row.get("item_id"))[:64]
        if row.get("channel_id"):
            channel_id = str(row.get("channel_id"))[:64]
        if row.get("sample"):
            sample = str(row.get("sample"))[:80]
    return item_id, channel_id, sample


def _record(path, rows, key, status, video_id, sha, reason=None, item_id=None, channel_id=None, sample=None):
    """Append a proof row. Later rows keep the item id and artifact hash."""
    prev_item, prev_channel, prev_sample = _prior_identity(rows, key)
    row = {
        "key": key,
        "status": status,
        "video_id": video_id,
        "public_success": False,
        "sha256": sha,
        "item_id": str(item_id or prev_item or "")[:64],
        "channel_id": str(channel_id or prev_channel or "")[:64],
        "sample": str(sample or prev_sample or "")[:80],
        "token_write": False,
    }
    if reason:
        row["reason"] = reason
    rows.append(row)
    try:
        _commit(path, rows)
    except LedgerError:
        return False
    return True


def _grab(argv, flag):
    if flag not in argv:
        return ""
    i = argv.index(flag)
    return argv[i + 1] if i + 1 < len(argv) else ""


def _token_from_file(path):
    """One-descriptor read. A symlink fails closed."""
    raw, err = runtime.read_regular_0600(path)
    if err or raw is None:
        return None
    try:
        data = json.loads(raw.decode())
    except (UnicodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv:
        print("Usage: python3 tools/private_proof.py --item sample-07 --channel MAIN --channel-id UC... --sample sample-07.mp4 --ledger PATH")
        print("PATH is one file inside the app data directory, not the public post ledger.")
        print("Add --execute to upload that one sample as private. Default prints a plan and does not upload.")
        print("rights_ok is not set. A private readback is not a public post.")
        return 0
    item_id = _grab(argv, "--item")
    channel = _grab(argv, "--channel")
    ledger = _grab(argv, "--ledger")
    sample = _grab(argv, "--sample")
    channel_id = _grab(argv, "--channel-id")
    if not item_id or not channel or not ledger:
        print("item, channel, and ledger are required", file=sys.stderr)
        return 2
    try:
        plan = plan_private_proof(
            item_id=item_id, channel=channel, ledger=ledger, sample=sample, channel_id=channel_id,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if "--execute" not in argv:
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if not sample or not channel_id:
        print("execute requires --sample and --channel-id", file=sys.stderr)
        return 2
    token_path = os.environ.get("CLIP_YT_PROOF_TOKEN_FILE", "").strip()
    token = _token_from_file(token_path) if token_path else None
    if token is None:
        print("token_missing", file=sys.stderr)
        return 2
    body = execute_private_proof(
        item_id=item_id, channel=channel, channel_id=channel_id, sample=sample,
        ledger=ledger, token=token, http=default_http,
        refresh=lambda ch, tok: nonpersisting_refresh(ch, tok, _form_post),
    )
    json.dump(body, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if body.get("status") == "readback_ok":
        return 0
    if body.get("status") == "duplicate":
        return 3
    if body.get("status") == "refused":
        return 2
    return 1


def _form_post(url, body):
    """Token-endpoint POST for a future --execute. Not called by tests or this session."""
    import urllib.parse
    import urllib.request
    raw = urllib.parse.urlencode(body).encode()
    req = urllib.request.Request(url, data=raw, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def default_http(method, url, headers, body):
    """Used only by an explicit CLI --execute. Tests inject their own client."""
    import urllib.error
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None

    data = body if isinstance(body, bytes) else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=60) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode() or "{}") if raw else {}
            return {"status": resp.status, "headers": dict(resp.headers.items()), "json": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode() or "{}")
        except ValueError:
            parsed = {}
        return {"status": exc.code, "headers": dict(exc.headers.items()) if exc.headers else {}, "json": parsed}


if __name__ == "__main__":
    raise SystemExit(main())
