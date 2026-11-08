"""GET-merge-PUT preserves other status fields; re-private + may-be-public alert."""
from __future__ import annotations

import youtube_label_step as Y

VID = "vidMerge001"  # 11
VID_Z = "vidZxxxxx01"
VID_ONE = "vidOne00001"  # 11


def test_update_video_status_get_merge_put_keeps_other_fields():
    calls = []

    def http_json(method, url, headers, body):
        calls.append((method, body))
        if method == "GET":
            return {"items": [{"status": {
                "privacyStatus": "private",
                "containsSyntheticMedia": False,
                "embeddable": True,
                "license": "youtube",
                "selfDeclaredMadeForKids": False,
            }}]}
        return {"id": body["id"], "status": body["status"]}

    Y.update_video_status(
        VID, "tok",
        {"containsSyntheticMedia": True},
        http_json=http_json,
    )
    puts = [c for c in calls if c[0] == "PUT"]
    assert len(puts) == 1
    status = puts[0][1]["status"]
    assert status["containsSyntheticMedia"] is True
    assert status["embeddable"] is True
    assert status["license"] == "youtube"
    assert status["selfDeclaredMadeForKids"] is False
    assert status["privacyStatus"] == "private"


def test_reprivate_on_confirm_fail_then_alert_if_unverified(tmp_path, monkeypatch):
    """GET sequence after Deadbolt recut (extra GET before set_contains_synthetic):
    1 status0, 2 merge-synth, 3 confirm-synth, 4 merge-public, 5 confirm-public (fail),
    6 merge-repriv, 7 verify-repriv (fail) → MAY_BE_PUBLIC.
    """
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    cid = tmp_path / "cid"; cid.write_text("c")
    sec = tmp_path / "sec"; sec.write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", cid)
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", sec)

    phase = {"n": 0}
    alerts = []

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        if method == "GET":
            phase["n"] += 1
            n = phase["n"]
            # 1 status0, 2 merge synth, 3 confirm synth — private+synthetic
            if n <= 3:
                return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "embeddable": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            # 4 merge public GET still private (merge)
            if n == 4:
                return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            # 5 confirm after public — neither public nor synthetic
            if n == 5:
                return {"items": [{"status": {"privacyStatus": "unlisted", "containsSyntheticMedia": False, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            # 6 merge repriv + 7 verify — still not private
            return {"items": [{"status": {"privacyStatus": "unlisted", "containsSyntheticMedia": False, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        return {"id": (body or {}).get("id")}

    def push(title, body, key=None):
        alerts.append(title)
        return True

    item = {"id": "m1", "title": "Tip", "route_target": "MAIN", "ai_disclosure": True}
    out = Y.run_after_approve(
        item, env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        opus_fn=lambda i: {"video_id": VID_Z},
        push_fn=push,
        ledger_path=tmp_path / "led.jsonl",
    )
    assert out["ok"] is False
    assert "MAY_BE_PUBLIC" in (out["error"] or "")
    urgent = [a for a in alerts if "may be PUBLIC" in a or "PUBLIC" in a]
    left_private = [a for a in alerts if "left private" in a.lower()]
    assert urgent, alerts
    assert not left_private, "must not also send left-private after may-be-public: %r" % (alerts,)


def test_reprivate_success_raises_reprivated(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    (tmp_path / "cid").write_text("c")
    (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")

    gets = {"n": 0}

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        if method == "GET":
            gets["n"] += 1
            n = gets["n"]
            # 1 status0, 2 merge synth, 3 confirm synth
            if n <= 3:
                return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            # 4 merge public
            if n == 4:
                return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            # 5 confirm public fails (still private, synthetic dropped)
            if n == 5:
                return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": False, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            # 6 merge repriv + 7 verify repriv ok
            return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        return {}

    out = Y.run_after_approve(
        {"id": "m2", "title": "T", "route_target": "MAIN"},
        env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        opus_fn=lambda i: {"video_id": "vxxxxxxxxxx"},
        push_fn=lambda *a, **k: True,
        ledger_path=tmp_path / "led.jsonl",
    )
    assert out["ok"] is False
    assert "reprivated" in (out["error"] or "")


def test_may_be_public_skips_left_private_alert(tmp_path, monkeypatch):
    """Deadbolt LOW: after URGENT may-be-PUBLIC, generic notify_fail must not fire."""
    monkeypatch.setattr(Y, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(Y.FLAG, "true")
    Y.save_token("MAIN", {"refresh_token": "rt", "access_token": "a", "bound_channel_id": "UCgMuVjQmB9WvZtSz4e23THw", "bound_channel_title": "Clipped Motions"})
    (tmp_path / "cid").write_text("c")
    (tmp_path / "sec").write_text("s")
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "cid")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "sec")

    gets = {"n": 0}
    alerts = []

    def http_post(url, body):
        return {"access_token": "access-new"}

    def http_json(method, url, headers, body):
        if method == "GET":
            gets["n"] += 1
            n = gets["n"]
            if n <= 3:
                return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            if n == 4:
                return {"items": [{"status": {"privacyStatus": "private", "containsSyntheticMedia": True, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
            # confirm + repriv verify fail
            return {"items": [{"status": {"privacyStatus": "unlisted", "containsSyntheticMedia": False, "channelId": "UCgMuVjQmB9WvZtSz4e23THw"}}]}
        return {}

    def push(title, body, key=None):
        alerts.append(title)
        return True

    out = Y.run_after_approve(
        {"id": "one-alert", "title": "Tip", "route_target": "MAIN", "ai_disclosure": True},
        env={Y.FLAG: "true"},
        http_post=http_post, http_json=http_json,
        opus_fn=lambda i: {"video_id": VID_ONE},
        push_fn=push,
        ledger_path=tmp_path / "led.jsonl",
    )
    assert out["ok"] is False
    assert "MAY_BE_PUBLIC" in (out["error"] or "")
    assert len(alerts) == 1, alerts
    assert "may be PUBLIC" in alerts[0] or "PUBLIC" in alerts[0]
    assert all("left private" not in a.lower() for a in alerts)
