"""Opus private create-post: postId match, URL hardening, targets-only accounts, idempotency."""
from __future__ import annotations

import youtube_label_step as Y
import schedule_hook as S
import post_idempotency as idem

TARGETS = {
    "version": 1,
    "poster": "opus",
    "targets": {
        "MAIN": {
            "name": "Clipped Motions",
            "handle": "@clippedmotions",
            "yt": S.MAIN_YOUTUBE_CHANNEL_ID,
            "opus_post_account_id": "opus-main-acct",
            "opus_sub_account_id": "opus-main-sub",
            "whop": "w1",
        },
        "PAID": {
            "name": "Paid",
            "handle": "@paid",
            "yt": "UC8TrAT8V-HacqYlqqqzIQKg",
            "opus_post_account_id": "opus-paid-acct",
            "whop": "w2",
        },
    },
}

# Valid 11-char YouTube ids
VID_A = "abcDEF12345"
VID_B = "xyz98765432"
VID_SHORT = "shortId9999"
VID_LIST = "fromList001"
VID_EXPL = "explicitV01"


def test_youtube_id_from_url_https_allowlist_and_id_shape():
    assert Y.youtube_id_from_url(f"https://www.youtube.com/watch?v={VID_A}") == VID_A
    assert Y.youtube_id_from_url(f"https://youtu.be/{VID_B}") == VID_B
    assert Y.youtube_id_from_url(f"https://m.youtube.com/shorts/{VID_SHORT}") == VID_SHORT
    assert Y.youtube_id_from_url(f"https://youtube.com/embed/{VID_A}") == VID_A
    # http rejected
    assert Y.youtube_id_from_url(f"http://www.youtube.com/watch?v={VID_A}") is None
    # host not allowlisted
    assert Y.youtube_id_from_url(f"https://youtube-nocookie.com/watch?v={VID_A}") is None
    assert Y.youtube_id_from_url(f"https://evil.youtube.com.attacker/watch?v={VID_A}") is None
    # userinfo rejected
    assert Y.youtube_id_from_url(f"https://user:pass@www.youtube.com/watch?v={VID_A}") is None
    assert Y.youtube_id_from_url(f"https://user@youtu.be/{VID_A}") is None
    # bad id length / charset
    assert Y.youtube_id_from_url("https://www.youtube.com/watch?v=short") is None
    assert Y.youtube_id_from_url("https://www.youtube.com/watch?v=toolongvideoid1") is None
    assert Y.youtube_id_from_url("https://www.youtube.com/watch?v=bad!chars!!") is None


def test_explicit_video_id_must_match_shape():
    assert Y.extract_youtube_video_id({"data": {"videoId": VID_EXPL}}) == VID_EXPL
    assert Y.extract_youtube_video_id({"data": {"videoId": "too-short"}}) is None
    assert Y.extract_youtube_video_id({"data": {"videoId": "waytoolongvid"}}) is None
    # create response with postId only — no URL scan
    assert Y.extract_youtube_video_id({"data": {"postId": "only-post"}}) is None


def test_match_video_by_post_id_not_first_url():
    """Wrong first URL must not win; matching postId row without id → fail closed."""
    payload = {
        "items": [
            {
                "postId": "other-post",
                "postAccountId": "opus-main-acct",
                "post_url": f"https://www.youtube.com/watch?v={VID_A}",
            },
            {
                "postId": "post-task-1",
                "postAccountId": "opus-main-acct",
                "post_url": f"https://www.youtube.com/watch?v={VID_LIST}",
            },
        ]
    }
    assert Y.extract_youtube_video_id_for_post(
        payload, "post-task-1", post_account_id="opus-main-acct"
    ) == VID_LIST
    # Account mismatch skips the row even with matching postId
    assert Y.extract_youtube_video_id_for_post(
        payload, "post-task-1", post_account_id="other-acct"
    ) is None
    # Matching postId, no valid id → None (fail closed)
    bad = {"items": [{"postId": "post-task-1", "post_url": "https://example.com/not-yt"}]}
    assert Y.extract_youtube_video_id_for_post(bad, "post-task-1") is None
    # No matching postId → None (do not fall back to first URL)
    assert Y.extract_youtube_video_id_for_post(payload, "missing") is None


def test_opus_upload_private_posts_private_to_routed_account(tmp_path):
    calls = []
    ledger = tmp_path / "ledger.jsonl"

    def http_json(method, url, headers, body):
        calls.append((method, url, body))
        if method == "POST":
            assert body["postAccountId"] == "opus-main-acct"
            assert body["subAccountId"] == "opus-main-sub"
            assert body["projectId"] == "Pproj1"
            assert body["clipId"] == "Cclip1"
            assert body["postDetail"]["title"] == "Keep Title"
            assert body["postDetail"]["custom"]["description"] == "Keep caption"
            assert body["postDetail"]["custom"]["privacy"] == "private"
            assert "clientRequestId" in body
            return {"data": {"postId": "post-task-1"}}
        # GET list — first row is a DIFFERENT post; must match post-task-1
        return {
            "items": [
                {
                    "postId": "older-post",
                    "postAccountId": "opus-main-acct",
                    "post_url": f"https://www.youtube.com/watch?v={VID_A}",
                    "status": "posted",
                },
                {
                    "postId": "post-task-1",
                    "postAccountId": "opus-main-acct",
                    "post_url": f"https://www.youtube.com/watch?v={VID_LIST}",
                    "status": "posted",
                },
            ]
        }

    item = {
        "id": "a1",
        "title": "Keep Title",
        "caption": "Keep caption",
        "projectId": "Pproj1",
        "clipId": "Pproj1.Cclip1",
        "ai_disclosure": True,
        "platforms": ["Clipped Motions YouTube", "TikTok Business"],
        # Poison fields — must be ignored
        "opus_post_account_id": "evil-from-item",
        "opus_sub_account_id": "evil-sub",
        "subAccountId": "evil-sub-2",
    }
    out = Y.opus_upload_private(
        item, targets=TARGETS, http_json=http_json, token="test-token", ledger_path=ledger,
    )
    assert out["video_id"] == VID_LIST  # not VID_A
    assert "privacy" not in out  # no hard-coded privacy claim
    assert out["post_account_id"] == "opus-main-acct"
    assert out["post_id"] == "post-task-1"
    row = idem.lookup("a1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert row["status"] == "done"
    assert row["opus_post_id"] == "post-task-1"


def test_item_opus_fields_ignored_for_account_ids(tmp_path):
    bodies = []

    def http_json(method, url, headers, body):
        if method == "POST":
            bodies.append(body)
            return {"data": {"postId": "p1", "videoId": VID_EXPL}}
        return {}

    item = {
        "id": "ign1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C",
        "opus_post_account_id": "from-item-must-ignore",
        "platforms": ["Clipped Motions YouTube"],
    }
    out = Y.opus_upload_private(
        item, targets=TARGETS, http_json=http_json, token="t", ledger_path=tmp_path / "l.jsonl",
    )
    assert bodies[0]["postAccountId"] == "opus-main-acct"
    assert out["post_account_id"] == "opus-main-acct"


def test_create_post_idempotent_no_double_on_retry(tmp_path):
    posts = {"n": 0}

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            return {"data": {"postId": "post-once"}}
        return {
            "items": [{
                "postId": "post-once",
                "postAccountId": "opus-main-acct",
                "post_url": f"https://www.youtube.com/watch?v={VID_B}",
            }]
        }

    item = {
        "id": "idem1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C",
        "platforms": ["Clipped Motions YouTube"],
    }
    ledger = tmp_path / "led.jsonl"
    r1 = Y.opus_upload_private(item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger)
    r2 = Y.opus_upload_private(item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger)
    assert posts["n"] == 1
    assert r1["video_id"] == VID_B
    assert r2["video_id"] == VID_B
    assert r2["post_id"] == "post-once"


def test_timeout_marks_timeout_pending_no_repost(tmp_path):
    posts = {"n": 0}

    def http_json(method, url, headers, body):
        if method == "POST":
            posts["n"] += 1
            raise TimeoutError("timed out")
        return {"items": []}

    item = {
        "id": "to1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C",
        "platforms": ["Clipped Motions YouTube"],
    }
    ledger = tmp_path / "led.jsonl"
    try:
        Y.opus_upload_private(item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger)
        assert False, "expected raise"
    except RuntimeError as e:
        assert "timeout_pending" in str(e)
    row = idem.lookup("to1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)
    assert row["status"] == "timeout_pending"
    assert posts["n"] == 1
    # Second call reconciles (no match) — must not POST again
    try:
        Y.opus_upload_private(item, targets=TARGETS, http_json=http_json, token="t", ledger_path=ledger)
        assert False
    except RuntimeError as e:
        assert "reconcile_waiting" in str(e) or "stuck" in str(e)
    assert posts["n"] == 1
    assert idem.lookup("to1", Y.CREATE_IDEMPOTENCY_PLATFORM, path=ledger)["status"] == "timeout_pending"


def test_opus_no_video_id_for_matching_post_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(S, "load_targets", lambda path=None: TARGETS)
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    (tmp_path / "cid").write_text("c")
    (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    tok = tmp_path / "opus-token"
    tok.write_text("opus-test-token")
    monkeypatch.setattr(Y, "OPUS_TOKEN_FILE", tok)

    alerts = []

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        if "post-tasks" in url and method == "POST":
            return {"data": {"postId": "p1"}}
        if method == "GET" and "post-tasks" in url:
            # Matching postId but no valid youtube id
            return {"items": [{"postId": "p1", "postAccountId": "opus-main-acct"}]}
        return {}

    item = {
        "id": "a2", "title": "T", "caption": "C", "route_target": "MAIN",
        "projectId": "P1", "clipId": "C1", "ai_disclosure": True,
        "platforms": ["Clipped Motions YouTube"],
    }
    out = Y.run_after_approve(
        item, env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        push_fn=lambda t, b, key=None: alerts.append(t) or True,
        ledger_path=tmp_path / "a2_ledger.jsonl",
    )
    assert out["ok"] is False
    assert "opus_no_video_id" in (out["error"] or "")


def test_refuse_label_when_video_already_public(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(S, "load_targets", lambda path=None: TARGETS)
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    (tmp_path / "cid").write_text("c"); (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    monkeypatch.setattr(Y, "OPUS_TOKEN_FILE", tmp_path / "ot")
    (tmp_path / "ot").write_text("tok")

    puts = []

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        if "post-tasks" in url and method == "POST":
            return {"data": {"postId": "p-pub", "videoId": VID_A}}
        if "post-tasks" in url and method == "GET":
            return {"items": [{
                "postId": "p-pub", "postAccountId": "opus-main-acct",
                "post_url": f"https://www.youtube.com/watch?v={VID_A}",
            }]}
        if "googleapis.com/youtube" in url and method == "GET":
            return {"items": [{"id": VID_A, "status": {"privacyStatus": "public", "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        if method == "PUT":
            puts.append(body)
            return {}
        return {}

    alerts = []
    item = {
        "id": "pub1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C", "ai_disclosure": True,
        "platforms": ["Clipped Motions YouTube"],
    }
    out = Y.run_after_approve(
        item, env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        push_fn=lambda t, b, key=None: alerts.append((t, b)) or True,
        ledger_path=tmp_path / "pub_ledger.jsonl",
    )
    assert out["ok"] is False
    assert "refuse_mutate_already_public" in (out["error"] or "")
    assert not puts  # never PUT / never privatize a public video
    # Must NOT claim "left private" (video is public)
    assert not any("left private" in (t + b).lower() for t, b in alerts)


def test_left_private_alert_only_when_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(S, "load_targets", lambda path=None: TARGETS)
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    (tmp_path / "cid").write_text("c"); (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    monkeypatch.setattr(Y, "OPUS_TOKEN_FILE", tmp_path / "ot")
    (tmp_path / "ot").write_text("tok")

    alerts = []

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        if "post-tasks" in url and method == "POST":
            return {"data": {"postId": "p-priv", "videoId": VID_B}}
        if "post-tasks" in url and method == "GET":
            return {"items": [{
                "postId": "p-priv", "postAccountId": "opus-main-acct",
                "post_url": f"https://www.youtube.com/watch?v={VID_B}",
            }]}
        if "googleapis.com/youtube" in url and method == "GET":
            # private on first GET; synthetic never sticks → fail after label attempt
            return {"items": [{"id": VID_B, "status": {
                "privacyStatus": "private",
                "containsSyntheticMedia": False,
            }}]}
        if method == "PUT":
            return {}
        return {}

    item = {
        "id": "priv1", "title": "T", "caption": "C",
        "projectId": "P", "clipId": "C", "ai_disclosure": True,
        "platforms": ["Clipped Motions YouTube"],
    }
    out = Y.run_after_approve(
        item, env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        push_fn=lambda t, b, key=None: alerts.append(t) or True,
        ledger_path=tmp_path / "priv_ledger.jsonl",
    )
    assert out["ok"] is False
    assert any("left private" in a.lower() for a in alerts)


def test_storyblocks_paid_label_step_never_uploads(tmp_path, monkeypatch):
    monkeypatch.setenv(Y.FLAG, "true")
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    Y.save_token("PAID", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UC8TrAT8V-HacqYlqqqzIQKg", "bound_channel_title": "Clips"})
    (tmp_path / "cid").write_text("c"); (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")
    monkeypatch.setattr(S, "load_targets", lambda path=None: TARGETS)

    called = []

    def boom(item):
        called.append(1)
        raise RuntimeError("should_not_run")

    alerts = []
    item = {
        "id": "sb1", "title": "T", "caption": "C",
        "license": {"source": "storyblocks"}, "is_ad": True,
        "projectId": "P", "clipId": "C",
        "platforms": ["TikTok Business"], "ai_disclosure": True,
    }
    out = Y.run_after_approve(
        item, env={Y.FLAG: "true"},
        opus_fn=boom,
        push_fn=lambda t, b, key=None: alerts.append(t) or True,
        http_post=lambda *a, **k: {"access_token": "x"},
    )
    assert out["ok"] is False
    assert str(out.get("error") or "").startswith("route_blocked:storyblocks_main_only")
    assert called == []


def test_title_caption_unchanged_in_opus_body(tmp_path):
    bodies = []

    def http_json(method, url, headers, body):
        if method == "POST":
            bodies.append(body)
            return {"data": {"postId": "p", "videoId": VID_EXPL}}
        return {}

    item = {
        "id": "a3", "title": "Exact Title", "caption": "Exact caption text",
        "projectId": "P", "clipId": "C",
        "platforms": ["Clipped Motions YouTube"],
    }
    out = Y.opus_upload_private(
        item, targets=TARGETS, http_json=http_json, token="t", ledger_path=tmp_path / "l.jsonl",
    )
    assert out["video_id"] == VID_EXPL
    assert bodies[0]["postDetail"]["title"] == "Exact Title"
    assert bodies[0]["postDetail"]["custom"]["description"] == "Exact caption text"
    assert "AI" not in bodies[0]["postDetail"]["title"]
