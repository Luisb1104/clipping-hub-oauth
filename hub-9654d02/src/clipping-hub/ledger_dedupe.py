"""Read-only YouTube upload dedupe across the private-proof, promote, and post ledgers.

An item that already has a video id for the same item id and channel is not
uploaded again. When both the request and the ledger row carry a sha256, they
must match. A ledger that cannot be read or parsed fails closed. A missing
synthetic-media echo is never a label-off.
"""
from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path

PRIVATE_PROOF_NAME = "private-proof-ledger.jsonl"
PROMOTE_NAME = "promote-ledger.jsonl"
POST_NAME = "post_ledger.jsonl"
_VIDEO_ID = __import__("re").compile(r"^[A-Za-z0-9_-]{11}$")

# Owner checked this video in YouTube Studio. The API echo was absent.
# Those two facts stay separate fields. They are not a label-off.
OWNER_ITEM_ID = "sample-07"
OWNER_VIDEO_ID = "LM6jkXooWGc"
OWNER_CONFIRMED_AT = "2026-11-07T23:50-05:00"
OWNER_CONFIRM_SOURCE = "owner_youtube_studio_check"

_PROMOTE_STATUSES = frozenset({
    "readback_ok", "readback_mismatch", "readback_failed", "echo_unconfirmed",
})


def data_dir(explicit=None):
    if explicit:
        return Path(explicit)
    raw = os.environ.get("CLIPPING_HUB_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parent / "data"


def _video_id(row):
    if not isinstance(row, dict):
        return ""
    for key in ("video_id", "remote_id"):
        raw = row.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text or text.lower() == "null" or "://" in text or "upload_id" in text:
            continue
        if _VIDEO_ID.fullmatch(text):
            return text
    key = str(row.get("key") or "")
    if key.startswith("promote:"):
        tail = key.split(":")[-1].strip()
        if _VIDEO_ID.fullmatch(tail):
            return tail
    return ""


def _row_item_id(row):
    return str(row.get("item_id") or row.get("job_id") or "").strip()[:64]


def _row_channel(row):
    channel_id = str(row.get("channel_id") or "").strip()
    label = str(row.get("channel") or "").strip().upper()
    key = str(row.get("key") or "")
    parts = key.split(":")
    if key.startswith("private-proof:") and len(parts) == 4:
        label = label or parts[1].upper()
        channel_id = channel_id or parts[2]
    elif key.startswith("promote:") and len(parts) >= 4:
        label = label or parts[1].upper()
        channel_id = channel_id or parts[2]
    return channel_id[:64], label[:16]


def _row_sha(row):
    return str(row.get("sha256") or row.get("artifact_sha256") or "").strip()[:64]


def _channel_match(row, query):
    q = str(query or "").strip()
    if not q:
        return True
    channel_id, label = _row_channel(row)
    if q == channel_id or q.upper() == label:
        return True
    if q.upper() == "MAIN" and (label == "MAIN" or str(row.get("key") or "").find(":MAIN:") >= 0):
        return True
    return False


def _sha_match(row, query):
    q = str(query or "").strip()
    have = _row_sha(row)
    if q and have and q != have:
        return False
    return True


def _read_text(path):
    """Return (text, error). Missing is ('', None). Symlink or non-file fails closed."""
    dest = Path(path)
    try:
        st = os.lstat(dest)
    except FileNotFoundError:
        return "", None
    except OSError:
        return None, "ledger_unreadable"
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return None, "ledger_unreadable"
    try:
        fd = os.open(str(dest), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        reason = "ledger_unreadable" if exc.errno == errno.ELOOP else "ledger_unreadable"
        return None, reason
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None, "ledger_unreadable"
        chunks = []
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
            chunks.append(buf)
        try:
            return b"".join(chunks).decode("utf-8"), None
        except UnicodeError:
            return None, "ledger_corrupt"
    finally:
        os.close(fd)


def _parse_jsonl(text):
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError("ledger_corrupt") from exc
        if not isinstance(row, dict):
            raise ValueError("ledger_corrupt")
        rows.append(row)
    return rows


def iter_ledger_files(data=None):
    """Yield (source, path) for the three ledgers. Paths are de-duplicated."""
    root = data_dir(data)
    found = []

    def add(source, path):
        if not path:
            return
        key = os.path.abspath(str(path))
        if any(os.path.abspath(str(p)) == key for _, p in found):
            return
        found.append((source, Path(path)))

    env_private = os.environ.get("CLIPPING_HUB_PRIVATE_PROOF_LEDGER", "").strip()
    env_promote = os.environ.get("CLIPPING_HUB_PROMOTE_LEDGER", "").strip()
    env_post = os.environ.get("CLIPPING_HUB_POST_LEDGER", "").strip()
    if env_private:
        add("private_proof", Path(env_private).expanduser())
    if env_promote:
        add("promote", Path(env_promote).expanduser())
    if env_post:
        add("post", Path(env_post).expanduser())
    add("private_proof", root / PRIVATE_PROOF_NAME)
    add("promote", root / PROMOTE_NAME)
    add("post", root / POST_NAME)
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    for name in names:
        if name.startswith(".") or not name.endswith(".jsonl"):
            continue
        path = root / name
        if name == PROMOTE_NAME:
            add("promote", path)
        elif name == POST_NAME:
            add("post", path)
        elif name == PRIVATE_PROOF_NAME:
            add("private_proof", path)
        else:
            add("scan", path)
    return found


def load_rows(data=None):
    """Return ([(source, row), ...], error).

    Missing files are empty. Unreadable or corrupt ledger files fail closed.
    A jsonl in the data dir that is not a ledger and does not parse is ignored.
    """
    root = data_dir(data)
    rows = []
    for source, path in iter_ledger_files(root):
        text, err = _read_text(path)
        if err:
            # Named and env-selected ledgers fail closed. An unrelated unreadable
            # file in the data directory is not one of the three ledgers.
            if source in ("post", "promote", "private_proof"):
                return [], err
            continue
        if not text:
            continue
        markers = "private-proof:" in text or "promote:" in text or '"phase"' in text
        ledgerish = source in ("post", "promote", "private_proof") or markers
        if source == "scan" and not markers:
            continue
        try:
            parsed = _parse_jsonl(text)
        except ValueError:
            if ledgerish:
                return [], "ledger_corrupt"
            continue
        if source == "scan":
            if "promote:" in text or '"phase"' in text:
                source = "promote"
            elif "private-proof:" in text:
                source = "private_proof"
            else:
                continue
        for row in parsed:
            rows.append((source, row))
    return rows, None


def _hits(rows, *, item_id, channel_id="", sha256=""):
    item_id = str(item_id or "").strip()
    matched = []
    for source, row in rows:
        if _row_item_id(row) != item_id:
            continue
        if not _channel_match(row, channel_id):
            continue
        if not _sha_match(row, sha256):
            continue
        vid = _video_id(row)
        if not vid:
            continue
        matched.append((source, row, vid))
    return matched


def check_upload(item, *, sha256="", channel_id="", data_dir=None):
    """Return action proceed, skip, or fail.

    skip reason is already_uploaded:<video_id>. fail reason is ledger_corrupt,
    ledger_unreadable, or ledger_video_conflict. Nothing is written.
    """
    item_id = ""
    if isinstance(item, dict):
        item_id = str(item.get("id") or item.get("item_id") or "").strip()
        if not channel_id:
            channel_id = str(item.get("route_channel_id") or item.get("channel_id") or "").strip()
        if not sha256:
            sha256 = str(item.get("sha256") or item.get("artifact_sha256") or "").strip()
    if not item_id:
        return {"action": "proceed", "reason": "", "video_id": ""}
    rows, err = load_rows(data_dir)
    if err:
        return {"action": "fail", "reason": err, "video_id": ""}
    matched = _hits(rows, item_id=item_id, channel_id=channel_id, sha256=sha256)
    ids = []
    for _source, _row, vid in matched:
        if vid not in ids:
            ids.append(vid)
    if len(ids) > 1:
        return {"action": "fail", "reason": "ledger_video_conflict", "video_id": ""}
    if not ids:
        return {"action": "proceed", "reason": "", "video_id": ""}
    vid = ids[0]
    source = matched[-1][0]
    return {
        "action": "skip",
        "reason": "already_uploaded:" + vid,
        "video_id": vid,
        "source": source,
    }


def promote_facts(item_id, *, channel_id="", sha256="", data_dir=None):
    """Latest promote readback for one item. Echo stays a string when present.

    A missing echo is reported as echo=None. Callers must not store that as
    a false label.
    """
    rows, err = load_rows(data_dir)
    if err:
        return {"ok": False, "reason": err}
    matched = _hits(rows, item_id=item_id, channel_id=channel_id, sha256=sha256)
    if not matched:
        return {
            "ok": True, "video_id": "", "status": "", "echo": None, "echo_seen": False,
            "to_privacy": "", "wrote_update": None, "reason": "",
        }
    ids = []
    for _source, _row, vid in matched:
        if vid not in ids:
            ids.append(vid)
    if len(ids) > 1:
        return {"ok": False, "reason": "ledger_video_conflict"}
    video_id = ""
    status = ""
    echo = None
    echo_seen = False
    to_privacy = ""
    wrote_update = None
    for source, row, vid in matched:
        video_id = vid
        if source != "promote" and not str(row.get("key") or "").startswith("promote:") and row.get("phase") not in ("intent", "result"):
            continue
        phase = str(row.get("phase") or "")
        if phase == "intent" or row.get("to_privacy"):
            privacy = str(row.get("to_privacy") or "").strip().lower()
            if privacy in ("public", "private"):
                to_privacy = privacy
        if phase == "result" or str(row.get("status") or "") in _PROMOTE_STATUSES:
            got = str(row.get("status") or "").strip()
            if got:
                status = got
            if "contains_synthetic_media_echo" in row or "echo" in row:
                echo_seen = True
                raw = row["contains_synthetic_media_echo"] if "contains_synthetic_media_echo" in row else row.get("echo")
                if isinstance(raw, str) and raw.strip():
                    echo = raw.strip()[:32]
                else:
                    # Present but not a string (null/false). That is a missing
                    # echo, not a label switched off.
                    echo = None
            if "wrote_update" in row:
                wrote_update = True if row.get("wrote_update") is True else False if row.get("wrote_update") is False else None
    if not video_id:
        video_id = matched[-1][2]
    return {
        "ok": True,
        "video_id": video_id,
        "status": status,
        "echo": echo if echo_seen else None,
        "echo_seen": echo_seen,
        "to_privacy": to_privacy,
        "wrote_update": wrote_update,
        "reason": "",
    }
