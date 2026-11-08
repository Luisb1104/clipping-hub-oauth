"""Production YouTube promote transport. The socket is mocked. This is not a live post."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import stat
import threading
import urllib.request
from email.message import EmailMessage
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError

import publish_adapters as A
import public_publish as P
import youtube_label_step as yls

MAIN = "UCgMuVjQmB9WvZtSz4e23THw"
VIDEO = "LM6jkXooWGc"
ROOT = Path(__file__).resolve().parents[1]
REFRESH = "refresh-secret-value"
ACCESS = "mock-access-token"
SESSION = (
    "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id="
    + ("A" * 180)
)


def _sha():
    return hashlib.sha256((ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()).hexdigest()


def _oauth(monkeypatch, directory):
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(yls, "TOKEN_DIR", directory)
    monkeypatch.setattr(yls, "CLIENT_ID_FILE", directory / "client_id")
    monkeypatch.setattr(yls, "CLIENT_SECRET_FILE", directory / "client_secret")
    yls.CLIENT_ID_FILE.write_text("client-id.apps.googleusercontent.com")
    yls.CLIENT_SECRET_FILE.write_text("client-secret-value")
    yls.save_token("MAIN", {
        "refresh_token": REFRESH,
        "access_token": "stale-access",
        "bound_channel_id": MAIN,
        "scope": yls.SCOPE,
    })
    before = yls.token_path("MAIN").read_bytes()
    return before


def _legacy(tmp_path, sha):
    row = {
        "key": "private-proof:MAIN:%s:%s" % (MAIN, sha),
        "status": "readback_mismatch",
        "video_id": VIDEO,
        "public_success": False,
        "sha256": sha,
        "token_write": False,
    }
    (tmp_path / "legacy.jsonl").write_text(json.dumps(row) + "\n")


def _item():
    return {
        "id": "sample-07", "caption": "c", "title": "Hallway", "ai_disclosure": True,
        "rights_ok": True, "status": "pending",
        "video": "/samples/sample-a.mp4", "platforms": ["Clipped Motions YouTube"],
    }


def _install_socket(monkeypatch, *, put_error=False):
    calls = []

    def urlopen(req, timeout=None):
        calls.append(("token", req.full_url, timeout))
        class Resp:
            def read(self):
                return json.dumps({"access_token": ACCESS, "expires_in": 3600}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        return Resp()

    def opener_open(self, req, data=None, timeout=None):
        calls.append(("youtube", req.get_method(), req.full_url, timeout, req.data, req.get_header("Authorization")))
        if put_error and req.get_method() == "PUT":
            raise URLError(OSError("connection reset"))
        if req.get_method() == "PUT":
            body = json.loads(req.data.decode())
            payload = {"id": body["id"], "status": body["status"]}
        else:
            payload = {"items": [{
                "id": VIDEO,
                "snippet": {"channelId": MAIN},
                "status": {
                    "privacyStatus": "private" if not any(c[0] == "youtube" and c[1] == "PUT" for c in calls) else "public",
                    "embeddable": True,
                    "license": "youtube",
                    "publicStatsViewable": False,
                    "containsSyntheticMedia": True,
                },
            }]}
            if any(c[0] == "youtube" and c[1] == "PUT" for c in calls):
                payload["items"][0]["status"]["privacyStatus"] = "public"
        class Resp:
            status = 200
            def read(self):
                return json.dumps(payload).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", opener_open)
    return calls


def test_promote_url_policy_rejects_other_destinations_and_redirects():
    assert A.youtube_promote_url_ok("https://www.googleapis.com/youtube/v3/videos?part=status")
    assert A.youtube_promote_url_ok(
        "https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id=" + VIDEO
    )
    for bad in (
        "http://www.googleapis.com/youtube/v3/videos?part=status",
        "https://user:pass@www.googleapis.com/youtube/v3/videos?part=status",
        "https://upload.googleapis.com/upload/youtube/v3/videos?part=status",
        "https://oauth2.googleapis.com/token",
        "https://www.googleapis.com/youtube/v3/videos?part=snippet",
        "https://evil.example/youtube/v3/videos?part=status",
    ):
        assert A.youtube_promote_url_ok(bad) is False
    try:
        A._RejectYouTubeRedirect().redirect_request(None, None, 302, "found", {}, "https://evil.example/")
        assert False
    except URLError as exc:
        assert "redirect_rejected" in str(exc.reason)


def test_promote_client_ignores_environment_proxies(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://proxy.invalid:9")
    lookups = []
    real_getproxies = urllib.request.getproxies

    def spy_getproxies():
        lookups.append(real_getproxies())
        return lookups[-1]

    monkeypatch.setattr(urllib.request, "getproxies", spy_getproxies)
    seen = []

    def https_open(self, req):
        seen.append(req.full_url)
        class Resp:
            status = 200
            code = 200
            msg = "OK"
            def info(self):
                return {}
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        return Resp()

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)
    out = A.youtube_promote_http(
        "GET",
        "https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id=vidPublic01",
        {"Authorization": "Bearer mock-access-token"},
        None,
    )
    assert out["status"] == 200
    assert seen == ["https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id=vidPublic01"]
    opener = A.youtube_promote_opener()
    assert lookups == []
    proxies = [dict(h.proxies) for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert proxies == [{}]
    assert all("proxy.invalid" not in str(item) for item in proxies)
    contexts = [getattr(h, "_context", None) for h in opener.handlers]
    contexts = [c for c in contexts if isinstance(c, ssl.SSLContext)]
    assert contexts
    assert all(c.verify_mode == ssl.CERT_REQUIRED and c.check_hostname for c in contexts)


def test_already_public_preflight_does_not_send_an_update():
    calls = []

    def http(method, url, headers, body):
        calls.append((method, url, body))
        return {"status": 200, "json": {"items": [{
            "id": "vidPublic01",
            "snippet": {"channelId": "UCgMuVjQmB9WvZtSz4e23THw"},
            "status": {
                "privacyStatus": "public",
                "embeddable": True,
                "license": "youtube",
                "publicStatsViewable": False,
                "containsSyntheticMedia": True,
            },
        }]}}

    out = A.youtube_promote_existing(
        {"id": "sample-07"},
        {"disclosures": {"ai": True, "paid": False}},
        token="mock-access-token",
        http=http,
        expected_channel_id="UCgMuVjQmB9WvZtSz4e23THw",
        video_id="vidPublic01",
    )
    assert out["mutation"] is False
    assert out["reason"] == "already_public_no_mutation"
    assert [c[0] for c in calls] == ["GET"]


def test_confirmed_promote_uses_oauth_and_official_videos_endpoint(tmp_path, monkeypatch):
    assert A.HTTP is None
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    before = _oauth(monkeypatch, tmp_path / "oauth")
    sha = _sha()
    _legacy(tmp_path, sha)
    calls = _install_socket(monkeypatch)
    item = _item()
    manifest = P.build_manifest(item)
    row = manifest["platforms"][0]
    assert row["public_action"] == "promote_existing", (row.get("reason"), row.get("line"))
    assert row["existing_video_id"] == VIDEO
    out = P.dispatch_item(
        item, manifest["manifest_hash"],
        platform_rows=[{"key": "youtube", "row_hash": row["row_hash"]}],
        ledger_path=tmp_path / "promote.jsonl",
    )
    assert out["platforms"][0]["status"] == "done"
    assert out["platforms"][0]["public_action"] == "promote_existing"
    assert out["platforms"][0]["remote_id"] == VIDEO
    youtube = [c for c in calls if c[0] == "youtube"]
    assert [c[1] for c in youtube] == ["GET", "PUT", "GET"]
    assert youtube[0][2].startswith("https://www.googleapis.com/youtube/v3/videos?part=snippet%2Cstatus&id=" + VIDEO) or (
        "www.googleapis.com" in youtube[0][2] and "part=snippet" in youtube[0][2] and VIDEO in youtube[0][2]
    )
    assert youtube[1][2].startswith("https://www.googleapis.com/youtube/v3/videos?part=status")
    assert youtube[1][3] == A.YOUTUBE_PROMOTE_TIMEOUT_S
    put = json.loads(youtube[1][4].decode())
    assert put["id"] == VIDEO and "snippet" not in put and "paidProductPlacementDetails" not in put
    assert all(c[1].startswith("https://oauth2.googleapis.com/token") for c in calls if c[0] == "token")
    text = (tmp_path / "promote.jsonl").read_text()
    assert REFRESH not in text and ACCESS not in text
    assert yls.token_path("MAIN").read_bytes() == before
    again = P.dispatch_item(
        item, manifest["manifest_hash"],
        platform_rows=[{"key": "youtube", "row_hash": row["row_hash"]}],
        ledger_path=tmp_path / "promote.jsonl",
    )
    assert again["platforms"][0]["called"] is False
    assert [c[1] for c in calls if c[0] == "youtube"].count("PUT") == 1


def test_production_transport_disconnect_does_not_update_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    sha = _sha()
    _legacy(tmp_path, sha)
    calls = _install_socket(monkeypatch, put_error=True)
    item = _item()
    manifest = P.build_manifest(item)
    row = manifest["platforms"][0]
    rows = [{"key": "youtube", "row_hash": row["row_hash"]}]
    first = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "promote.jsonl")
    second = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "promote.jsonl")
    assert first["platforms"][0]["status"] == "unknown"
    assert first["platforms"][0]["reason"] == "transport_uncertain"
    assert second["platforms"][0]["called"] is False
    assert [c[1] for c in calls if c[0] == "youtube"].count("PUT") == 1


def _upload_video(channel=MAIN, video_id="vidNewUp001", privacy="private"):
    return {
        "id": video_id,
        "snippet": {"channelId": channel},
        "status": {"privacyStatus": privacy, "containsSyntheticMedia": True},
    }


def _insert_socket(monkeypatch, raw, *, put_error=False, status_error=False, status_video=None, preflight_failures=0, status_308=False, put_json=None, post_error=False):
    calls = []
    preflight_left = {"n": preflight_failures}

    def urlopen(req, timeout=None):
        calls.append(("token", req.full_url))
        class Resp:
            def read(self):
                return json.dumps({"access_token": ACCESS, "expires_in": 3600}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        return Resp()

    def opener_open(self, req, data=None, timeout=None):
        calls.append(("upload", req.get_method(), req.full_url, timeout, req.data, req.header_items()))
        if req.get_method() == "GET":
            if preflight_left["n"]:
                preflight_left["n"] -= 1
                raise URLError(TimeoutError("timed out"))
            body = json.dumps({"items": [{"id": MAIN}]}).encode()
            status = 200
        elif post_error and req.get_method() == "POST":
            raise URLError(TimeoutError("timed out"))
        elif put_error and req.get_method() == "PUT" and req.data:
            raise URLError(OSError("connection reset"))
        elif put_json is not None and req.get_method() == "PUT" and req.data:
            body = json.dumps(put_json).encode()
            status = 201
        elif status_error and req.get_method() == "PUT" and not req.data:
            raise URLError(OSError("status reset"))
        elif status_308 and req.get_method() == "PUT" and not req.data:
            class Incomplete:
                status = 308
                headers = None
                def read(self):
                    return b""
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
            return Incomplete()
        elif req.get_method() == "POST":
            class Headers:
                def get(self, key):
                    if key == "Location":
                        return SESSION
                    return None
            class Resp:
                status = 200
                headers = Headers()
                def read(self):
                    return b"{}"
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
            return Resp()
        else:
            payload = status_video if req.get_method() == "PUT" and not req.data and status_video is not None else _upload_video()
            body = json.dumps(payload).encode()
            status = 201
        class Resp:
            def __init__(self):
                self.status = status
                self.headers = None
            def read(self):
                return body
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", opener_open)
    return calls


def test_production_private_insert_uses_exact_bytes_and_does_not_promote(tmp_path, monkeypatch):
    assert A.HTTP is None
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    before = _oauth(monkeypatch, tmp_path / "oauth")
    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    calls = _insert_socket(monkeypatch, raw)
    item = {
        "id": "newclip01", "caption": "c", "title": "New clip", "ai_disclosure": True,
        "rights_ok": True, "status": "pending", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"],
    }
    manifest = P.build_manifest(item)
    row = manifest["platforms"][0]
    assert row["public_action"] == "private_upload"
    assert row["will_dispatch"] is True
    rows = [{"key": "youtube", "row_hash": row["row_hash"]}]
    out = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "insert.jsonl")
    assert out["platforms"][0]["status"] == "private_uploaded"
    assert out["platforms"][0]["public_action"] == "private_upload"
    assert out["platforms"][0]["remote_id"] == "vidNewUp001"
    uploads = [c for c in calls if c[0] == "upload"]
    assert [c[1] for c in uploads] == ["GET", "POST", "PUT"]
    assert uploads[0][2] == A.YOUTUBE_CHANNELS_MINE
    assert uploads[0][3] == A.YOUTUBE_PROMOTE_TIMEOUT_S
    assert uploads[1][2] == A.YOUTUBE_INIT
    assert uploads[1][3] == A.YOUTUBE_PROMOTE_TIMEOUT_S
    meta = json.loads(uploads[1][4].decode())
    assert meta["status"]["privacyStatus"] == "private"
    assert meta["status"]["containsSyntheticMedia"] is True
    assert "paidProductPlacementDetails" not in meta
    assert uploads[2][3] == A.YOUTUBE_UPLOAD_PUT_TIMEOUT_S
    assert uploads[2][4] == raw
    assert "part=status" not in uploads[2][2]
    assert "LM6jkXooWGc" not in (tmp_path / "insert.jsonl").read_text()
    assert REFRESH not in (tmp_path / "insert.jsonl").read_text()
    assert yls.token_path("MAIN").read_bytes() == before
    again = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "insert.jsonl")
    assert again["platforms"][0]["called"] is False
    assert [c[1] for c in calls if c[0] == "upload"].count("POST") == 1


def test_private_insert_disconnect_does_not_reinsert(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    calls = _insert_socket(monkeypatch, raw, put_error=True)
    item = {
        "id": "newclip02", "caption": "c", "title": "New clip", "ai_disclosure": True,
        "rights_ok": True, "status": "pending", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"],
    }
    manifest = P.build_manifest(item)
    row = manifest["platforms"][0]
    rows = [{"key": "youtube", "row_hash": row["row_hash"]}]
    first = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "insert.jsonl")
    second = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "insert.jsonl")
    assert first["platforms"][0]["status"] == "unknown"
    assert first["platforms"][0]["reason"] == "transport_uncertain"
    assert first["platforms"][0]["remote_id"] is None
    assert "upload_id" not in json.dumps(first)
    ledger = tmp_path / "insert.jsonl"
    assert stat.S_IMODE(os.stat(ledger).st_mode) == 0o600
    stored = ledger.read_text()
    assert SESSION in stored
    assert second["platforms"][0]["status"] == "private_uploaded"
    assert second["platforms"][0]["remote_id"] == "vidNewUp001"
    assert "upload_id" not in json.dumps(second)
    uploads = [c for c in calls if c[0] == "upload"]
    assert [c[1] for c in uploads].count("POST") == 1
    assert [c[1] for c in uploads].count("PUT") == 2
    status_put = uploads[-1]
    assert status_put[4] in (None, b"")
    assert status_put[3] == A.YOUTUBE_PROMOTE_TIMEOUT_S
    ranges = [value for key, value in status_put[5] if key.lower() == "content-range"]
    assert ranges == ["bytes */%d" % len(raw)]
    assert not any("search" in c[2] for c in uploads)
    assert "part=status" not in status_put[2]


def test_public_flag_default_never_reaches_the_transport(monkeypatch):
    monkeypatch.delenv(P.FLAG, raising=False)
    calls = _install_socket(monkeypatch)
    out = P.dispatch_platform({"id": "sample-07"}, {"key": "youtube", "public_action": "promote_existing", "will_dispatch": True}, ledger_path=None)
    assert out["reason"] == "public_publish_off"
    assert calls == []


def _new_item(iid):
    return {
        "id": iid, "caption": "c", "title": "New clip", "ai_disclosure": True,
        "rights_ok": True, "status": "pending", "video": "/samples/sample-a.mp4",
        "platforms": ["Clipped Motions YouTube"],
    }


def test_session_status_failure_does_not_reinsert(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    calls = _insert_socket(monkeypatch, raw, put_error=True, status_error=True)
    item = _new_item("newclip03")
    manifest = P.build_manifest(item)
    rows = [{"key": "youtube", "row_hash": manifest["platforms"][0]["row_hash"]}]
    ledger = tmp_path / "insert.jsonl"
    first = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    second = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert first["platforms"][0]["status"] == "unknown"
    assert second["platforms"][0]["status"] == "unknown"
    assert second["platforms"][0]["remote_id"] is None
    assert "upload_id" not in json.dumps(first) and "upload_id" not in json.dumps(second)
    uploads = [c for c in calls if c[0] == "upload"]
    assert [c[1] for c in uploads].count("POST") == 1
    stored = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert sum(1 for row in stored if row.get("remote_id") == SESSION or row.get("session_url") == SESSION) == 1


def test_session_status_does_not_bind_an_unproven_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    foreign = _upload_video(channel="UCaaaaaaaaaaaaaaaaaaaaaa", video_id="vidForeign1")
    calls = _insert_socket(monkeypatch, raw, put_error=True, status_video=foreign)
    item = _new_item("newclip04")
    manifest = P.build_manifest(item)
    rows = [{"key": "youtube", "row_hash": manifest["platforms"][0]["row_hash"]}]
    ledger = tmp_path / "insert.jsonl"
    P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    second = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert second["platforms"][0]["status"] == "unknown"
    assert second["platforms"][0]["remote_id"] is None
    text = ledger.read_text()
    assert "vidForeign1" not in text
    assert "private_uploaded" not in text
    assert [c[1] for c in calls if c[0] == "upload"].count("POST") == 1


def test_unknown_session_outside_the_allowlist_is_not_queried(tmp_path, monkeypatch):
    import post_idempotency as idem
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    calls = _insert_socket(monkeypatch, b"")
    item = _new_item("newclip05")
    manifest = P.build_manifest(item)
    row = manifest["platforms"][0]
    ledger = tmp_path / "insert.jsonl"
    idem.append_row({
        "key": idem.make_key(item["id"], "pub:youtube"),
        "job_id": item["id"],
        "platform": "pub:youtube",
        "status": "unknown",
        "remote_id": "https://evil.example/upload_id=secret-session",
        "upload_length": 4,
        "artifact_sha256": row.get("artifact_sha256"),
        "account_id": row.get("account_id"),
    }, path=ledger)
    out = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=[{"key": "youtube", "row_hash": row["row_hash"]}], ledger_path=ledger)
    assert out["platforms"][0]["status"] == "unknown"
    assert out["platforms"][0]["called"] is False
    assert "evil.example" not in json.dumps(out)
    assert "upload_id" not in json.dumps(out)
    assert [c for c in calls if c[0] == "upload"] == []
    assert stat.S_IMODE(os.stat(ledger).st_mode) == 0o600
    seen = []
    refused = A.youtube_session_status(
        "https://www.googleapis.com:8443/upload/youtube/v3/videos?upload_id=nope",
        token="mock-access-token", http=lambda *args: seen.append(args), file_size=4,
        expected_channel_id=MAIN,
    )
    assert refused["called"] is False
    assert seen == []


def test_upload_client_ignores_proxies_rejects_redirects_and_keeps_tls(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://proxy.invalid:9")
    lookups = []
    real_getproxies = urllib.request.getproxies

    def spy_getproxies():
        lookups.append(real_getproxies())
        return lookups[-1]

    monkeypatch.setattr(urllib.request, "getproxies", spy_getproxies)
    seen = []

    def https_open(self, req):
        seen.append((req.full_url, getattr(req, "timeout", None), req.data))
        if req.get_header("Content-range"):
            class Resume:
                status = 308
                code = 308
                msg = "Resume Incomplete"
                headers = EmailMessage()
                def info(self):
                    return self.headers
                def read(self):
                    return b""
                def close(self):
                    return None
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
            return Resume()
        if req.data == b"redirect":
            hdrs = EmailMessage()
            hdrs["Location"] = "https://evil.example/collect"
            class Redirected:
                status = 302
                code = 302
                msg = "Found"
                headers = hdrs
                def info(self):
                    return self.headers
                def read(self):
                    return b""
                def close(self):
                    return None
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
            return Redirected()
        class Resp:
            status = 200
            code = 200
            msg = "OK"
            def info(self):
                return EmailMessage()
            def get(self, key):
                if key == "Location" and req.get_method() == "POST":
                    return SESSION
                return None
            def read(self):
                if req.full_url == A.YOUTUBE_CHANNELS_MINE:
                    return json.dumps({"items": [{"id": MAIN}]}).encode()
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        Resp.headers = Resp()
        return Resp()

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)
    auth = {"Authorization": "Bearer mock-access-token"}
    mine = A.youtube_insert_http("GET", A.YOUTUBE_CHANNELS_MINE, auth, None)
    assert mine["json"]["items"][0]["id"] == MAIN
    init = A.youtube_insert_http("POST", A.YOUTUBE_INIT, auth, b"{}")
    assert init["headers"]["Location"] == SESSION
    uploaded = A.youtube_insert_http("PUT", SESSION, auth, b"video-bytes")
    assert uploaded["status"] == 200
    assert [row[0] for row in seen] == [A.YOUTUBE_CHANNELS_MINE, A.YOUTUBE_INIT, SESSION]
    assert [row[1] for row in seen] == [
        A.YOUTUBE_PROMOTE_TIMEOUT_S,
        A.YOUTUBE_PROMOTE_TIMEOUT_S,
        A.YOUTUBE_UPLOAD_PUT_TIMEOUT_S,
    ]
    assert seen[2][2] == b"video-bytes"
    assert lookups == []
    assert all("proxy.invalid" not in row[0] for row in seen)
    opener = A.youtube_promote_opener()
    proxies = [dict(h.proxies) for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert proxies == [{}]
    contexts = [c for c in (getattr(h, "_context", None) for h in opener.handlers) if isinstance(c, ssl.SSLContext)]
    assert contexts
    assert all(c.verify_mode == ssl.CERT_REQUIRED and c.check_hostname for c in contexts)
    try:
        A.youtube_insert_http("PUT", "https://www.googleapis.com:8443/upload/youtube/v3/videos?upload_id=nope", auth, b"x")
        assert False
    except URLError as exc:
        assert "youtube_destination_rejected" in str(exc.reason)
    assert len(seen) == 3
    try:
        A.youtube_insert_http("PUT", SESSION, auth, b"redirect")
        assert False
    except URLError as exc:
        assert "redirect_rejected" in str(exc.reason)
    assert all("evil.example" not in row[0] for row in seen)
    resumed = A.youtube_insert_http("PUT", SESSION, {"Content-Range": "bytes */4", "Content-Length": "0"}, b"")
    assert resumed["status"] == 308
    assert seen[-1][1] == A.YOUTUBE_PROMOTE_TIMEOUT_S
    assert seen[-1][2] in (None, b"")


def _rows_for(item):
    manifest = P.build_manifest(item)
    return manifest, [{"key": "youtube", "row_hash": manifest["platforms"][0]["row_hash"]}]


def test_channel_preflight_timeout_is_retryable_and_sends_no_insert(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    calls = _insert_socket(monkeypatch, raw, preflight_failures=1)
    item = _new_item("newclip06")
    manifest, rows = _rows_for(item)
    assert "status query" in manifest["platforms"][0]["line"]
    assert "does not insert the file again" in manifest["platforms"][0]["line"]
    ledger = tmp_path / "insert.jsonl"
    first = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    uploads = [c for c in calls if c[0] == "upload"]
    assert [c[1] for c in uploads] == ["GET"]
    assert first["platforms"][0]["called"] is False
    assert first["platforms"][0]["reason"] == "youtube_channel_preflight_failed"
    stored = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert stored[-1]["status"] == "failed"
    assert all(row.get("status") != "unknown" for row in stored)
    second = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert second["platforms"][0]["status"] == "private_uploaded"
    uploads = [c for c in calls if c[0] == "upload"]
    assert [c[1] for c in uploads] == ["GET", "GET", "POST", "PUT"]


def test_incomplete_session_is_recorded_and_not_replaced(tmp_path, monkeypatch):
    import post_idempotency as idem
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    calls = _insert_socket(monkeypatch, raw, put_error=True, status_308=True)
    item = _new_item("newclip07")
    manifest, rows = _rows_for(item)
    ledger = tmp_path / "insert.jsonl"
    P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    second = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert second["platforms"][0]["status"] == "unknown"
    assert second["platforms"][0]["status_query"] is True
    assert second["platforms"][0]["remote_id"] is None
    assert "upload_id" not in json.dumps(second)
    stored = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert stored[-1]["status"] == "unknown"
    assert stored[-1]["session_observation"] == "upload_incomplete"
    assert stored[-1]["remote_id"] == SESSION
    ok, err = idem.unstick(item["id"], "pub:youtube", path=ledger)
    assert ok is False
    assert err["error"] == "refuse_upload_evidence"
    assert "remote_id" not in err
    assert SESSION not in json.dumps(err)
    third = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert third["platforms"][0]["status"] == "unknown"
    uploads = [c for c in calls if c[0] == "upload"]
    assert [c[1] for c in uploads].count("POST") == 1
    assert [c[1] for c in uploads].count("PUT") == 3


def test_upload_refuses_without_an_object_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    monkeypatch.setattr("tools.private_proof._lock_objects", lambda: (None, None))
    calls = _insert_socket(monkeypatch, b"")
    item = _new_item("newclip08")
    manifest, rows = _rows_for(item)
    out = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "insert.jsonl")
    assert out["platforms"][0]["called"] is False
    assert out["platforms"][0]["reason"] == "youtube_object_lock_unavailable"
    assert [c for c in calls if c[0] == "upload"] == []
    assert not (tmp_path / "insert.jsonl").exists()


def test_missing_data_dir_is_created_and_locked_before_upload(tmp_path, monkeypatch):
    missing = tmp_path / "fresh-data"
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(missing))
    monkeypatch.setenv(P.FLAG, "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    calls = _insert_socket(monkeypatch, b"")
    item = _new_item("newclip09")
    manifest, rows = _rows_for(item)
    ledger = tmp_path / "insert.jsonl"
    out = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
    assert out["platforms"][0]["status"] == "private_uploaded"
    lock = missing / ".youtube-object.lock"
    assert lock.is_file()
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert missing.is_dir()
    assert stat.S_IMODE(missing.stat().st_mode) & 0o077 == 0
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(blocker / "child"))
    calls.clear()
    refused = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=tmp_path / "blocked.jsonl")
    assert refused["platforms"][0]["reason"] == "data_dir_missing"
    assert refused["platforms"][0]["called"] is False
    assert [c for c in calls if c[0] == "upload"] == []


def _unstick_via_endpoint(monkeypatch, ledger, job_id):
    import server
    import post_idempotency as idem
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "true")
    monkeypatch.setattr(idem, "LEDGER_PATH", ledger)
    data = ledger.parent
    state = data / "state.json"
    approvals = data / "approvals.json"
    events = data / "events.json"
    approvals.write_text(json.dumps({"version": 1, "items": []}) + "\n")
    events.write_text(json.dumps({"version": 1, "events": []}) + "\n")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state, approvals_path=approvals, events_path=events))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    token = (data / "hub-token").read_text().strip()
    raw = json.dumps({"job_id": job_id, "platform": "pub:youtube"}).encode()
    import socket
    host, port = httpd.server_address
    raw_req = (
        "POST /api/post-ledger/unstick HTTP/1.1\r\n"
        "Host: %s:%s\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: %d\r\n"
        "X-Hub-Token: %s\r\n"
        "Connection: close\r\n\r\n"
    ) % (host, port, len(raw), token)
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.sendall(raw_req.encode() + raw)
        chunks = []
        while True:
            piece = sock.recv(4096)
            if not piece:
                break
            chunks.append(piece)
        sock.close()
        blob = b"".join(chunks)
        Path("/tmp/unstick-http.txt").write_bytes(blob)
        head, _, payload = blob.partition(b"\r\n\r\n")
        status_line = head.split(b"\r\n", 1)[0].decode()
        code = int(status_line.split()[1])
        body = payload.decode()
    finally:
        httpd.shutdown()
    return code, body


def _assert_no_session_leak(body, session):
    assert session not in body
    assert "upload_id" not in body
    assert "remote_id" not in body
    assert "googleapis.com" not in body


def test_unstick_cannot_reinsert_or_reveal_a_session(tmp_path, monkeypatch):
    import post_idempotency as idem
    monkeypatch.setenv("CLIPPING_HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(P.FLAG, "true")
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "true")
    _oauth(monkeypatch, tmp_path / "oauth")
    raw = (ROOT / "tests" / "fixtures" / "samples" / "sample-a.mp4").read_bytes()
    wrong = {
        "id": "vidWrongCh1",
        "snippet": {"channelId": "UCaaaaaaaaaaaaaaaaaaaaaa"},
        "status": {"privacyStatus": "private", "containsSyntheticMedia": True},
    }
    public = {
        "id": "vidPublic01",
        "snippet": {"channelId": MAIN},
        "status": {"privacyStatus": "public", "containsSyntheticMedia": True},
    }
    omitted = {
        "id": "vidEchoOmit1",
        "snippet": {"channelId": MAIN},
        "status": {"privacyStatus": "private"},
    }

    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(tmp_path / "post_ledger.jsonl"))

    def _run(iid, ledger_name, **socket_kwargs):
        ledger = tmp_path / ledger_name
        calls = _insert_socket(monkeypatch, raw, **socket_kwargs)
        item = _new_item(iid)
        manifest, rows = _rows_for(item)
        first = P.dispatch_item(item, manifest["manifest_hash"], platform_rows=rows, ledger_path=ledger)
        return calls, item, manifest, rows, ledger, first

    calls, item, manifest, rows, ledger, first = _run(
        "newclip10", "echo.jsonl", put_json=omitted,
    )
    assert first["platforms"][0]["status"] == "unknown"
    assert first["platforms"][0]["reason"] == "youtube_synthetic_echo_omitted"
    stored = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert stored[-1]["video_id"] == "vidEchoOmit1"
    assert stored[-1]["session_url"] == SESSION
    code, body = _unstick_via_endpoint(monkeypatch, ledger, item["id"])
    assert code == 400, (code, body)
    assert "refuse_upload_evidence" in body
    _assert_no_session_leak(body, SESSION)
    assert SESSION not in json.dumps(first)
    fresh, fresh_rows = _rows_for(item)
    again = P.dispatch_item(item, fresh["manifest_hash"], platform_rows=fresh_rows, ledger_path=ledger)
    assert again.get("platforms"), again
    assert [c[1] for c in calls if c[0] == "upload"].count("POST") == 1

    calls, item, manifest, rows, ledger, first = _run(
        "newclip11", "channel.jsonl", put_json=wrong,
    )
    assert first["platforms"][0]["status"] == "create_error"
    assert first["platforms"][0]["reason"] == "youtube_channel_mismatch"
    stored = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert stored[-1]["video_id"] == "vidWrongCh1"
    assert stored[-1]["session_url"] == SESSION
    code, body = _unstick_via_endpoint(monkeypatch, ledger, item["id"])
    assert code == 400 and "refuse_upload_evidence" in body
    _assert_no_session_leak(body, SESSION)
    idem.append_row({
        "key": idem.make_key(item["id"], "pub:youtube"),
        "job_id": item["id"], "platform": "pub:youtube", "status": "failed",
        "artifact_sha256": stored[-1].get("artifact_sha256"),
        "account_id": stored[-1].get("account_id"),
        "error": "operator_unstick",
    }, path=ledger)
    fresh, fresh_rows = _rows_for(item)
    again = P.dispatch_item(item, fresh["manifest_hash"], platform_rows=fresh_rows, ledger_path=ledger)
    assert again.get("platforms"), again
    assert again["platforms"][0]["called"] is False
    assert [c[1] for c in calls if c[0] == "upload"].count("POST") == 1

    calls, item, manifest, rows, ledger, first = _run(
        "newclip12", "privacy.jsonl", put_json=public,
    )
    assert first["platforms"][0]["reason"] == "youtube_privacy_not_private"
    stored = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert stored[-1]["video_id"] == "vidPublic01"
    code, body = _unstick_via_endpoint(monkeypatch, ledger, item["id"])
    assert code == 400 and "refuse_upload_evidence" in body
    _assert_no_session_leak(body, SESSION)
    fresh, fresh_rows = _rows_for(item)
    again = P.dispatch_item(item, fresh["manifest_hash"], platform_rows=fresh_rows, ledger_path=ledger)
    assert again.get("platforms"), again
    assert [c[1] for c in calls if c[0] == "upload"].count("POST") == 1

    calls, item, manifest, rows, ledger, first = _run(
        "newclip13", "noid.jsonl", post_error=True,
    )
    assert first["platforms"][0]["status"] == "unknown"
    assert first["platforms"][0]["remote_id"] is None
    code, body = _unstick_via_endpoint(monkeypatch, ledger, item["id"])
    assert code == 400 and "refuse_unresolved_youtube_object" in body
    _assert_no_session_leak(body, SESSION)
    fresh, fresh_rows = _rows_for(item)
    again = P.dispatch_item(item, fresh["manifest_hash"], platform_rows=fresh_rows, ledger_path=ledger)
    assert again.get("platforms"), again
    assert again["platforms"][0]["called"] is False
    assert [c[1] for c in calls if c[0] == "upload"].count("POST") == 1

    ledger = tmp_path / "stale.jsonl"
    calls = _insert_socket(monkeypatch, raw)
    item = _new_item("newclip14")
    manifest, rows = _rows_for(item)
    row = manifest["platforms"][0]
    idem.append_row({
        "key": idem.make_key(item["id"], "pub:youtube"),
        "job_id": item["id"], "platform": "pub:youtube", "status": "in_flight",
        "artifact_sha256": row.get("artifact_sha256"),
        "account_id": row.get("account_id"),
        "at": "2020-01-01T00:00:00+0000",
    }, path=ledger)
    code, body = _unstick_via_endpoint(monkeypatch, ledger, item["id"])
    assert code == 400 and "refuse_unresolved_youtube_object" in body
    _assert_no_session_leak(body, SESSION)
    fresh, fresh_rows = _rows_for(item)
    again = P.dispatch_item(item, fresh["manifest_hash"], platform_rows=fresh_rows, ledger_path=ledger)
    assert again.get("platforms"), again
    assert again["platforms"][0]["called"] is False
    assert [c for c in calls if c[0] == "upload"] == []

    calls, item, manifest, rows, ledger, first = _run(
        "newclip15", "reconcile.jsonl", put_error=True, status_video=omitted,
    )
    fresh, fresh_rows = _rows_for(item)
    second = P.dispatch_item(item, fresh["manifest_hash"], platform_rows=fresh_rows, ledger_path=ledger)
    assert second["platforms"][0]["status"] == "unknown"
    assert second["platforms"][0]["reason"] == "youtube_synthetic_echo_omitted"
    stored = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert stored[-1]["video_id"] == "vidEchoOmit1"
    assert stored[-1]["session_url"] == SESSION
    code, body = _unstick_via_endpoint(monkeypatch, ledger, item["id"])
    assert code == 400 and "refuse_upload_evidence" in body
    _assert_no_session_leak(body, SESSION)
    fresh, fresh_rows = _rows_for(item)
    third = P.dispatch_item(item, fresh["manifest_hash"], platform_rows=fresh_rows, ledger_path=ledger)
    assert third.get("platforms"), third
    assert [c[1] for c in calls if c[0] == "upload"].count("POST") == 1
