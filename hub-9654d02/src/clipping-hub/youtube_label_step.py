"""YouTube AI-label step after hub Approve (CLIP_YOUTUBE_LABEL_STEP, default OFF).

One-tap when flag on: Opus private upload → videos.update containsSyntheticMedia=true
→ re-read confirm → privacyStatus=public. OAuth once per channel (MAIN/PAID/GAMING, separate tokens).
Fail closed: any error leaves the video private and fires a push alert.
Never prints tokens. No real Google calls unless flag on and http not mocked.
"""
from __future__ import annotations

import json
import hashlib
import base64
import re
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FLAG = "CLIP_YOUTUBE_LABEL_STEP"
# Minimum scope listed on videos.update that is not partner/force-ssl.
# Docs accept youtube | youtube.force-ssl | youtubepartner. `youtube` is enough
# to update status (incl. containsSyntheticMedia + privacyStatus). force-ssl
# also allows permanent delete; partner is Content ID — both wider than needed.
SCOPE = "https://www.googleapis.com/auth/youtube"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
YT_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
OPUS_API_BASE = os.environ.get("CLIP_OPUS_API_BASE", "https://api.opus.pro")
OPUS_TOKEN_FILE = Path(os.environ.get(
    "CLIP_OPUS_API_TOKEN_FILE",
    str(Path.home() / ".config" / "clipping-hub" / "opus-api-token"),
))

# Outside the repo. Per-channel files: MAIN.json, PAID.json. chmod 600.
DEFAULT_TOKEN_DIR = Path.home() / ".config" / "clipping-hub" / "youtube-oauth"
TOKEN_DIR = Path(os.environ.get("CLIP_YT_OAUTH_DIR", str(DEFAULT_TOKEN_DIR)))

# Client id/secret live outside repo too (never committed).
CLIENT_ID_FILE = Path(os.environ.get(
    "CLIP_YT_CLIENT_ID_FILE",
    str(Path.home() / ".config" / "clipping-hub" / "youtube-oauth" / "client_id"),
))
CLIENT_SECRET_FILE = Path(os.environ.get(
    "CLIP_YT_CLIENT_SECRET_FILE",
    str(Path.home() / ".config" / "clipping-hub" / "youtube-oauth" / "client_secret"),
))

# Hub callback (localhost or Tailscale → same hub port). Override via env.
DEFAULT_REDIRECT = os.environ.get(
    "CLIP_YT_OAUTH_REDIRECT",
    "http://127.0.0.1:8505/oauth/youtube/callback",
)

# Pending OAuth state (channel + approval id) — ephemeral, outside repo.
STATE_DIR = Path(os.environ.get(
    "CLIP_YT_OAUTH_STATE_DIR",
    str(Path.home() / ".config" / "clipping-hub" / "youtube-oauth" / "state"),
))
STATE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
STATE_TTL_S = 600  # 10 minutes

# Google Cloud OAuth app in Testing mode: refresh tokens expire 7 days after grant.
GRANT_TTL_S = 7 * 24 * 3600
GRANT_WARN_BEFORE_S = 24 * 3600  # one push 24h before expiry
HUB_BASE = os.environ.get("CLIP_YT_HUB_BASE", "http://127.0.0.1:8505").rstrip("/")
TESTING_MODE_FLAG = "CLIP_YT_OAUTH_TESTING_MODE"  # default false: Production (no 7d countdown)

TIKTOK_LABEL_HELP = "https://www.tiktok.com/tiktokstudio"
IG_LABEL_HELP = "https://www.instagram.com/"


def enabled(env=None):
    e = env if env is not None else os.environ
    v = str(e.get(FLAG, "false")).strip().lower()
    return v in ("1", "true", "yes", "on")


def testing_mode(env=None):
    """True only when CLIP_YT_OAUTH_TESTING_MODE is on (7-day refresh expiry). Default false (Production)."""
    e = env if env is not None else os.environ
    v = str(e.get(TESTING_MODE_FLAG, "false")).strip().lower()
    return v in ("1", "true", "yes", "on")


GRANT_CHANNELS = ("MAIN", "PAID", "GAMING")


def hub_channel(channel) -> str:
    """Normalize a hub channel. Each of MAIN / PAID / GAMING has its OWN token file and grant; never shared.
    Unknown strings keep the legacy MAIN default (callers that route by target check GRANT_CHANNELS first)."""
    u = str(channel or "").strip().upper()
    return u if u in GRANT_CHANNELS else "MAIN"


def token_path(channel: str) -> Path:
    key = hub_channel(channel)
    return TOKEN_DIR / f"{key}.json"


def load_token(channel: str):
    p = token_path(channel)
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) and d.get("refresh_token") else None
    except (OSError, ValueError):
        return None


def save_token(channel: str, data: dict) -> bool:
    """Write refresh token file mode 600. Never logs contents.

    granted_at is metadata (not the secret): set on new grant, preserved on refresh.
    expiry_warn_for_granted_at records which grant already got the 24h warning push.
    """
    try:
        TOKEN_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        p = token_path(channel)
        tmp = p.with_suffix(".tmp")
        ch = hub_channel(channel)
        prior = None
        try:
            if p.is_file():
                prior = json.loads(p.read_text())
                if not isinstance(prior, dict):
                    prior = None
        except (OSError, ValueError):
            prior = None
        now_s = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        # New grant if caller sets granted_at, or no prior granted_at, or refresh_token changed.
        granted_at = data.get("granted_at")
        if not granted_at and prior and prior.get("granted_at"):
            if str(data.get("refresh_token") or "") == str(prior.get("refresh_token") or ""):
                granted_at = prior.get("granted_at")
        if not granted_at:
            granted_at = now_s
        warn_for = data.get("expiry_warn_for_granted_at")
        if warn_for is None and prior:
            # Preserve warn marker when refreshing same grant
            if str(granted_at) == str(prior.get("granted_at") or ""):
                warn_for = prior.get("expiry_warn_for_granted_at")
        payload = {
            "channel": ch,
            "refresh_token": str(data.get("refresh_token") or ""),
            "access_token": str(data.get("access_token") or ""),
            "expiry": data.get("expiry"),
            "scope": str(data.get("scope") or SCOPE),
            "saved_at": now_s,
            "granted_at": str(granted_at)[:64],
        }
        if warn_for:
            payload["expiry_warn_for_granted_at"] = str(warn_for)[:64]
        # Preserve / set revoked-alert dedupe marker (not a secret)
        revoked_for = data.get("revoked_alert_for_granted_at")
        if revoked_for is None and prior:
            revoked_for = prior.get("revoked_alert_for_granted_at")
        if revoked_for:
            payload["revoked_alert_for_granted_at"] = str(revoked_for)[:64]
        # Channel-bind metadata (not secrets). Whitelist only — never persist channel_mismatch.
        for key in ("bound_channel_id", "bound_channel_title", "granted_channel_ids"):
            val = data.get(key)
            if val is None and prior:
                val = prior.get(key)
            if val is None or val == "":
                continue
            if key == "granted_channel_ids":
                if isinstance(val, list):
                    payload[key] = [str(x)[:64] for x in val[:8]]
            else:
                payload[key] = str(val)[:120]
        if not payload["refresh_token"]:
            return False
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(p))
        os.chmod(p, 0o600)
        return True
    except OSError:
        return False


def _parse_ts(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if len(s) >= 5 and (s[-5] in "+-") and len(s) >= 3 and s[-3] != ":":
            s = s[:-2] + ":" + s[-2:]
        from datetime import datetime
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def delete_token(channel: str) -> bool:
    """Remove token file for channel. Never logs contents."""
    try:
        p = token_path(channel)
        if p.is_file():
            p.unlink()
        return True
    except OSError:
        return False


def revoke_token_best_effort(token: str, *, http_post=None) -> bool:
    """Best-effort Google token revoke. Never logs the token value."""
    raw = str(token or "").strip()
    if not raw:
        return False
    body = {"token": raw}
    try:
        if http_post:
            http_post("https://oauth2.googleapis.com/revoke", body)
        else:
            data = urllib.parse.urlencode(body).encode()
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/revoke", data=data, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        return True
    except Exception:
        return False


def discard_grant_tokens(tok: dict, channel: str, *, http_post=None) -> None:
    """On failed verify: best-effort revoke + ensure no token file remains. Never logs secrets."""
    if isinstance(tok, dict):
        for key in ("access_token", "refresh_token"):
            try:
                revoke_token_best_effort(tok.get(key) or "", http_post=http_post)
            except Exception:
                pass
    try:
        delete_token(channel)
    except Exception:
        pass


def regrant_hub_url(channel: str = "MAIN") -> str:
    """Hub route Luis opens on the Mac — SPA then POSTs /api/youtube-oauth/start (X-Hub-Token)."""
    ch = hub_channel(channel)
    return f"{HUB_BASE}/approvals?yt_regrant={ch}"


def grant_meta(channel: str, *, now=None, env=None):
    """Public grant metadata for hub chip / Approve gates. Never includes secrets.

    Production (testing_mode false): no 7-day countdown; expired/needs_regrant only when
    token missing (revocation detected separately via tick).
    Testing mode: 7-day TTL from granted_at + countdown chip fields.
    """
    ch = hub_channel(channel)
    tok = load_token(ch)
    tm = testing_mode(env)
    out = {
        "channel": ch,
        "present": bool(tok),
        "granted_at": None,
        "expires_at_epoch": None,
        "expires_in_s": None,
        "expires_in_days": None,
        "expired": not bool(tok),
        "needs_regrant": not bool(tok),
        "regrant_url": regrant_hub_url(ch),
        "testing_mode": tm,
        "show_countdown": False,
    }
    if not tok:
        return out
    out["granted_at"] = str(tok.get("granted_at") or tok.get("saved_at") or "")[:64] or None
    if not tm:
        # Production: no fixed expiry countdown
        out["expired"] = False
        out["needs_regrant"] = False
        out["show_countdown"] = False
        return out
    g_at = _parse_ts(tok.get("granted_at") or tok.get("saved_at"))
    if g_at is None:
        out["expired"] = False
        out["needs_regrant"] = False
        out["show_countdown"] = False
        return out
    now_e = float(now) if isinstance(now, (int, float)) else time.time()
    expires_at = g_at + GRANT_TTL_S
    remaining = expires_at - now_e
    out["expires_at_epoch"] = expires_at
    out["expires_in_s"] = int(remaining)
    out["expires_in_days"] = max(0, int((remaining + 86399) // 86400)) if remaining > 0 else 0
    out["expired"] = remaining <= 0
    out["needs_regrant"] = remaining <= 0
    out["show_countdown"] = True
    return out


def grants_summary(*, now=None, env=None):
    """Both channels' public grant meta for /api/state chip."""
    return {
        "testing_mode": testing_mode(env),
        "MAIN": grant_meta("MAIN", now=now, env=env),
        "PAID": grant_meta("PAID", now=now, env=env),
        "GAMING": grant_meta("GAMING", now=now, env=env),
    }


def mark_expiry_warn_sent(channel: str) -> bool:
    tok = load_token(channel)
    if not tok:
        return False
    tok = dict(tok)
    tok["expiry_warn_for_granted_at"] = str(tok.get("granted_at") or tok.get("saved_at") or "")
    return save_token(channel, tok)


def maybe_warn_grant_expiry(channel: str, *, push_fn=None, now=None, env=None) -> bool:
    """One push 24h before 7-day expiry (Testing mode only), deduped per granted_at."""
    if not testing_mode(env):
        return False
    meta = grant_meta(channel, now=now, env=env)
    if not meta.get("present") or meta.get("expired"):
        return False
    rem = meta.get("expires_in_s")
    if rem is None or rem > GRANT_WARN_BEFORE_S:
        return False
    tok = load_token(channel)
    if not tok:
        return False
    granted = str(tok.get("granted_at") or tok.get("saved_at") or "")
    if str(tok.get("expiry_warn_for_granted_at") or "") == granted and granted:
        return False  # already warned for this grant
    ch = meta["channel"]
    url = meta["regrant_url"]
    days = meta.get("expires_in_days")
    title = "YouTube grant expires soon"
    body = (
        f"{ch} refresh token expires in ~{days}d (Testing mode, 7-day grants). "
        f"Re-grant on the Mac: {url}"
    )
    try:
        if push_fn:
            ok = bool(push_fn(title, body, key=f"yt-grant-exp:{ch}:{granted[:32]}"))
        else:
            import push_alerts as _push
            ok = bool(_push.send_ntfy(
                title, body, key=f"yt-grant-exp:{ch}:{granted[:32]}",
                tags="hourglass,warning", priority="default",
            ))
    except Exception:
        ok = False
    if ok:
        mark_expiry_warn_sent(ch)
    return ok


def notify_regrant(channel: str, reason: str, *, push_fn=None, item=None) -> bool:
    ch = hub_channel(channel)
    url = regrant_hub_url(ch)
    name = ""
    if isinstance(item, dict):
        name = (item.get("title") or item.get("id") or "")[:40]
    title = "YouTube re-grant required"
    body = f"{ch}: {reason}. Open on Mac: {url}" + (f" ({name})" if name else "")
    try:
        if push_fn:
            return bool(push_fn(title, body, key=f"yt-regrant:{ch}"))
        import push_alerts as _push
        return bool(_push.send_ntfy(
            title, body, key=f"yt-regrant:{ch}", tags="warning", priority="high",
        ))
    except Exception:
        return False


def verify_client_secret_file(path=None):
    """Check client_secret.json is web type, redirect matches, mode 600, dir 700.
    Never returns or logs the secret value.
    """
    p = Path(path) if path else (TOKEN_DIR / "client_secret.json")
    out = {"ok": False, "type": None, "redirect_ok": False, "mode_ok": False, "dir_mode_ok": False, "error": None}
    try:
        mode = p.stat().st_mode & 0o777
        out["mode_ok"] = mode in (0o600, 0o700)
        dmode = p.parent.stat().st_mode & 0o777
        out["dir_mode_ok"] = dmode in (0o700, 0o600)
        raw = json.loads(p.read_text())
        if "web" in raw:
            out["type"] = "web"
            block = raw["web"] or {}
        elif "installed" in raw:
            out["type"] = "installed"
            block = raw["installed"] or {}
        else:
            out["error"] = "unknown_type"
            return out
        redirects = list(block.get("redirect_uris") or [])
        out["redirect_ok"] = DEFAULT_REDIRECT in redirects
        out["ok"] = (
            out["type"] == "web"
            and out["redirect_ok"]
            and out["mode_ok"]
            and out["dir_mode_ok"]
            and bool(block.get("client_id"))
            and bool(block.get("client_secret"))
        )
        if not out["ok"] and not out["error"]:
            out["error"] = "verify_failed"
        return out
    except Exception as e:
        out["error"] = type(e).__name__
        return out


def expected_yt_for_hub_channel(channel: str):
    """Return (name, yt_channel_id, handle) for MAIN/PAID from post_targets.json."""
    import schedule_hook as _sched
    key = hub_channel(channel)
    bucket = (_sched.load_targets() or {}).get("targets") or {}
    row = bucket.get(key) or {}
    return (
        str(row.get("name") or key)[:80],
        str(row.get("yt") or "")[:64],
        str(row.get("handle") or "")[:64],
    )


def fetch_granted_channels(access_token: str, *, http_json=None):
    """GET youtube channels.list mine=true. Returns list of {id,title} (no secrets)."""
    url = (
        "https://www.googleapis.com/youtube/v3/channels"
        "?part=snippet&mine=true&maxResults=50"
    )
    headers = {
        "Authorization": "Bearer " + str(access_token),
        "Accept": "application/json",
    }
    if http_json:
        data = http_json("GET", url, headers, None)
    else:
        req = urllib.request.Request(url, data=None, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode() or "{}")
    out = []
    for item in (data or {}).get("items") or []:
        cid = str((item or {}).get("id") or "").strip()
        title = str(((item or {}).get("snippet") or {}).get("title") or "").strip()
        if cid:
            out.append({"id": cid[:64], "title": title[:120]})
    return out


def verify_grant_matches_channel(channel: str, access_token: str, *, http_json=None):
    """Post-grant check: mine=true must include expected yt id for hub channel.

    Returns dict: ok, expected_id, expected_name, granted=[{id,title}], mismatch, error.
    """
    name, expect_id, handle = expected_yt_for_hub_channel(channel)
    out = {
        "ok": False,
        "channel": hub_channel(channel),
        "expected_id": expect_id,
        "expected_name": name,
        "expected_handle": handle,
        "granted": [],
        "mismatch": False,
        "error": None,
    }
    if not expect_id:
        out["error"] = "missing_expected_yt"
        return out
    try:
        granted = fetch_granted_channels(access_token, http_json=http_json)
    except Exception as e:
        out["error"] = "channels_list_failed:" + type(e).__name__
        return out
    out["granted"] = granted
    ids = {g["id"] for g in granted}
    if expect_id in ids:
        out["ok"] = True
        return out
    out["mismatch"] = True
    out["error"] = "channel_mismatch"
    return out


def assert_video_owned_by_grant(video_status_or_snippet, channel: str, *, bound_channel_id=None):
    """Fail-closed: video channelId must match BOTH bound grant id and post_targets id.

    Missing bind (no bound_channel_id) refuses — operator must re-grant.
    """
    name, expect_id, _ = expected_yt_for_hub_channel(channel)
    expect_id = str(expect_id or "").strip()
    bound = str(bound_channel_id or "").strip()
    if not bound:
        raise RuntimeError("youtube_missing_bound_channel_id")
    if not expect_id:
        raise RuntimeError("opus_missing_expected_yt_channel")
    if bound != expect_id:
        raise RuntimeError(
            "youtube_bound_targets_mismatch:bound_%s_targets_%s(%s)" % (bound, expect_id, name)
        )
    got = ""
    if isinstance(video_status_or_snippet, dict):
        got = str(
            video_status_or_snippet.get("channelId")
            or (video_status_or_snippet.get("snippet") or {}).get("channelId")
            or ""
        ).strip()
    if not got:
        raise RuntimeError("youtube_video_missing_channel_id")
    if got != expect_id or got != bound:
        raise RuntimeError(
            "youtube_channel_mismatch:video_on_%s_grant_expects_%s(%s)" % (got, expect_id, name)
        )
    return True


def read_client_id():
    try:
        return CLIENT_ID_FILE.read_text().strip() or None
    except OSError:
        return None


def read_client_secret():
    """Plain client_secret file first; else the sibling Google client_secret.json (web.client_secret), but only when
    its web.client_id equals read_client_id(). Never logged."""
    try:
        s = CLIENT_SECRET_FILE.read_text().strip()
        if s:
            return s
    except OSError:
        pass
    try:
        web = json.loads(CLIENT_SECRET_FILE.with_name("client_secret.json").read_text()).get("web") or {}
    except (OSError, ValueError, AttributeError):
        return None
    cid = read_client_id()
    if not isinstance(web, dict) or not cid or str(web.get("client_id") or "").strip() != cid:
        return None
    return str(web.get("client_secret") or "").strip() or None


def token_bind_ok(channel: str, tok=None) -> bool:
    """True when stored token has bound_channel_id matching post_targets yt for channel."""
    _, expect_id, _ = expected_yt_for_hub_channel(channel)
    expect_id = str(expect_id or "").strip()
    if not expect_id:
        return False
    data = tok if isinstance(tok, dict) else load_token(channel)
    if not data:
        return False
    bound = str(data.get("bound_channel_id") or "").strip()
    return bool(bound) and bound == expect_id


def needs_oauth(channel: str, *, now=None) -> bool:
    """True when no token, Testing-mode grant expired, or bound_channel_id != expected."""
    meta = grant_meta(channel, now=now)
    if (not meta.get("present")) or bool(meta.get("expired")):
        return True
    return not token_bind_ok(channel)


def _pkce_pair():
    """S256 PKCE verifier + challenge. Verifier stays in the state file only."""
    verifier = secrets.token_urlsafe(64)
    if len(verifier) < 43:
        verifier = (verifier + secrets.token_urlsafe(32))[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def validate_state_token(state: str) -> bool:
    return bool(isinstance(state, str) and STATE_RE.fullmatch(state))


def _state_path(state: str) -> Path:
    """Resolve state file path under STATE_DIR only. Raises ValueError on bad/traversal."""
    if not validate_state_token(state):
        raise ValueError("bad_state")
    base = STATE_DIR.resolve()
    p = (base / f"{state}.json").resolve()
    p.relative_to(base)  # raises ValueError if outside
    return p


def clean_stale_oauth_state(*, now=None):
    """Remove state files older than STATE_TTL_S. Never touches paths outside STATE_DIR."""
    try:
        base = STATE_DIR.resolve()
        if not base.is_dir():
            return 0
        now_s = time.time() if now is None else float(now)
        removed = 0
        for child in base.iterdir():
            if not child.is_file() or not child.name.endswith(".json"):
                continue
            token = child.name[:-5]
            if not validate_state_token(token):
                # refuse to delete unexpected names (could be traversal residue)
                continue
            try:
                child.resolve().relative_to(base)
            except ValueError:
                continue
            try:
                d = json.loads(child.read_text())
                at = _parse_at(d.get("at"))
                if at is None or (now_s - at) > STATE_TTL_S:
                    child.unlink()
                    removed += 1
            except (OSError, ValueError):
                try:
                    child.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed
    except OSError:
        return 0


def _parse_at(raw):
    if not isinstance(raw, str) or not raw:
        return None
    # Accept epoch float string or ISO-ish with optional offset
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        # 2026-11-06T12:00:00-0500 or with colon in offset
        s = raw.strip()
        if re.match(r".*[+-]\d{4}$", s):
            s = s[:-2] + ":" + s[-2:]
        from datetime import datetime
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def build_auth_url(*, channel: str, approval_id: str, redirect_uri=None, client_id=None, state=None):
    """Build Google auth URL with PKCE S256. State file marked authorized_approve=True.
    Only called after an authorized Approve when the flag is on.
    """
    cid = client_id or read_client_id()
    if not cid:
        return None, "missing_client_id"
    clean_stale_oauth_state()
    state_tok = state or secrets.token_urlsafe(24)
    if not validate_state_token(state_tok):
        state_tok = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    ok = _save_oauth_state(
        state_tok,
        channel=channel,
        approval_id=approval_id,
        code_verifier=verifier,
        authorized_approve=True,
    )
    if not ok:
        return None, "state_save_failed"
    q = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": redirect_uri or DEFAULT_REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state_tok,
    })
    return f"{AUTH_URI}?{q}", None


def _save_oauth_state(state: str, *, channel: str, approval_id: str,
                      code_verifier: str = "", authorized_approve: bool = False):
    try:
        p = _state_path(state)
        STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({
                "channel": hub_channel(channel),
                "approval_id": str(approval_id)[:64],
                "at": str(time.time()),
                "code_verifier": str(code_verifier or "")[:128],
                "authorized_approve": bool(authorized_approve),
            }, f)
        return True
    except (OSError, ValueError):
        return False


def load_oauth_state(state: str, *, consume: bool = True, now=None):
    """Load a grant state file. Rejects bad/traversal/expired/unauthorized.
    Only deletes the validated path under STATE_DIR when consume=True.
    """
    try:
        clean_stale_oauth_state(now=now)
        p = _state_path(state)
        d = json.loads(p.read_text())
        if not isinstance(d, dict):
            return None
        if not d.get("authorized_approve"):
            return None
        at = _parse_at(d.get("at"))
        now_s = time.time() if now is None else float(now)
        if at is None or (now_s - at) > STATE_TTL_S:
            if consume:
                try:
                    p.unlink()
                except OSError:
                    pass
            return None
        if consume:
            try:
                # Delete only this validated file under STATE_DIR
                p.resolve().relative_to(STATE_DIR.resolve())
                p.unlink()
            except (OSError, ValueError):
                pass
        return d
    except (OSError, ValueError):
        return None


def grant_in_progress(state: str, *, now=None) -> bool:
    """True when flag is ON and an unexpired authorized state file exists for state."""
    if not enabled():
        return False
    if not validate_state_token(state or ""):
        return False
    try:
        p = _state_path(state)
        if not p.is_file():
            return False
        d = json.loads(p.read_text())
        if not isinstance(d, dict) or not d.get("authorized_approve"):
            return False
        at = _parse_at(d.get("at"))
        now_s = time.time() if now is None else float(now)
        return at is not None and (now_s - at) <= STATE_TTL_S
    except (OSError, ValueError):
        return False


def exchange_code(code: str, *, redirect_uri=None, http_post=None, code_verifier=None):
    """Swap auth code for tokens (PKCE). http_post(url, data_dict) -> dict. Never prints secrets."""
    cid, secret = read_client_id(), read_client_secret()
    if not cid or not secret:
        return None, "missing_client"
    body = {
        "code": code,
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": redirect_uri or DEFAULT_REDIRECT,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        body["code_verifier"] = str(code_verifier)[:128]
    try:
        if http_post:
            data = http_post(TOKEN_URI, body)
        else:
            raw = urllib.parse.urlencode(body).encode()
            req = urllib.request.Request(TOKEN_URI, data=raw, method="POST")
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
        if not isinstance(data, dict) or not data.get("refresh_token"):
            return None, "no_refresh_token"
        return data, None
    except Exception as e:
        return None, f"exchange_failed:{type(e).__name__}"


def refresh_access(channel: str, *, http_post=None, now=None, token=None, persist=True):
    """Exchange the refresh token for an access token.

    persist=True (default) writes the token file via save_token, which is what
    the label step has always done. Callers that are not allowed to write
    tokens, including the private proof, must pass persist=False. The new
    access token then exists only in memory.
    """
    # Expired Testing-mode grant → fail closed before hitting Google.
    # An in-memory token is not re-read from disk.
    if token is None:
        meta = grant_meta(channel, now=now)
        if meta.get("expired"):
            return None, "grant_expired"
        tok = load_token(channel)
    else:
        tok = token if isinstance(token, dict) else None
    if not tok:
        return None, "no_token"
    if not token_bind_ok(channel, tok):
        return None, "channel_bind_mismatch"
    cid, secret = read_client_id(), read_client_secret()
    if not cid or not secret:
        return None, "missing_client"
    body = {
        "client_id": cid,
        "client_secret": secret,
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    }
    try:
        if http_post:
            data = http_post(TOKEN_URI, body)
        else:
            raw = urllib.parse.urlencode(body).encode()
            req = urllib.request.Request(TOKEN_URI, data=raw, method="POST")
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
        if isinstance(data, dict) and data.get("error") == "invalid_grant":
            return None, "invalid_grant"
        access = (data or {}).get("access_token")
        if not access:
            err = (data or {}).get("error") if isinstance(data, dict) else None
            if err == "invalid_grant":
                return None, "invalid_grant"
            return None, "no_access"
        tok["access_token"] = access
        if persist:
            save_token(channel, tok)  # preserves granted_at; private proof does not authorize this
        return access, None
    except Exception as e:
        msg = str(e)
        if "invalid_grant" in msg:
            return None, "invalid_grant"
        return None, f"refresh_failed:{type(e).__name__}"


def _yt_request(method, params, body, access_token, *, http_json=None):
    """http_json(method, url, headers, body) -> dict. Raises on hard failure."""
    q = urllib.parse.urlencode(params)
    url = f"{YT_VIDEOS}?{q}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if http_json:
        return http_json(method, url, headers, body)
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")


def get_video_status(video_id: str, access_token: str, *, http_json=None):
    data = _yt_request(
        "GET",
        {"part": "status,snippet", "id": video_id},
        None,
        access_token,
        http_json=http_json,
    )
    items = (data or {}).get("items") or []
    if not items:
        return None
    row = items[0] or {}
    status = dict(row.get("status") or {})
    # Attach channelId for ownership checks (fail-closed label step).
    snip = row.get("snippet") or {}
    cid = snip.get("channelId") or status.get("channelId") or row.get("channelId")
    if cid:
        status["channelId"] = str(cid)[:64]
    return status


def update_video_status(video_id: str, access_token: str, patch: dict, *, http_json=None):
    """GET current status, merge patch, PUT status fields only (never channelId in status body)."""
    current = get_video_status(video_id, access_token, http_json=http_json) or {}
    if not isinstance(current, dict):
        current = {}
    merged = dict(current)
    for k, v in (patch or {}).items():
        merged[k] = v
    # channelId is snippet ownership metadata from GET — not a videos.update status field.
    merged.pop("channelId", None)
    return _yt_request(
        "PUT",
        {"part": "status"},
        {"id": video_id, "status": merged},
        access_token,
        http_json=http_json,
    )


def set_contains_synthetic(video_id: str, access_token: str, *, http_json=None):
    return update_video_status(
        video_id, access_token,
        {"containsSyntheticMedia": True, "privacyStatus": "private"},
        http_json=http_json,
    )


def set_privacy_public(video_id: str, access_token: str, *, http_json=None):
    return update_video_status(
        video_id, access_token,
        {"privacyStatus": "public", "containsSyntheticMedia": True},
        http_json=http_json,
    )


def set_paid_placement(video_id: str, access_token: str, *, http_json=None):
    """YouTube Data API paidProductPlacementDetails.hasPaidProductPlacement.

    A caption hashtag is not this toggle. part is paidProductPlacementDetails only.
    """
    return _yt_request(
        "PUT",
        {"part": "paidProductPlacementDetails"},
        {"id": video_id, "paidProductPlacementDetails": {"hasPaidProductPlacement": True}},
        access_token,
        http_json=http_json,
    )


def paid_placement_confirmed(video_id: str, access_token: str, *, http_json=None) -> bool:
    data = _yt_request(
        "GET",
        {"part": "paidProductPlacementDetails", "id": video_id},
        None,
        access_token,
        http_json=http_json,
    )
    items = (data or {}).get("items") or []
    if not items:
        return False
    details = (items[0] or {}).get("paidProductPlacementDetails") or {}
    return details.get("hasPaidProductPlacement") is True


def set_privacy_private(video_id: str, access_token: str, *, http_json=None):
    return update_video_status(
        video_id, access_token,
        {"privacyStatus": "private"},
        http_json=http_json,
    )


def notify_may_be_public(item, err, *, push_fn=None):
    """Loud alert: re-private failed after a public flip; video may still be public."""
    try:
        title = "URGENT: YouTube video may be PUBLIC"
        name = (item.get("title") or item.get("id") or "clip")[:60]
        body = f"{name}: {err}. Re-private FAILED — check YouTube Studio now."
        if push_fn:
            return push_fn(title, body, key=f"ytlabel-maypublic:{item.get('id')}")
        import push_alerts as _push
        return _push.send_ntfy(
            title, body, key=f"ytlabel-maypublic:{item.get('id')}",
            tags="rotating_light,warning", priority="urgent",
        )
    except Exception:
        return False


def read_opus_token():
    try:
        return OPUS_TOKEN_FILE.read_text().strip() or None
    except OSError:
        return None


def bare_clip_id(raw):
    """Opus social posting wants bare clipId, not projectId.clipId."""
    s = str(raw or "").strip()
    if "." in s:
        return s.split(".", 1)[-1][:64]
    return s[:64]


YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_URL_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
})
CREATE_IDEMPOTENCY_PLATFORM = "youtube:create"


def normalize_youtube_video_id(raw):
    """Accept only YouTube video ids matching ^[A-Za-z0-9_-]{11}$."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return s if YT_ID_RE.fullmatch(s) else None


def youtube_id_from_url(url: str):
    """Parse a YouTube watch/shorts/youtu.be URL. https only; exact host allowlist; no userinfo."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        u = urllib.parse.urlparse(url.strip())
        if (u.scheme or "").lower() != "https":
            return None
        netloc = u.netloc or ""
        # Reject userinfo (user:pass@host or anything with @)
        if "@" in netloc or u.username is not None or u.password is not None:
            return None
        host = (u.hostname or "").lower()
        if host not in YT_URL_HOSTS:
            return None
        if host == "youtu.be":
            vid = (u.path or "/").lstrip("/").split("/")[0].split("?")[0]
            return normalize_youtube_video_id(vid)
        qs = urllib.parse.parse_qs(u.query or "")
        if qs.get("v"):
            return normalize_youtube_video_id(str(qs["v"][0]))
        parts = [p for p in (u.path or "").split("/") if p]
        if parts and parts[0] in ("shorts", "embed", "live", "v") and len(parts) > 1:
            return normalize_youtube_video_id(parts[1].split("?")[0])
    except Exception:
        return None
    return None


def _iter_post_rows(payload):
    """Yield dict rows from create-post / list-posts shaped payloads."""
    if not isinstance(payload, dict):
        return
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    yield payload
    if data:
        yield data
    for key in ("posts", "items"):
        for row in (payload.get(key) or data.get(key) or []):
            if isinstance(row, dict):
                yield row


def extract_youtube_video_id_from_row(row):
    """Pull a validated video id from one Opus post row only (explicit field or its URL)."""
    if not isinstance(row, dict):
        return None
    for key in ("videoId", "youtubeVideoId", "youtube_video_id", "video_id"):
        vid = normalize_youtube_video_id(row.get(key) if isinstance(row.get(key), str) else None)
        if vid:
            return vid
    for ukey in ("post_url", "postUrl", "url", "permalink"):
        url = row.get(ukey)
        if isinstance(url, str):
            vid = youtube_id_from_url(url)
            if vid:
                return vid
    return None


def extract_youtube_video_id_for_post(payload, post_id, *, post_account_id=None):
    """Match the Opus row by postId (and account when present). Never use the first parseable URL.

    If a matching row exists but has no valid YouTube id → None (caller fails closed).
    If no matching row → None.
    """
    if not post_id or not isinstance(payload, dict):
        return None
    want = str(post_id).strip()
    want_acct = str(post_account_id or "").strip() or None
    matched = None
    for row in _iter_post_rows(payload):
        rid = str(row.get("postId") or row.get("post_id") or "").strip()
        if rid != want:
            continue
        if want_acct:
            aid = str(
                row.get("postAccountId")
                or row.get("post_account_id")
                or row.get("accountId")
                or ""
            ).strip()
            # If the row carries an account id, it must match. Rows without account still match postId.
            if aid and aid != want_acct:
                continue
        matched = row
        break
    if matched is None:
        return None
    return extract_youtube_video_id_from_row(matched)


def extract_youtube_video_id(payload):
    """Legacy helper: explicit videoId on the create response only (validated). No URL scan."""
    if not isinstance(payload, dict):
        return None
    for obj in (payload, payload.get("data") if isinstance(payload.get("data"), dict) else None):
        if not isinstance(obj, dict):
            continue
        for key in ("videoId", "youtubeVideoId", "youtube_video_id", "video_id"):
            vid = normalize_youtube_video_id(obj.get(key) if isinstance(obj.get(key), str) else None)
            if vid:
                return vid
    return None


def opus_http_create_post(body: dict, *, token=None, http_json=None):
    """POST https://api.opus.pro/api/post-tasks. http_json(method, url, headers, body)->dict."""
    tok = token or read_opus_token()
    if not tok:
        raise RuntimeError("opus_token_missing")
    url = OPUS_API_BASE.rstrip("/") + "/api/post-tasks"
    headers = {
        "Authorization": "Bearer " + tok,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if http_json:
        return http_json("POST", url, headers, body)
    raw = json.dumps(body).encode()
    req = urllib.request.Request(url, data=raw, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode() or "{}")


def opus_http_list_posts_for_project(project_id: str, *, token=None, http_json=None):
    """Best-effort list of posts for a project (MCP list_scheduled_posts analog).
    REST path is not in the public Publish docs; injectable for tests. Default tries
    GET /api/post-tasks?projectId=… and ignores hard failures (returns {}).
    """
    tok = token or read_opus_token()
    if not tok:
        return {}
    q = urllib.parse.urlencode({"projectId": project_id})
    url = OPUS_API_BASE.rstrip("/") + "/api/post-tasks?" + q
    headers = {"Authorization": "Bearer " + tok, "Accept": "application/json"}
    try:
        if http_json:
            return http_json("GET", url, headers, None) or {}
        req = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")
    except Exception:
        return {}



def notify_stuck_upload(item, err, *, push_fn=None):
    """Clear alert when in_flight is stale and Opus has no matching post."""
    try:
        title = "Stuck upload — check Opus"
        name = (item.get("title") or item.get("id") or "clip")[:60]
        body = f"{name}: {err}. In-flight timed out; no matching Opus post found. Check Opus Studio, then unstick or retry."
        if push_fn:
            return bool(push_fn(title, body, key=f"opus-stuck:{item.get('id')}"))
        import push_alerts as _push
        return bool(_push.send_ntfy(
            title, body, key=f"opus-stuck:{item.get('id')}", tags="warning", priority="high",
        ))
    except Exception:
        return False



def mark_revoked_alert_sent(channel: str) -> bool:
    tok = load_token(channel)
    if not tok:
        return False
    tok = dict(tok)
    tok["revoked_alert_for_granted_at"] = str(tok.get("granted_at") or tok.get("saved_at") or "")
    return save_token(channel, tok)


def check_grant_alive(channel: str, *, http_post=None, http_json=None, now=None):
    """Cheap token check: refresh_access. Returns (ok, error).
    invalid_grant / missing → not ok. Does not raise.
    """
    ch = hub_channel(channel)
    if needs_oauth(ch, now=now):
        # In testing mode this includes TTL expiry; in production only missing token.
        meta = grant_meta(ch, now=now)
        if not meta.get("present"):
            return False, "no_token"
        if meta.get("expired"):
            return False, "grant_expired"
    access, err = refresh_access(ch, http_post=http_post, now=now)
    if err in ("invalid_grant", "grant_expired"):
        return False, err
    if not access:
        # Treat 401-ish / no_access after refresh as revoked
        if err in ("no_access", "no_token"):
            return False, err or "no_access"
        return False, err or "refresh_failed"
    return True, None


def maybe_alert_revoked(channel: str, reason: str, *, push_fn=None) -> bool:
    """ONE deduped 'grant revoked or expired' alert with re-grant link."""
    ch = hub_channel(channel)
    tok = load_token(ch)
    granted = str((tok or {}).get("granted_at") or (tok or {}).get("saved_at") or "") or "none"
    if tok and str(tok.get("revoked_alert_for_granted_at") or "") == granted:
        return False
    title = "YouTube grant revoked or expired"
    body = f"{ch}: {reason}. Re-grant on Mac: {regrant_hub_url(ch)}"
    try:
        if push_fn:
            ok = bool(push_fn(title, body, key=f"yt-revoked:{ch}:{granted[:32]}"))
        else:
            import push_alerts as _push
            ok = bool(_push.send_ntfy(
                title, body, key=f"yt-revoked:{ch}:{granted[:32]}",
                tags="warning", priority="high",
            ))
    except Exception:
        ok = False
    if ok:
        mark_revoked_alert_sent(ch)
    return ok


def reconcile_opus_post(
    *,
    project_id: str,
    clip_id: str,
    post_account_id: str,
    token=None,
    http_json=None,
    push_fn=None,
    item=None,
):
    """Find an existing Opus post-task. Requires exact clipId AND projectId AND account.

    Rows missing any of the three fields are skipped. If 0 or >1 rows match → fail closed
    (ok False + alert). Never picks the first parseable / other-clip row.
    Returns {ok, post_id, video_id, error, count}.
    """
    want_clip = bare_clip_id(clip_id)
    want_proj = str(project_id or "").strip()
    want_acct = str(post_account_id or "").strip()
    if not want_clip or not want_proj or not want_acct:
        return {"ok": False, "error": "reconcile_missing_want", "count": 0, "post_id": None, "video_id": None}

    listed = opus_http_list_posts_for_project(want_proj, token=token, http_json=http_json)
    if not isinstance(listed, dict):
        listed = {}
    matches = []
    for row in _iter_post_rows(listed):
        rid = str(row.get("postId") or row.get("post_id") or "").strip()
        if not rid:
            continue
        row_clip = bare_clip_id(row.get("clipId") or row.get("clip_id") or "")
        row_proj = str(row.get("projectId") or row.get("project_id") or "").strip()
        row_acct = str(
            row.get("postAccountId") or row.get("post_account_id") or row.get("accountId") or ""
        ).strip()
        # Skip incomplete rows — do not treat missing as wildcard
        if not row_clip or not row_proj or not row_acct:
            continue
        if row_clip != want_clip or row_proj != want_proj or row_acct != want_acct:
            continue
        matches.append(row)

    if len(matches) != 1:
        err = "reconcile_ambiguous" if len(matches) > 1 else "reconcile_none"
        # Caller alerts once (deduped) and keeps timeout_pending — do not mark failed here.
        return {"ok": False, "error": err, "count": len(matches), "post_id": None, "video_id": None}

    best = matches[0]
    post_id = str(best.get("postId") or best.get("post_id") or "").strip()
    video_id = extract_youtube_video_id_from_row(best)
    return {"ok": True, "post_id": post_id, "video_id": video_id, "error": None, "count": 1, "row": best}


def notify_create_error(item, err, *, push_fn=None):
    """One deduped alert for terminal create_error (non-timeout / missing postId)."""
    try:
        title = "YouTube create failed — needs unstick"
        name = (item.get("title") or item.get("id") or "clip")[:60] if isinstance(item, dict) else "clip"
        body = (
            f"{name}: {err}. Ledger is create_error (no auto-retry). "
            f"Check Opus, then authorized unstick before Approve again."
        )
        key = f"opus-create-err:{(item.get('id') if isinstance(item, dict) else 'x')}"
        if push_fn:
            return bool(push_fn(title, body, key=key))
        import push_alerts as _push
        return bool(_push.send_ntfy(title, body, key=key, tags="warning", priority="high"))
    except Exception:
        return False


def notify_timeout_may_stuck(item, *, push_fn=None):

    """Immediate alert on create timeout — upload may be stuck; check Opus."""
    try:
        title = "Upload may be stuck — check Opus"
        name = (item.get("title") or item.get("id") or "clip")[:60] if isinstance(item, dict) else "clip"
        body = (
            f"{name}: Opus create-post timed out. Ledger marked timeout_pending. "
            f"Approve again (reconcile only) or wait for tick — never double-posts."
        )
        key = f"opus-timeout:{(item.get('id') if isinstance(item, dict) else 'x')}"
        if push_fn:
            return bool(push_fn(title, body, key=key))
        import push_alerts as _push
        return bool(_push.send_ntfy(title, body, key=key, tags="warning,hourglass", priority="high"))
    except Exception:
        return False


def opus_upload_private(
    item,
    *,
    opus_fn=None,
    targets=None,
    http_json=None,
    token=None,
    ledger_path=None,
    push_fn=None,
):
    """Opus create-post with privacy=private for the routed YouTube account.

    Account ids come ONLY from the routed post_targets.json row (never item.opus_*).
    Idempotent: ledger key job_id::youtube:create stored before the call; postId recorded
    on success. Timeout / retry looks up by postId instead of creating a second post.
    Video id is resolved only from the row matching that postId (fail closed otherwise).
    Does not claim privacy — caller must GET YouTube status and verify.
    """
    if opus_fn:
        return opus_fn(item)

    import schedule_hook as _sched
    import post_idempotency as _idem

    route = _sched.route_for_item(item, targets=targets) or {}
    if route.get("blocked"):
        raise RuntimeError("opus_blocked_route:" + str(route.get("block_reason") or "blocked"))
    if (route.get("target") or "MAIN") not in GRANT_CHANNELS:
        # Hub YouTube grants exist for MAIN/PAID only: never upload for a label step we cannot finish.
        raise RuntimeError("opus_no_hub_grant_for_target:" + str(route.get("target")))
    if not isinstance(item, dict):
        raise RuntimeError("opus_bad_item")

    project_id = str(item.get("projectId") or item.get("project_id") or item.get("opus_project_id") or "")[:64]
    clip_raw = item.get("clipId") or item.get("clip_id") or item.get("opus_clip_id") or ""
    clip_id = bare_clip_id(clip_raw)
    if not project_id or not clip_id:
        raise RuntimeError("opus_missing_project_or_clip_id")

    cfg = targets if isinstance(targets, dict) and "targets" in targets else _sched.load_targets()
    tkey = route.get("target") or "MAIN"
    trow = (cfg.get("targets") or {}).get(tkey) or {}
    # ONLY from routed targets row — ignore item.opus_* / item.subAccountId
    post_account_id = str(trow.get("opus_post_account_id") or route.get("opus_post_account_id") or "")[:64]
    sub_account_id = str(
        trow.get("opus_sub_account_id") or trow.get("sub_account_id") or ""
    )[:64]
    if not post_account_id:
        raise RuntimeError("opus_missing_post_account_id")

    title = str(item.get("title") or "")[:200]
    description = str(item.get("caption") or item.get("description") or "")[:500]
    if not title:
        raise RuntimeError("opus_missing_title")

    job_id = str(item.get("id") or "").strip()
    if not job_id:
        raise RuntimeError("opus_missing_job_id")

    def _resolve_video_for_post(post_id):
        """List posts and take video id only from the matching postId row."""
        listed = opus_http_list_posts_for_project(project_id, token=token, http_json=http_json)
        vid = extract_youtube_video_id_for_post(
            listed if isinstance(listed, dict) else {},
            post_id,
            post_account_id=post_account_id,
        )
        return vid

    def _return_for(post_id, video_id):
        return {
            "video_id": video_id,
            "post_id": str(post_id or "")[:128],
            "project_id": project_id,
            "clip_id": clip_id,
            "post_account_id": post_account_id,
        }

    def _reconcile_only():
        found = reconcile_opus_post(
            project_id=project_id, clip_id=clip_id, post_account_id=post_account_id,
            token=token, http_json=http_json, push_fn=push_fn, item=item,
        )
        if found and found.get("ok") and found.get("post_id"):
            _idem.mark_done(
                job_id, CREATE_IDEMPOTENCY_PLATFORM,
                opus_post_id=found["post_id"], path=ledger_path,
            )
            video_id = found.get("video_id") or _resolve_video_for_post(found["post_id"])
            if not video_id:
                raise RuntimeError("opus_no_video_id_for_existing_post")
            return _return_for(found["post_id"], video_id)
        # none / ambiguous: keep timeout_pending (never mark failed → never re-POST via begin)
        err = (found or {}).get("error") or "reconcile_failed"
        prior = _idem.lookup(job_id, CREATE_IDEMPOTENCY_PLATFORM, path=ledger_path) or {}
        already = bool(prior.get("reconcile_alerted"))
        if not already:
            notify_stuck_upload(item, f"{err}:waiting", push_fn=push_fn)
        # Stay timeout_pending forever until unique match or explicit unstick — never mark failed.
        _idem.mark_timeout_pending(
            job_id, CREATE_IDEMPOTENCY_PLATFORM,
            error=err, path=ledger_path, reconcile_alerted=True,
        )
        raise RuntimeError("opus_reconcile_waiting:" + str(err))

    acquired, existing = _idem.begin(job_id, CREATE_IDEMPOTENCY_PLATFORM, path=ledger_path)
    if not acquired:
        prior_post = (existing or {}).get("opus_post_id")
        st_prior = (existing or {}).get("status")
        if prior_post:
            video_id = _resolve_video_for_post(prior_post)
            if not video_id:
                raise RuntimeError("opus_no_video_id_for_existing_post")
            return _return_for(prior_post, video_id)
        # timeout_pending or stale in_flight → reconcile only, never re-POST
        if st_prior == "timeout_pending" or (existing or {}).get("timeout_pending"):
            return _reconcile_only()
        if st_prior == "in_flight":
            stale = bool((existing or {}).get("stale_in_flight")) or _idem.is_in_flight_stale(existing or {})
            if not stale:
                raise RuntimeError("opus_create_in_flight")
            return _reconcile_only()
        raise RuntimeError("opus_create_blocked_idempotent")

    body = {
        "projectId": project_id,
        "clipId": clip_id,
        "postAccountId": post_account_id,
        "postDetail": {
            "title": title,
            "mediaType": "short",
            "custom": {
                "description": description,
                "privacy": "private",
            },
        },
        # Hub-side idempotency marker (also in ledger). Harmless if Opus ignores unknown fields.
        "clientRequestId": _idem.make_key(job_id, CREATE_IDEMPOTENCY_PLATFORM),
    }
    if sub_account_id:
        body["subAccountId"] = sub_account_id

    try:
        resp = opus_http_create_post(body, token=token, http_json=http_json)
    except Exception as e:
        err_name = type(e).__name__
        msg = str(e)[:160]
        is_timeout = (
            "timeout" in msg.lower()
            or "Timeout" in err_name
            or err_name in ("URLError", "timeout", "TimeoutError")
        )
        # Reconcile before failing — never blind retry POST. Exact match required.
        found = reconcile_opus_post(
            project_id=project_id, clip_id=clip_id, post_account_id=post_account_id,
            token=token, http_json=http_json, push_fn=push_fn, item=item,
        )
        if found and found.get("ok") and found.get("post_id"):
            _idem.mark_done(
                job_id, CREATE_IDEMPOTENCY_PLATFORM,
                opus_post_id=found["post_id"], path=ledger_path,
            )
            video_id = found.get("video_id") or _resolve_video_for_post(found["post_id"])
            if video_id:
                return _return_for(found["post_id"], video_id)
            raise RuntimeError("opus_no_video_id_for_existing_post") from e
        if is_timeout:
            _idem.mark_timeout_pending(
                job_id, CREATE_IDEMPOTENCY_PLATFORM,
                error="create_timeout", path=ledger_path,
            )
            notify_timeout_may_stuck(item, push_fn=push_fn)
            raise RuntimeError("opus_create_timeout_pending") from e
        # Non-timeout create error: terminal create_error (begin refuses until unstick).
        prior = _idem.lookup(job_id, CREATE_IDEMPOTENCY_PLATFORM, path=ledger_path) or {}
        already = bool(prior.get("create_error_alerted"))
        if not already:
            notify_create_error(item, msg, push_fn=push_fn)
        _idem.mark_create_error(
            job_id, CREATE_IDEMPOTENCY_PLATFORM,
            error=msg, path=ledger_path, alerted=True,
        )
        raise RuntimeError("opus_create_error:" + msg) from e

    post_id = None
    if isinstance(resp, dict):
        data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        post_id = data.get("postId") or resp.get("postId")
    post_id = str(post_id or "").strip() or None
    if not post_id:
        prior = _idem.lookup(job_id, CREATE_IDEMPOTENCY_PLATFORM, path=ledger_path) or {}
        already = bool(prior.get("create_error_alerted"))
        if not already:
            notify_create_error(item, "opus_no_post_id", push_fn=push_fn)
        _idem.mark_create_error(
            job_id, CREATE_IDEMPOTENCY_PLATFORM,
            error="opus_no_post_id", path=ledger_path, alerted=True,
        )
        raise RuntimeError("opus_no_post_id")

    # Record postId before resolving video id (retry can resume from postId).
    _idem.mark_done(job_id, CREATE_IDEMPOTENCY_PLATFORM, opus_post_id=post_id, path=ledger_path)

    # Explicit videoId on create response (rare) — must still be validated.
    video_id = extract_youtube_video_id(resp if isinstance(resp, dict) else {})
    if not video_id:
        # Match by this postId only — never the first parseable URL in the list.
        video_id = extract_youtube_video_id_for_post(
            resp if isinstance(resp, dict) else {},
            post_id,
            post_account_id=post_account_id,
        )
    if not video_id:
        video_id = _resolve_video_for_post(post_id)

    if not video_id:
        raise RuntimeError("opus_no_video_id")

    return _return_for(post_id, video_id)



def notify_fail(item, err, *, push_fn=None):
    try:
        title = "YouTube label failed — left private"
        name = (item.get("title") or item.get("id") or "clip")[:60]
        body = f"{name}: {err}. Video stays private."
        if push_fn:
            return push_fn(title, body, key=f"ytlabel-fail:{item.get('id')}")
        import push_alerts as _push
        return _push.send_ntfy(title, body, key=f"ytlabel-fail:{item.get('id')}", tags="warning", priority="high")
    except Exception:
        return False


def notify_tt_ig_labels(item, *, push_fn=None):
    """ONE push with deep links for TikTok + Instagram AI labels.

    Returns True only when the push was sent. Caller marks TT/IG done on True;
    on False keeps label_pending and should fire the failure alert.
    """
    try:
        name = (item.get("title") or item.get("id") or "clip")[:60]
        title = "Set TikTok + IG AI labels"
        body = (
            f"{name} needs AI labels on TikTok + Instagram. "
            f"TikTok: {TIKTOK_LABEL_HELP} · Instagram: {IG_LABEL_HELP}"
        )
        if push_fn:
            return bool(push_fn(title, body, key=f"ttig-label:{item.get('id')}"))
        import push_alerts as _push
        return bool(_push.send_ntfy(
            title, body, key=f"ttig-label:{item.get('id')}", tags="label", priority="high",
        ))
    except Exception:
        return False


def apply_tt_ig_after_push(item, pushed, *, yt_step_on=None):
    """Flip TT/IG to done when push succeeded; complete status when YouTube is done or YT step is off.
    Push failed → leave label_pending (caller sends failure alert). Mutates item. Returns item.
    """
    if not isinstance(item, dict):
        return item
    if not pushed:
        return item
    item["tiktok_label_set"] = True
    item["instagram_label_set"] = True
    step_on = enabled() if yt_step_on is None else bool(yt_step_on)
    yt_ok = bool(item.get("youtube_label_set")) or (not step_on) or item.get("ai_disclosure") is False
    if yt_ok:
        item["status"] = "scheduled"
        item["privacy"] = "public"
    return item


def run_after_approve(
    item,
    *,
    env=None,
    http_post=None,
    http_json=None,
    opus_fn=None,
    push_fn=None,
    channel=None,
    ledger_path=None,
    require_paid_native=False,
):
    """Approve → (oauth if needed) → Opus private → synthetic flag → confirm → public.

    require_paid_native: when the route is a paid promotion, set and re-read
    paidProductPlacementDetails before privacy goes public. Default off so the
    existing label step does not change. #ad is not accepted as that toggle.
    Returns dict: ok, need_oauth, oauth_url, error, video_id, youtube_label.
    Fail closed on any error (video left private + push).
    """
    out = {
        "ok": False,
        "need_oauth": False,
        "oauth_url": None,
        "error": None,
        "video_id": None,
        "youtube_label": False,
        "skipped": False,
    }
    if not enabled(env):
        out["skipped"] = True
        out["ok"] = True
        return out
    if not isinstance(item, dict):
        out["error"] = "bad_item"
        return out
    # Storyblocks / routing guard before any Opus or YouTube call
    try:
        import schedule_hook as _sched
        route = _sched.route_for_item(item) or {}
        if route.get("blocked"):
            notify_fail(item, "storyblocks_or_route_blocked", push_fn=push_fn)
            out["error"] = "route_blocked:" + str(route.get("block_reason") or "")
            return out
        dest = str(route.get("target") or "").upper()
    except Exception:
        dest = str(item.get("route_target") or "").upper()
    # The grant channel comes ONLY from the item's own destination. A caller-supplied channel must match it;
    # refuse before any token load/refresh so a GAMING item can never touch MAIN's/PAID's grant (and vice versa).
    if dest not in GRANT_CHANNELS:
        out["error"] = "no_hub_grant_for_target:" + (dest or "NONE")[:16]
        notify_fail(item, out["error"], push_fn=push_fn)
        return out
    if channel is not None and str(channel).strip().upper() != dest:
        out["error"] = "channel_mismatch:%s!=%s" % (str(channel).strip().upper()[:16], dest)
        notify_fail(item, out["error"], push_fn=push_fn)
        return out
    ch = dest

    if needs_oauth(ch):
        url, err = build_auth_url(channel=ch, approval_id=str(item.get("id") or ""))
        out["need_oauth"] = True
        out["oauth_url"] = url
        out["regrant_url"] = regrant_hub_url(ch)
        reason = "grant_expired" if grant_meta(ch).get("present") else "oauth_required"
        out["error"] = err or reason
        notify_regrant(ch, reason, push_fn=push_fn, item=item)
        return out

    access, err = refresh_access(ch, http_post=http_post)
    if not access:
        if err in ("invalid_grant", "grant_expired"):
            out["need_oauth"] = True
            url, _ = build_auth_url(channel=ch, approval_id=str(item.get("id") or ""))
            out["oauth_url"] = url
            out["regrant_url"] = regrant_hub_url(ch)
            out["error"] = err
            notify_regrant(ch, err, push_fn=push_fn, item=item)
            return out
        notify_fail(item, err or "no_access", push_fn=push_fn)
        out["error"] = err or "no_access"
        return out

    try:
        up = opus_upload_private(item, opus_fn=opus_fn, http_json=http_json, ledger_path=ledger_path, push_fn=push_fn)
        video_id = normalize_youtube_video_id(str((up or {}).get("video_id") or ""))
        if not video_id:
            raise RuntimeError("opus_no_video_id")
        out["video_id"] = video_id

        # GET first: refuse to mutate a public video or a missing/wrong id.
        status0 = get_video_status(video_id, access, http_json=http_json) or {}
        if not status0:
            raise RuntimeError("video_not_found_before_label")
        # Fail-closed: video must live on the granted/expected hub channel.
        tok = load_token(ch) or {}
        assert_video_owned_by_grant(
            status0, ch, bound_channel_id=tok.get("bound_channel_id"),
        )
        priv0 = str(status0.get("privacyStatus") or "").lower()
        if priv0 == "public":
            raise RuntimeError("refuse_mutate_already_public")
        if priv0 != "private":
            raise RuntimeError("expected_private_before_label")

        set_contains_synthetic(video_id, access, http_json=http_json)
        status_pre = get_video_status(video_id, access, http_json=http_json) or {}
        if not status_pre.get("containsSyntheticMedia"):
            raise RuntimeError("synthetic_not_confirmed")
        if str(status_pre.get("privacyStatus") or "").lower() != "private":
            raise RuntimeError("expected_private_before_public")

        if require_paid_native:
            paid = False
            try:
                import schedule_hook as _sched_paid
                paid = bool((_sched_paid.route_for_item(item) or {}).get("paid_promotion"))
            except Exception:
                paid = bool(item.get("is_ad") or item.get("campaign_id"))
            if paid:
                set_paid_placement(video_id, access, http_json=http_json)
                if not paid_placement_confirmed(video_id, access, http_json=http_json):
                    raise RuntimeError("paid_placement_not_confirmed")

        set_privacy_public(video_id, access, http_json=http_json)
        status_after = get_video_status(video_id, access, http_json=http_json) or {}
        public_ok = str(status_after.get("privacyStatus") or "").lower() == "public"
        synth_ok = bool(status_after.get("containsSyntheticMedia"))
        if not public_ok or not synth_ok:
            # Confirm re-read failed after public flip → re-private, verify, then fail closed.
            repriv_ok = False
            try:
                set_privacy_private(video_id, access, http_json=http_json)
                status_priv = get_video_status(video_id, access, http_json=http_json) or {}
                repriv_ok = str(status_priv.get("privacyStatus") or "").lower() == "private"
            except Exception:
                repriv_ok = False
            if repriv_ok:
                raise RuntimeError("public_confirm_failed_reprivated")
            notify_may_be_public(item, "re-private did not verify after failed public confirm", push_fn=push_fn)
            raise RuntimeError("public_confirm_failed_MAY_BE_PUBLIC")

        out["ok"] = True
        out["youtube_label"] = True
        item["youtube_label_set"] = True
        pushed = notify_tt_ig_labels(item, push_fn=push_fn)
        apply_tt_ig_after_push(item, pushed, yt_step_on=True)
        out["tt_ig_push"] = bool(pushed)
        if not pushed:
            # YT already public; hub stays label_pending until a later retry/push.
            notify_fail(item, "tt_ig_push_failed", push_fn=push_fn)
            out["error"] = "tt_ig_push_failed"
            # ok stays True for YouTube; tt_ig_push False signals pending labels
        return out
    except Exception as e:
        err = str(e)[:200]
        out["error"] = err
        out["ok"] = False
        out["youtube_label"] = False
        # If the URGENT may-be-PUBLIC alert already fired, do not also send
        # the generic "left private" failure (one alert only).
        # Only alert "left private" when YouTube GET verifies privacyStatus=private.
        if "MAY_BE_PUBLIC" not in err:
            verified_private = False
            try:
                vid = normalize_youtube_video_id(str(out.get("video_id") or ""))
                if vid and access:
                    st_v = get_video_status(vid, access, http_json=http_json) or {}
                    verified_private = str(st_v.get("privacyStatus") or "").lower() == "private"
            except Exception:
                verified_private = False
            if verified_private:
                notify_fail(item, err[:120], push_fn=push_fn)
        return out




def try_reconcile_label_item(item, *, env=None, http_json=None, push_fn=None, ledger_path=None, youtube_runner=None):
    """Re-entrant path for label_pending: reconcile timeout_pending / finish label. Never re-POST create blindly.
    Invoked from Approve re-entry or authorized tick.
    """
    if not enabled(env):
        return {"ok": True, "skipped": True}
    if not isinstance(item, dict):
        return {"ok": False, "error": "bad_item"}
    # Delegate to run_after_approve which uses ledger reconcile-only when timeout_pending/stale.
    runner = youtube_runner or run_after_approve
    return runner(item, env=env, http_json=http_json, push_fn=push_fn, ledger_path=ledger_path)
