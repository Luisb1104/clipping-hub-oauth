"""Outside-git publish identity. This module does not ship secrets and does not log them.

CLIPPING_HUB_PUBLISH_CONFIG points at a JSON file. When unset, the path is
~/.config/clipping-hub/publish-config.json. A missing file is an empty config,
not a guessed account. Tests point the env var at a temp file so a real home
config is never opened.

A platform is returned only when available is true and the documented identity,
secret shape, and scopes or tasks are present. The secret value is kept for the
adapter and is never copied into an error string.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

IG_SCOPES = frozenset({"instagram_content_publish"})
IG_PAID_SCOPES = frozenset({"instagram_basic", "instagram_branded_content_creator"})
FB_SCOPES = frozenset({"pages_show_list", "pages_read_engagement", "pages_manage_posts"})
FB_TASKS = frozenset({"CREATE_CONTENT"})
_ID = re.compile(r"^[0-9]{5,32}$")
_SECRET = re.compile(r"^[^\s\x00-\x1f\x7f]{8,4096}$")
_NAME = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


def config_path():
    raw = os.environ.get("CLIPPING_HUB_PUBLISH_CONFIG", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".config" / "clipping-hub" / "publish-config.json"


def _problems():
    return _STATE.setdefault("problems", [])


class _State(dict):
    pass


_STATE = _State(problems=[])


def config_problems():
    """Validation notes from the last load. No secret values."""
    load_publish_credentials()
    return list(_STATE.get("problems") or [])


def _note(platform, problem):
    _problems().append({"platform": platform, "problem": problem})


def _scopes(raw):
    if not isinstance(raw, list):
        return None
    out = []
    for item in raw:
        if not isinstance(item, str) or not _NAME.fullmatch(item):
            return None
        if item not in out:
            out.append(item)
    return out


def _instagram(row):
    if not isinstance(row, dict) or row.get("available") is not True:
        _note("instagram", "not_marked_available")
        return None
    ig_user_id = str(row.get("ig_user_id") or "")
    token = str(row.get("access_token") or "")
    scopes = _scopes(row.get("scopes"))
    if not _ID.fullmatch(ig_user_id):
        _note("instagram", "ig_user_id_invalid")
        return None
    if not _SECRET.fullmatch(token):
        _note("instagram", "access_token_invalid")
        return None
    if scopes is None or not IG_SCOPES.issubset(scopes):
        _note("instagram", "scopes_missing")
        return None
    paid_ok = row.get("sponsor_eligible") is True and bool(IG_PAID_SCOPES.intersection(scopes))
    return {
        "ig_user_id": ig_user_id,
        "access_token": token,
        "sponsor_eligible": paid_ok,
        "scopes": scopes,
        "available": True,
    }


def _facebook(row):
    if not isinstance(row, dict) or row.get("available") is not True:
        _note("facebook", "not_marked_available")
        return None
    page_id = str(row.get("page_id") or "")
    token = str(row.get("access_token") or "")
    scopes = _scopes(row.get("scopes"))
    tasks = _scopes(row.get("tasks"))
    if not _ID.fullmatch(page_id):
        _note("facebook", "page_id_invalid")
        return None
    if not _SECRET.fullmatch(token):
        _note("facebook", "access_token_invalid")
        return None
    if scopes is None or not FB_SCOPES.issubset(scopes):
        _note("facebook", "scopes_missing")
        return None
    if tasks is None or not FB_TASKS.issubset(tasks):
        _note("facebook", "tasks_missing")
        return None
    return {
        "page_id": page_id,
        "access_token": token,
        "scopes": scopes,
        "tasks": tasks,
        "available": True,
    }


def _tiktok(row):
    if not isinstance(row, dict) or row.get("available") is not True:
        _note("tiktok", "not_marked_available")
        return None
    key = str(row.get("api_key") or "")
    integration = str(row.get("integration_id") or "")
    if not _SECRET.fullmatch(key):
        _note("tiktok", "api_key_invalid")
        return None
    if not _NAME.fullmatch(integration):
        _note("tiktok", "integration_id_invalid")
        return None
    return {"api_key": key, "integration_id": integration, "available": True}


def read_regular_0600(path):
    """Read a regular mode-0600 file through one descriptor.

    O_NOFOLLOW plus fstat on that descriptor. A symlink, a swapped symlink,
    or any other mode fails closed and the bytes are not parsed.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None, "absent"
    except OSError:
        return None, "symlink_or_unreadable"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600:
            return None, "mode_not_0600"
        chunks = []
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
            chunks.append(buf)
        return b"".join(chunks), None
    finally:
        os.close(fd)


def load_publish_credentials():
    """Validated identities. Missing or invalid platforms are omitted."""
    _STATE["problems"] = []
    path = config_path()
    raw_bytes, err = read_regular_0600(str(path))
    if err == "absent":
        _note("config", "absent")
        return {}
    if err:
        _note("config", err)
        return {}
    try:
        raw = json.loads(raw_bytes.decode())
    except (UnicodeError, ValueError):
        _note("config", "unreadable")
        return {}
    if not isinstance(raw, dict):
        _note("config", "not_object")
        return {}
    out = {}
    ig = _instagram(raw.get("instagram"))
    if ig:
        out["instagram"] = ig
    fb = _facebook(raw.get("facebook"))
    if fb:
        out["facebook"] = fb
    tt = _tiktok(raw.get("tiktok"))
    if tt:
        out["tiktok"] = tt
    return out


def configured_platform_names():
    """Platform names that validated. Secret fields are not returned."""
    creds = load_publish_credentials()
    names = [name for name in ("instagram", "facebook", "tiktok") if name in creds]
    creds.clear()
    return names
