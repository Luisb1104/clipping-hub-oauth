"""Platform publish adapters.

YouTube promote uses the stdlib client when no test double is installed.
That client is not a live proof: callers and tests must supply the network.
Other platforms stay disabled until a test or runner injects HTTP.

YouTube: Data API resumable videos.insert for a local file. Opus project and
clip ids are not required. A missing hub grant is an auth readiness gate.

Instagram: Content Publishing guide (updated Oct 20, 2026, examples on v27.0).
Reel container uses media_type=REELS. A local file uses upload_type=resumable
and rupload.facebook.com, then POST /<IG_ID>/media_publish with creation_id.

Facebook: Reels Publishing guide v27.0 for the upload steps. Graph API
reference lists is_ai_generated. No paid field is documented on that edge.

TikTok: Postiz public API (POST /public/v1/upload and POST /public/v1/posts),
DIRECT_POST settings only. This process cannot call the agent's Postiz connector.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from urllib.error import HTTPError, URLError
import stat
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# videos.insert, page updated 2026-11-03 UTC.
# The "you can set" list names status.privacyStatus and status.containsSyntheticMedia.
# It does not name paidProductPlacementDetails.hasPaidProductPlacement.
# Omitting privacyStatus defaults the upload to public, so a new upload must
# send private. Unverified API projects are not forced to stay private; that
# sentence is not a monetization rule. Quota on that page: 100 calls/day,
# 1 unit in the Video Uploads bucket.
YOUTUBE_PRIVACY_SOURCE = (
    "videos.insert status.privacyStatus (updated 2026-11-03): "
    "If unset, privacy defaults to public. Unverified API projects are not "
    "restricted to private viewing mode."
)
YOUTUBE_INIT = (
    "https://www.googleapis.com/upload/youtube/v3/videos"
    "?uploadType=resumable&part=snippet,status"
)
# channels.list mine=true, part=id only. Proves the token's channel before any upload byte.
YOUTUBE_CHANNELS_MINE = "https://www.googleapis.com/youtube/v3/channels?part=id&mine=true"
# Resumable PUT Location must be this host. HTTP, userinfo, localhost,
# link-local, metadata hosts, and any port other than 443 are rejected.
# Redirects are not followed.
YOUTUBE_UPLOAD_HOSTS = frozenset({"www.googleapis.com"})

# Graph API reference, Page Video Reels create parameters.
FB_AI_SOURCE = (
    "Graph API reference /{page_id}/video_reels, is_ai_generated boolean: "
    "A boolean flag for developers to self-claim whether the video was created with AI. "
    "Reels publishing guide examples use graph.facebook.com v27.0."
)
FB_GRAPH = "https://graph.facebook.com/v27.0"
FB_RUPLOAD = "https://rupload.facebook.com/video-upload/v27.0"

IG_GRAPH = "https://graph.facebook.com/v27.0"
IG_RUPLOAD = "https://rupload.facebook.com/ig-api-upload/v27.0"
IG_SOURCE = (
    "Instagram Content Publishing, updated Oct 20, 2026. "
    "POST /<IG_ID>/media media_type=REELS; local file via upload_type=resumable "
    "then POST rupload.facebook.com/ig-api-upload/<API_VERSION>/<IG_MEDIA_CONTAINER_ID> "
    "with offset and file_size; POST /<IG_ID>/media_publish creation_id. "
    "is_ai_generated, is_paid_partnership, and branded_content_sponsor_ids are container fields."
)

POSTIZ_ORIGIN = "https://api.postiz.com/public/v1"
# The Hub process has no MCP session. Postiz is reached only by this HTTP API
# when an API key and integration id are configured. integrationList on the
# agent connector was empty; that is an account gate, not a second TikTok OAuth.
POSTIZ_BOUNDARY = (
    "Hub runtime cannot invoke the agent Postiz connector. "
    "Supported boundary is POST /public/v1/upload and POST /public/v1/posts "
    "with a Postiz API key and a connected integration id. "
    "content_posting_method UPLOAD is the TikTok inbox and is not a publish."
)

HTTP = None  # tests assign a callable. Production promote does not read this.
YOUTUBE_PROMOTE_TIMEOUT_S = 30
# The video-byte PUT only. Metadata, channel proof, and session-status queries stay at 30s.
YOUTUBE_UPLOAD_PUT_TIMEOUT_S = 120


def _http():
    return HTTP


class _RejectYouTubeRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is not followed. The token must not be sent to the new host.

    Resumable upload status uses 308 Resume Incomplete with no Location.
    That response is returned to the caller. A 308 that names a new URL is
    rejected the same way as any other redirect.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise URLError("redirect_rejected")

    def http_error_308(self, req, fp, code, msg, headers):
        location = None
        if headers is not None:
            location = headers.get("Location")
        if location:
            raise URLError("redirect_rejected")
        raise HTTPError(getattr(req, "full_url", ""), code, msg, headers, fp)


def youtube_promote_url_ok(url):
    """True only for https://www.googleapis.com/youtube/v3/videos list or status update."""
    if not isinstance(url, str):
        return False
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    if parts.port not in (None, 443):
        return False
    host = (parts.hostname or "").rstrip(".").lower()
    if host != "www.googleapis.com" or parts.path != "/youtube/v3/videos":
        return False
    query = parse_qs(parts.query, keep_blank_values=False)
    part = (query.get("part") or [""])[0]
    if part not in ("status", "snippet,status"):
        return False
    if part == "snippet,status":
        video_id = (query.get("id") or [""])[0]
        return youtube_video_id_ok(video_id)
    return "id" not in query


class _NoEnvironmentProxy(urllib.request.ProxyHandler):
    """Proxy map is empty, so getproxies() and env proxy variables are not used."""

    def __init__(self):
        super().__init__({})

    def http_open(self, req):
        return None

    def https_open(self, req):
        return None


def youtube_promote_opener():
    """Opener with no environment proxy and no redirect following.

    The default opener would install ProxyHandler(), which reads HTTP_PROXY,
    HTTPS_PROXY, and ALL_PROXY. An empty map skips that lookup. The default
    HTTPS handler stays in place and keeps certificate and hostname checks.
    """
    return urllib.request.build_opener(
        _NoEnvironmentProxy(),
        _RejectYouTubeRedirect,
    )


def youtube_promote_http(method, url, headers, body):
    """Stdlib YouTube videos client. No redirects, no other hosts, no header logging.

    This opens a socket only when a caller invokes it. Tests that replace
    urllib's opener never leave this process. It is not evidence of a live post.
    """
    if method not in ("GET", "PUT") or not youtube_promote_url_ok(url):
        raise URLError("youtube_destination_rejected")
    data = body if isinstance(body, bytes) else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = youtube_promote_opener()
    try:
        with opener.open(req, timeout=YOUTUBE_PROMOTE_TIMEOUT_S) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode() or "{}") if raw else {}
            return {"status": getattr(resp, "status", 200), "headers": {}, "json": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        try:
            parsed = json.loads(raw.decode() or "{}")
        except ValueError:
            parsed = {}
        return {"status": exc.code, "headers": {}, "json": parsed}


def youtube_metadata(*, title, description, ai, paid):
    """Writable on videos.insert: status.privacyStatus and status.containsSyntheticMedia.

    The insert "you can set" list dated 2026-11-03 does not name
    paidProductPlacementDetails. The part name existing on the resource is
    not write support. paid is ignored. privacyStatus is private: omitting it
    would default the upload to public.
    """
    del paid
    return {
        "snippet": {
            "title": (title or "Clip")[:100],
            "description": description or "",
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "private",
            "containsSyntheticMedia": bool(ai),
        },
    }


_YT_CHANNEL_ID = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
_YT_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# videos.update part=status, page dated 2026-11-03.
# These three are writable and are deleted if omitted. publishAt is also
# writable, but only while privacy stays private, so a public promotion must
# not send it. selfDeclaredMadeForKids and containsSyntheticMedia are exempt:
# omitting them keeps the current value. Output-only status fields
# (uploadStatus, failureReason, rejectionReason, madeForKids) are not copied.
_YT_STATUS_PRESERVE = ("embeddable", "license", "publicStatsViewable")
_YT_LICENSES = {"youtube", "creativeCommon"}
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"


def youtube_video_id_ok(value):
    return bool(_YT_VIDEO_ID.fullmatch(str(value or "").strip()))


def youtube_promote_status_body(current, *, ai):
    """Status object for videos.update, or None when the preflight is incomplete.

    embeddable, license, and publicStatsViewable are deleted by YouTube when
    omitted. A missing or unusable value refuses the update instead of
    resetting it. Exempt fields (selfDeclaredMadeForKids, and
    containsSyntheticMedia unless AI is requested) stay omitted on purpose.
    publishAt is not sent because a public video cannot keep a schedule.
    """
    current = current if isinstance(current, dict) else {}
    if not isinstance(current.get("embeddable"), bool):
        return None
    if not isinstance(current.get("publicStatsViewable"), bool):
        return None
    if current.get("license") not in _YT_LICENSES:
        return None
    status = {
        "privacyStatus": "public",
        "embeddable": current["embeddable"],
        "publicStatsViewable": current["publicStatsViewable"],
        "license": current["license"],
    }
    if ai:
        status["containsSyntheticMedia"] = True
    return status


def _uncertain_transport(exc):
    """Lost or timed-out transport. An HTTP error response is a definite result."""
    if isinstance(exc, HTTPError):
        return False
    return isinstance(exc, (TimeoutError, URLError))


def youtube_channel_id_ok(value):
    """True only for a non-blank YouTube channel id. Empty is not a bound grant."""
    return bool(_YT_CHANNEL_ID.fullmatch(str(value or "").strip()))


def youtube_put_location_ok(location):
    """True only for an https URL on an allowlisted Google upload host."""
    if not isinstance(location, str) or not location.strip():
        return False
    parts = urlsplit(location.strip())
    if parts.scheme != "https":
        return False
    if parts.username or parts.password:
        return False
    host = (parts.hostname or "").rstrip(".").lower()
    if not host or host not in YOUTUBE_UPLOAD_HOSTS:
        return False
    if parts.port not in (None, 443):
        return False
    return True


def _yt_error_reason(payload):
    err = (payload or {}).get("error") if isinstance(payload, dict) else None
    errors = (err or {}).get("errors") if isinstance(err, dict) else None
    for row in errors or []:
        if isinstance(row, dict) and row.get("reason") == "forbiddenPrivacySetting":
            return "youtube_privacy_rejected"
    if isinstance(err, dict) and "forbiddenPrivacySetting" in json.dumps(err):
        return "youtube_privacy_rejected"
    return None


def youtube_insert_url_ok(method, url):
    """Channel proof, the fixed session URL, or an allowlisted Location. Nothing else."""
    if method == "GET":
        return url == YOUTUBE_CHANNELS_MINE
    if method == "POST":
        return url == YOUTUBE_INIT
    if method == "PUT":
        return youtube_put_location_ok(url)
    return False


def youtube_insert_http(method, url, headers, body):
    """Stdlib resumable insert. No env proxy, no redirects, no other hosts.

    The video-byte PUT uses the upload timeout. Channel proof, session start,
    and a status query stay on the short timeout. A mocked opener is not a
    live upload. This does not search by title or size.
    """
    if not youtube_insert_url_ok(method, url):
        raise URLError("youtube_destination_rejected")
    data = body if isinstance(body, bytes) else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = youtube_promote_opener()
    timeout = YOUTUBE_UPLOAD_PUT_TIMEOUT_S if method == "PUT" and data else YOUTUBE_PROMOTE_TIMEOUT_S
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode() or "{}") if raw else {}
            hdrs = {}
            location = None
            if getattr(resp, "headers", None) is not None:
                location = resp.headers.get("Location")
            if location:
                hdrs["Location"] = location
            return {"status": getattr(resp, "status", 200), "headers": hdrs, "json": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        try:
            parsed = json.loads(raw.decode() or "{}")
        except ValueError:
            parsed = {}
        hdrs = {}
        if exc.headers is not None and exc.headers.get("Location"):
            hdrs["Location"] = exc.headers.get("Location")
        return {"status": exc.code, "headers": hdrs, "json": parsed}


def _mine_channel_ids(payload):
    """Channel ids from channels.list, or None when the body does not prove a list."""
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    ids = []
    for item in items:
        if not isinstance(item, dict):
            return None
        cid = str(item.get("id") or "")
        if not youtube_channel_id_ok(cid):
            return None
        ids.append(cid)
    return ids


def _prove_upload_channel(http, token, expected_channel_id):
    """GET channels.list mine=true. None means the token's only channel matches.

    This read happens before any session. A timeout or a body that does not
    prove exactly one channel is retryable: called stays false and no POST
    or PUT is made. A different single channel is a mismatch.
    """
    headers = {"Authorization": "Bearer " + str(token), "Accept": "application/json"}
    try:
        resp = http("GET", YOUTUBE_CHANNELS_MINE, headers, None)
    except Exception as exc:
        if _uncertain_transport(exc):
            return {
                "ok": False, "called": False, "mutation": False,
                "reason": "youtube_channel_preflight_failed",
                "error": "youtube_channel_preflight_failed",
                "transport": "youtube_resumable_upload",
            }
        raise
    status = int((resp or {}).get("status") or 0)
    ids = _mine_channel_ids((resp or {}).get("json") if isinstance(resp, dict) else None)
    if status != 200 or not ids or len(ids) != 1:
        return {
            "ok": False, "called": False, "mutation": False,
            "reason": "youtube_channel_preflight_failed",
            "error": "youtube_channel_preflight_failed",
            "transport": "youtube_resumable_upload",
        }
    if ids[0] != str(expected_channel_id or ""):
        return {
            "ok": False, "called": False, "mutation": False,
            "reason": "youtube_channel_mismatch", "error": "youtube_channel_mismatch",
            "transport": "youtube_resumable_upload",
        }
    return None


def _video_channel_id(video):
    snippet = video.get("snippet") if isinstance(video, dict) else None
    status = video.get("status") if isinstance(video, dict) else None
    return str(
        ((snippet or {}).get("channelId") if isinstance(snippet, dict) else "")
        or ((status or {}).get("channelId") if isinstance(status, dict) else "")
        or ""
    )


def _private_video_result(video, *, expected_channel_id, ai, mutation):
    """Bind a completed video only when channel, privacy, and echo are proven."""
    video = video if isinstance(video, dict) else {}
    vid = str(video.get("id") or "")
    status_obj = video.get("status") if isinstance(video.get("status"), dict) else {}
    privacy = str(status_obj.get("privacyStatus") or "").lower()
    got_channel = _video_channel_id(video)
    if not got_channel:
        return {
            "ok": False, "called": True, "accepted": True, "mutation": mutation,
            "reason": "youtube_video_missing_channel_id", "error": "youtube_video_missing_channel_id",
            "video_id": vid,
        }
    if got_channel != str(expected_channel_id or ""):
        return {
            "ok": False, "called": True, "accepted": True, "mutation": mutation,
            "reason": "youtube_channel_mismatch", "error": "youtube_channel_mismatch",
            "video_id": vid,
        }
    if privacy != "private":
        return {
            "ok": False, "called": True, "accepted": True, "mutation": mutation,
            "reason": "youtube_privacy_not_private", "error": "youtube_privacy_not_private",
            "video_id": vid,
        }
    synth = status_obj.get("containsSyntheticMedia")
    if ai and "containsSyntheticMedia" not in status_obj:
        return {
            "ok": False, "called": True, "accepted": True, "mutation": mutation, "echo_omitted": True,
            "reason": "youtube_synthetic_echo_omitted", "error": "youtube_synthetic_echo_omitted",
            "video_id": vid,
        }
    if ai and synth is not True:
        return {
            "ok": False, "called": True, "accepted": True, "mutation": mutation,
            "reason": "youtube_synthetic_not_confirmed", "error": "youtube_synthetic_not_confirmed",
            "video_id": vid,
        }
    return {
        "ok": False, "private_uploaded": True, "called": True, "mutation": mutation,
        "youtube_label": bool(ai), "video_id": vid,
    }


def youtube_session_status(session_url, *, token, http, file_size, expected_channel_id, ai=False):
    """Ask one allowlisted session whether the upload finished. Sends no video bytes.

    200 or 201 can bind a video id only when the channel matches. Anything else
    stays unproven. This does not start a session and does not promote.
    """
    if not youtube_put_location_ok(session_url):
        return {
            "ok": False, "called": False, "proven": False, "mutation": False,
            "reason": "youtube_channel_unproven", "error": "youtube_channel_unproven",
        }
    try:
        size = int(file_size)
    except (TypeError, ValueError):
        return {
            "ok": False, "called": False, "proven": False, "mutation": False,
            "reason": "youtube_channel_unproven", "error": "youtube_channel_unproven",
        }
    if size < 0 or not youtube_channel_id_ok(expected_channel_id) or not token:
        return {
            "ok": False, "called": False, "proven": False, "mutation": False,
            "reason": "youtube_channel_unproven", "error": "youtube_channel_unproven",
        }
    if http is None:
        http = youtube_insert_http
    headers = {
        "Authorization": "Bearer " + str(token),
        "Content-Length": "0",
        "Content-Range": "bytes */%d" % size,
    }
    try:
        resp = http("PUT", session_url, headers, b"")
    except Exception as exc:
        if _uncertain_transport(exc):
            return {
                "ok": False, "called": True, "proven": False, "mutation": False,
                "reason": "transport_uncertain", "error": "transport_uncertain",
            }
        raise
    status = int((resp or {}).get("status") or 0)
    if status == 308:
        # The session is unfinished now. It can still complete later, so this
        # observation does not authorize a new insert.
        return {
            "ok": False, "called": True, "proven": False, "mutation": False,
            "reason": "upload_incomplete", "error": "upload_incomplete",
            "session_observation": "upload_incomplete",
        }
    video = (resp or {}).get("json") if isinstance(resp, dict) else None
    video = video if isinstance(video, dict) else {}
    if status not in (200, 201) or not video.get("id"):
        return {
            "ok": False, "called": True, "proven": False, "mutation": False,
            "reason": "youtube_channel_unproven", "error": "youtube_channel_unproven",
        }
    got = _video_channel_id(video)
    if got != str(expected_channel_id):
        return {
            "ok": False, "called": True, "proven": False, "mutation": False,
            "reason": "youtube_channel_unproven", "error": "youtube_channel_unproven",
        }
    result = _private_video_result(video, expected_channel_id=expected_channel_id, ai=bool(ai), mutation=False)
    result["proven"] = True
    return result


def youtube_upload(item, row, *, token, http, file_bytes, expected_channel_id=None):
    """Private resumable insert of the exact approved bytes.

    Paid placement returns before any request. Success is a private video id
    on the bound channel. It does not promote the video. A missing synthetic
    echo is not a confirmed label. http=None uses the stdlib insert client.
    A video id already in the private-proof, promote, or post ledger is not
    inserted again.
    """
    import ledger_dedupe as _dedupe
    gate = _dedupe.check_upload(
        item if isinstance(item, dict) else {},
        sha256=str((row or {}).get("artifact_sha256") or ""),
        channel_id=str(expected_channel_id or (row or {}).get("bound_channel_id") or ""),
    )
    if gate.get("action") == "fail":
        reason = str(gate.get("reason") or "ledger_unreadable")
        return {
            "ok": False, "called": False, "reason": reason, "error": reason,
            "transport": "youtube_resumable_upload",
        }
    if gate.get("action") == "skip":
        reason = str(gate.get("reason") or "")
        return {
            "ok": False, "called": False, "reason": reason, "error": reason,
            "video_id": gate.get("video_id") or "",
            "transport": "youtube_resumable_upload",
        }
    disc = row.get("disclosures") or {}
    if disc.get("paid"):
        return {
            "ok": False, "called": False, "reason": "youtube_paid_label_unverified",
            "error": "youtube_paid_label_unverified",
            "transport": "youtube_resumable_upload",
        }
    if not youtube_channel_id_ok(expected_channel_id):
        return {
            "ok": False, "called": False, "reason": "youtube_channel_unbound",
            "error": "youtube_channel_unbound",
            "transport": "youtube_resumable_upload",
        }
    if not token:
        return {
            "ok": False, "called": False, "reason": "youtube_grant_absent",
            "transport": "youtube_resumable_upload",
        }
    approved = str((row or {}).get("artifact_sha256") or "")
    digest = hashlib.sha256(file_bytes or b"").hexdigest()
    if not approved or approved != digest:
        return {
            "ok": False, "called": False, "reason": "artifact_hash_mismatch",
            "error": "artifact_hash_mismatch",
            "transport": "youtube_resumable_upload",
        }
    if http is None:
        http = youtube_insert_http
    proof = _prove_upload_channel(http, token, expected_channel_id)
    if proof is not None:
        return proof
    meta = youtube_metadata(
        title=(item.get("title") or item.get("caption") or "Clip"),
        description=row.get("caption") or item.get("caption") or "",
        ai=bool(disc.get("ai")),
        paid=bool(disc.get("paid")),
    )
    raw = json.dumps(meta).encode()
    init_headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(len(file_bytes)),
        "X-Upload-Content-Type": "video/mp4",
    }
    try:
        init = http("POST", YOUTUBE_INIT, init_headers, raw)
    except Exception as exc:
        if _uncertain_transport(exc):
            return {
                "ok": False, "called": True, "accepted": True, "mutation": False,
                "reason": "transport_uncertain", "error": "transport_uncertain",
            }
        raise
    status = int((init or {}).get("status") or 0)
    body = (init or {}).get("json") or {}
    privacy_reason = _yt_error_reason(body)
    if privacy_reason or status == 403:
        return {
            "ok": False, "called": True, "reason": privacy_reason or "youtube_privacy_rejected",
            "error": privacy_reason or "youtube_privacy_rejected",
        }
    location = ((init or {}).get("headers") or {}).get("Location") or ((init or {}).get("headers") or {}).get("location")
    if status != 200 or not location:
        return {"ok": False, "called": True, "reason": "youtube_session_failed", "error": "youtube_session_failed"}
    if not youtube_put_location_ok(location):
        return {
            "ok": False, "called": True, "reason": "youtube_upload_location_rejected",
            "error": "youtube_upload_location_rejected",
        }
    put_headers = {
        "Authorization": "Bearer " + token,
        "Content-Length": str(len(file_bytes)),
        "Content-Type": "video/mp4",
    }
    try:
        put = http("PUT", location, put_headers, file_bytes)
    except Exception as exc:
        if _uncertain_transport(exc):
            return {
                "ok": False, "called": True, "accepted": True, "mutation": True,
                "reason": "transport_uncertain", "error": "transport_uncertain",
                "remote_id": location,
                "upload_length": len(file_bytes),
            }
        raise
    put_status = int((put or {}).get("status") or 0)
    video = (put or {}).get("json") or {}
    if put_status == 308:
        return {
            "ok": False, "called": True, "accepted": True, "mutation": True,
            "reason": "upload_incomplete", "error": "upload_incomplete",
            "remote_id": location, "upload_length": len(file_bytes),
        }
    if 300 <= put_status < 400:
        return {
            "ok": False, "called": True, "reason": "youtube_upload_redirect",
            "error": "youtube_upload_redirect", "video_id": str(video.get("id") or ""),
        }
    if _yt_error_reason(video) or put_status == 403:
        return {"ok": False, "called": True, "reason": "youtube_privacy_rejected", "error": "youtube_privacy_rejected",
                "video_id": str(video.get("id") or "")}
    if put_status not in (200, 201) or not video.get("id"):
        return {"ok": False, "called": True, "accepted": bool(video.get("id")), "reason": "youtube_upload_incomplete",
                "error": "youtube_upload_incomplete", "video_id": str(video.get("id") or "")}
    result = _private_video_result(
        video, expected_channel_id=expected_channel_id, ai=bool(disc.get("ai")), mutation=True,
    )
    if youtube_put_location_ok(location):
        result["session_url"] = location
    return result


def _yt_resource(payload):
    if not isinstance(payload, dict):
        return {}
    items = payload.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    if payload.get("id"):
        return payload
    return {}


def youtube_promote_existing(item, row, *, token, http, expected_channel_id, video_id):
    """Promote one named private video with videos.update part=status.

    Does not insert. A ledger hit is not enough: video_id and the bound channel
    are required. Preflight reads channel, id, and current privacy. Only a
    private video is updated. Already-public is not mutated again. Missing
    synthetic echo stays unconfirmed.
    """
    disc = (row or {}).get("disclosures") or {}
    named = str(video_id or "").strip()
    bound = str(expected_channel_id or "").strip()
    if disc.get("paid"):
        return {"ok": False, "called": False, "reason": "youtube_paid_label_unverified", "error": "youtube_paid_label_unverified"}
    if not youtube_video_id_ok(named):
        return {"ok": False, "called": False, "reason": "existing_video_reconcile", "error": "existing_video_reconcile"}
    if not youtube_channel_id_ok(bound):
        return {"ok": False, "called": False, "reason": "youtube_channel_unbound", "error": "youtube_channel_unbound"}
    if not token:
        return {"ok": False, "called": False, "reason": "youtube_grant_absent", "error": "youtube_grant_absent"}
    if http is None:
        return {"ok": False, "called": False, "reason": "live_network_disabled", "error": "live_network_disabled"}
    headers = {"Authorization": "Bearer " + str(token), "Accept": "application/json"}
    list_url = YOUTUBE_VIDEOS + "?part=snippet,status&id=" + named
    try:
        listed = http("GET", list_url, headers, None)
    except Exception as exc:
        if _uncertain_transport(exc):
            return {"ok": False, "called": True, "accepted": True, "mutation": False, "reason": "transport_uncertain", "error": "transport_uncertain", "video_id": named}
        raise
    resource = _yt_resource((listed or {}).get("json") or {})
    got_id = str(resource.get("id") or "")
    status_obj = resource.get("status") if isinstance(resource.get("status"), dict) else {}
    got_channel = str(((resource.get("snippet") or {}).get("channelId") or status_obj.get("channelId") or ""))
    privacy_from = str(status_obj.get("privacyStatus") or "").lower()
    if got_id != named or not got_channel:
        return {
            "ok": False, "called": True, "mutation": False, "reason": "youtube_video_missing_channel_id",
            "error": "youtube_video_missing_channel_id", "video_id": named, "privacy_from": privacy_from,
        }
    if got_channel != bound:
        return {
            "ok": False, "called": True, "mutation": False, "reason": "youtube_channel_mismatch",
            "error": "youtube_channel_mismatch", "video_id": named, "privacy_from": privacy_from,
        }
    if privacy_from != "private":
        if privacy_from == "public" and disc.get("ai") and "containsSyntheticMedia" not in status_obj:
            return {
                "ok": False, "called": True, "mutation": False, "accepted": True, "echo_omitted": True,
                "reason": "youtube_synthetic_echo_omitted", "error": "youtube_synthetic_echo_omitted",
                "video_id": named, "privacy_from": privacy_from,
            }
        if privacy_from == "public" and disc.get("ai") and status_obj.get("containsSyntheticMedia") is not True:
            return {
                "ok": False, "called": True, "mutation": False, "accepted": True,
                "reason": "youtube_synthetic_not_confirmed", "error": "youtube_synthetic_not_confirmed",
                "video_id": named, "privacy_from": privacy_from,
            }
        if privacy_from == "public":
            return {
                "ok": True, "called": True, "mutation": False, "youtube_label": bool(disc.get("ai")),
                "video_id": named, "privacy_from": privacy_from,
                "permalink": "https://www.youtube.com/watch?v=" + named,
                "reason": "already_public_no_mutation",
            }
        return {
            "ok": False, "called": True, "mutation": False, "reason": "youtube_privacy_not_private",
            "error": "youtube_privacy_not_private", "video_id": named, "privacy_from": privacy_from,
        }
    body_status = youtube_promote_status_body(status_obj, ai=bool(disc.get("ai")))
    if body_status is None:
        return {
            "ok": False, "called": True, "mutation": False,
            "reason": "youtube_status_preflight_incomplete",
            "error": "youtube_status_preflight_incomplete",
            "video_id": named, "privacy_from": privacy_from,
        }
    body = {"id": named, "status": body_status}
    raw = json.dumps(body).encode()
    put_headers = dict(headers, **{"Content-Type": "application/json; charset=UTF-8"})
    try:
        updated = http("PUT", YOUTUBE_VIDEOS + "?part=status", put_headers, raw)
    except Exception as exc:
        if _uncertain_transport(exc):
            return {
                "ok": False, "called": True, "accepted": True, "mutation": True,
                "reason": "transport_uncertain", "error": "transport_uncertain",
                "video_id": named, "privacy_from": privacy_from,
            }
        raise
    put_status = int((updated or {}).get("status") or 0)
    updated_resource = _yt_resource((updated or {}).get("json") or {})
    if put_status not in (200, 204) or (updated_resource.get("id") and str(updated_resource.get("id")) != named):
        return {
            "ok": False, "called": True, "mutation": True, "accepted": bool(updated_resource.get("id")),
            "reason": "youtube_promote_incomplete", "error": "youtube_promote_incomplete",
            "video_id": named, "privacy_from": privacy_from, "http_status": put_status,
        }
    try:
        readback = http("GET", list_url, headers, None)
    except Exception as exc:
        if _uncertain_transport(exc):
            return {
                "ok": False, "called": True, "accepted": True, "mutation": True,
                "reason": "transport_uncertain", "error": "transport_uncertain",
                "video_id": named, "privacy_from": privacy_from, "http_status": put_status,
            }
        raise
    back = _yt_resource((readback or {}).get("json") or {})
    back_status = back.get("status") if isinstance(back.get("status"), dict) else {}
    back_channel = str(((back.get("snippet") or {}).get("channelId") or back_status.get("channelId") or ""))
    privacy = str(back_status.get("privacyStatus") or "").lower()
    if str(back.get("id") or "") != named or back_channel != bound:
        return {
            "ok": False, "called": True, "accepted": True, "mutation": True,
            "reason": "youtube_channel_mismatch", "error": "youtube_channel_mismatch",
            "video_id": named, "privacy_from": privacy_from, "http_status": put_status,
        }
    if privacy != "public":
        return {
            "ok": False, "called": True, "accepted": True, "mutation": True,
            "reason": "youtube_privacy_not_public", "error": "youtube_privacy_not_public",
            "video_id": named, "privacy_from": privacy_from, "http_status": put_status,
        }
    if disc.get("ai") and "containsSyntheticMedia" not in back_status:
        return {
            "ok": False, "called": True, "accepted": True, "mutation": True, "echo_omitted": True,
            "reason": "youtube_synthetic_echo_omitted", "error": "youtube_synthetic_echo_omitted",
            "video_id": named, "privacy_from": privacy_from, "http_status": put_status,
            "permalink": "https://www.youtube.com/watch?v=" + named,
        }
    if disc.get("ai") and back_status.get("containsSyntheticMedia") is not True:
        return {
            "ok": False, "called": True, "accepted": True, "mutation": True,
            "reason": "youtube_synthetic_not_confirmed", "error": "youtube_synthetic_not_confirmed",
            "video_id": named, "privacy_from": privacy_from, "http_status": put_status,
        }
    return {
        "ok": True, "called": True, "mutation": True, "youtube_label": True, "video_id": named,
        "privacy_from": privacy_from, "http_status": put_status,
        "permalink": "https://www.youtube.com/watch?v=" + named,
    }


def instagram_reel(item, row, *, ig_user_id, token, sponsor_eligible, http, file_bytes):
    """Local Reel via the documented resumable container, rupload, and media_publish."""
    if not token or not ig_user_id:
        return {"ok": False, "called": False, "reason": "instagram_auth_identity_sponsor_unverified"}
    disc = row.get("disclosures") or {}
    if disc.get("paid") and not sponsor_eligible:
        return {"ok": False, "called": False, "reason": "instagram_sponsor_eligibility_unverified"}
    # No documented pre-publish read of is_ai_generated or is_paid_partnership.
    # Do not create the container just to see whether the label stuck.
    if disc.get("ai") or disc.get("paid"):
        return {"ok": False, "called": False, "reason": "disclosure_readback_unverified"}
    if http is None:
        return {"ok": False, "called": False, "reason": "live_network_disabled"}
    body = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": row.get("caption") or "",
        "is_ai_generated": bool(disc.get("ai")),
    }
    if disc.get("paid"):
        body["is_paid_partnership"] = True
        sponsors = [str(s) for s in (disc.get("sponsor_ids") or []) if str(s).strip()]
        if sponsors:
            body["branded_content_sponsor_ids"] = sponsors
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    try:
        created = http("POST", "%s/%s/media" % (IG_GRAPH, ig_user_id), headers, json.dumps(body).encode())
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout"}
    container = str(((created or {}).get("json") or {}).get("id") or "")
    if int((created or {}).get("status") or 0) not in (200, 201) or not container:
        return {"ok": False, "called": True, "reason": "instagram_container_failed", "error": "instagram_container_failed"}
    up_headers = {
        "Authorization": "OAuth " + token,
        "offset": "0",
        "file_size": str(len(file_bytes)),
        "Content-Type": "application/octet-stream",
    }
    try:
        uploaded = http(
            "POST", "%s/%s" % (IG_RUPLOAD, container), up_headers, file_bytes,
        )
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout", "remote_id": container}
    up_json = (uploaded or {}).get("json") or {}
    if up_json.get("success") is not True:
        return {"ok": False, "called": True, "reason": "instagram_rupload_failed", "error": "instagram_rupload_failed", "remote_id": container}
    try:
        published = http(
            "POST", "%s/%s/media_publish" % (IG_GRAPH, ig_user_id), headers,
            json.dumps({"creation_id": container}).encode(),
        )
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout", "remote_id": container}
    media_id = str(((published or {}).get("json") or {}).get("id") or "")
    if not media_id:
        return {"ok": False, "called": True, "accepted": True, "reason": "accepted_without_permalink", "error": "accepted_without_permalink", "remote_id": container}
    return {"ok": True, "called": True, "permalink": "https://www.instagram.com/reel/" + media_id, "video_id": media_id}


def facebook_reel(item, row, *, page_id, token, http, file_bytes):
    """v27.0 Page Reels upload. Paid stays blocked: the reference has no paid field."""
    disc = row.get("disclosures") or {}
    if disc.get("paid"):
        return {
            "ok": False, "called": False,
            "reason": "facebook_reels_paid_disclosure_not_in_official_schema",
            "source": FB_AI_SOURCE,
        }
    if not token or not page_id:
        return {"ok": False, "called": False, "reason": "facebook_reels_auth_absent", "source": FB_AI_SOURCE}
    if disc.get("ai") or disc.get("paid"):
        return {"ok": False, "called": False, "reason": "disclosure_readback_unverified", "source": FB_AI_SOURCE}
    if http is None:
        return {"ok": False, "called": False, "reason": "live_network_disabled", "source": FB_AI_SOURCE}
    start_body = json.dumps({"upload_phase": "start"}).encode()
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    try:
        started = http("POST", "%s/%s/video_reels" % (FB_GRAPH, page_id), headers, start_body)
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout"}
    video_id = str(((started or {}).get("json") or {}).get("video_id") or "")
    if not video_id:
        return {"ok": False, "called": True, "reason": "facebook_reels_start_failed", "error": "facebook_reels_start_failed"}
    up_headers = {
        "Authorization": "OAuth " + token,
        "offset": "0",
        "file_size": str(len(file_bytes)),
        "Content-Type": "application/octet-stream",
    }
    try:
        uploaded = http("POST", "%s/%s" % (FB_RUPLOAD, video_id), up_headers, file_bytes)
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout", "remote_id": video_id}
    if ((uploaded or {}).get("json") or {}).get("success") is not True:
        return {"ok": False, "called": True, "reason": "facebook_reels_upload_failed", "error": "facebook_reels_upload_failed", "remote_id": video_id}
    finish = {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": "PUBLISHED",
        "description": row.get("caption") or "",
        "is_ai_generated": bool(disc.get("ai")),
    }
    if "is_paid_partnership" in finish or "branded_content_sponsor_ids" in finish:
        raise RuntimeError("facebook_transplant")
    try:
        done = http("POST", "%s/%s/video_reels" % (FB_GRAPH, page_id), headers, json.dumps(finish).encode())
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout", "remote_id": video_id}
    if ((done or {}).get("json") or {}).get("success") is not True:
        return {"ok": False, "called": True, "accepted": True, "reason": "accepted_without_permalink", "error": "accepted_without_permalink", "remote_id": video_id}
    return {
        "ok": True, "called": True, "video_id": video_id,
        "permalink": "https://www.facebook.com/reel/" + video_id,
    }


def postiz_tiktok_settings(row):
    disc = row.get("disclosures") or {}
    return {
        "__type": "tiktok",
        "title": (row.get("caption") or "")[:90],
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "duet": False,
        "stitch": False,
        "comment": True,
        "autoAddMusic": "no",
        "brand_content_toggle": bool(disc.get("paid")),
        "brand_organic_toggle": False,
        "video_made_with_ai": bool(disc.get("ai")),
        "content_posting_method": "DIRECT_POST",
    }


def postiz_tiktok(item, row, *, api_key, integration_id, http, file_bytes, filename):
    """Postiz HTTP only. UPLOAD is never selected. No TikTok user token is minted here."""
    if not api_key or not integration_id:
        return {"ok": False, "called": False, "reason": "postiz_integration_absent", "boundary": POSTIZ_BOUNDARY}
    if http is None:
        return {"ok": False, "called": False, "reason": "live_network_disabled", "boundary": POSTIZ_BOUNDARY}
    settings = postiz_tiktok_settings(row)
    if settings["content_posting_method"] != "DIRECT_POST":
        return {"ok": False, "called": False, "reason": "postiz_upload_is_not_publish"}
    disc = row.get("disclosures") or {}
    if disc.get("ai") or disc.get("paid"):
        return {
            "ok": False, "called": False, "reason": "disclosure_readback_unverified",
            "boundary": POSTIZ_BOUNDARY,
        }
    auth = {"Authorization": api_key}
    try:
        uploaded = http(
            "POST", POSTIZ_ORIGIN + "/upload",
            dict(auth, **{"Content-Type": "multipart/form-data"}),
            {"file": (filename or "clip.mp4", file_bytes, "video/mp4")},
        )
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout"}
    media = (uploaded or {}).get("json") or {}
    if not media.get("id") or not media.get("path"):
        return {"ok": False, "called": True, "reason": "postiz_upload_failed", "error": "postiz_upload_failed"}
    if media.get("status") == "processing":
        return {"ok": False, "called": True, "accepted": True, "reason": "accepted_without_permalink", "error": "accepted_without_permalink", "remote_id": media.get("id")}
    post = {
        "type": "now",
        "shortLink": False,
        "tags": [],
        "posts": [{
            "integration": {"id": integration_id},
            "value": [{
                "content": row.get("caption") or "",
                "image": [{"id": media["id"], "path": media["path"]}],
            }],
            "settings": settings,
        }],
    }
    try:
        created = http(
            "POST", POSTIZ_ORIGIN + "/posts",
            dict(auth, **{"Content-Type": "application/json"}),
            json.dumps(post).encode(),
        )
    except TimeoutError:
        return {"ok": False, "called": True, "accepted": True, "reason": "timeout", "error": "timeout", "remote_id": media.get("id")}
    body = (created or {}).get("json") or {}
    release = str(body.get("releaseId") or body.get("postId") or body.get("id") or "")
    if not release or release == "missing":
        return {"ok": False, "called": True, "accepted": True, "reason": "accepted_without_permalink", "error": "accepted_without_permalink"}
    return {"ok": True, "called": True, "permalink": release, "video_id": release}


def samples_base(root=None):
    """Fixture dir when CLIPPING_HUB_SAMPLES_DIR is set, else <root>/static/samples."""
    env = os.environ.get("CLIPPING_HUB_SAMPLES_DIR", "").strip()
    if env:
        return Path(env)
    return (Path(root) if root else Path(__file__).resolve().parent) / "static" / "samples"


def open_sample(name, root=None):
    """Basename only, inside samples_base. Symlinks and path escape return None."""
    raw = str(name or "")
    if not raw or raw != Path(raw).name or "/" in raw or "\\" in raw or ".." in raw or raw.startswith("."):
        return None
    base = samples_base(root)
    try:
        if base.is_symlink():
            return None
        candidate = base / raw
        st = candidate.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode):
        return None
    try:
        resolved = candidate.resolve()
        resolved.relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    if not resolved.is_file():
        return None
    return resolved


def read_local(name, root=None):
    path = open_sample(name, root)
    if path is None:
        return None
    return path.read_bytes()
