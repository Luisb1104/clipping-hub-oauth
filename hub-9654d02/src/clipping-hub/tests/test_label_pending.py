"""ai_disclosure → privacy=private, status=label_pending, Label pending chip."""
from pathlib import Path
import json
import schedule_hook as S
import server as srv

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "app.js").read_text()


def test_job_ai_on_is_private_label_pending():
    rec = S.job_record({
        "id": "lp1", "caption": "Watch the full episode", "title": "Tip cut",
        "status": "approved", "ai_disclosure": True,
    })
    assert rec["privacy"] == "private"
    assert rec["status"] == "label_pending"
    assert rec["ai_disclosure"] is True
    assert "AI" not in rec["caption"] and "ai_disclosure" not in rec["caption"]
    assert "AI" not in rec["title"]


def test_job_ai_off_stays_queued_public():
    rec = S.job_record({
        "id": "lp2", "caption": "plain", "title": "t",
        "status": "approved", "ai_disclosure": False,
    })
    assert rec["privacy"] == "public"
    assert rec["status"] == "queued"


def test_decide_approved_ai_becomes_label_pending():
    data = {"version": 1, "items": [
        srv._clean_item({
            "id": "lp3", "video": "/samples/a.mp4", "caption": "c", "title": "t",
            "ai_disclosure": True, "status": "pending",
            "platforms": ["TikTok Business"],
        })
    ]}
    data, item, changed = srv.decide_approval(data, {"op": "decide", "id": "lp3", "status": "approved"})
    assert changed is True
    assert item["status"] == "label_pending"
    assert item["privacy"] == "private"


def test_tt_ig_push_success_marks_done_no_hub_tap():
    import youtube_label_step as Y
    item = {
        "id": "lp4", "title": "t", "status": "label_pending", "privacy": "private",
        "ai_disclosure": True, "youtube_label_set": True,
    }
    pushed = Y.notify_tt_ig_labels(item, push_fn=lambda *a, **k: True)
    Y.apply_tt_ig_after_push(item, pushed, yt_step_on=True)
    assert item["tiktok_label_set"] is True
    assert item["instagram_label_set"] is True
    assert item["status"] == "scheduled"
    assert item["privacy"] == "public"


def test_tt_ig_push_fail_keeps_label_pending():
    import youtube_label_step as Y
    item = {
        "id": "lp4b", "title": "t", "status": "label_pending", "privacy": "private",
        "ai_disclosure": True, "youtube_label_set": True,
    }
    fails = []
    pushed = Y.notify_tt_ig_labels(item, push_fn=lambda *a, **k: False)
    Y.apply_tt_ig_after_push(item, pushed, yt_step_on=True)
    assert pushed is False
    assert item["status"] == "label_pending"
    assert not item.get("tiktok_label_set")
    Y.notify_fail(item, "tt_ig_push_failed", push_fn=lambda t, b, key=None: fails.append(t) or True)
    assert fails and ("fail" in fails[0].lower() or "private" in fails[0].lower())


def test_ui_has_label_pending_chip_no_labels_set_tap():
    assert "Label pending" in JS
    assert 'data-appr-act="confirm_labels"' not in JS
    assert "Labels set" not in JS
    assert "label_pending" in JS
    assert "no hub tap" in JS.lower()


def test_caption_title_unchanged_on_label_pending_path():
    cap, title = "Watch the full episode — link in bio.", "Nemoris tip cut"
    item = {"id": "lp5", "caption": cap, "title": title, "ai_disclosure": True, "status": "approved"}
    rec = S.job_record(item)
    assert rec["caption"] == cap
    assert rec["title"] == title
    for bad in ("label_pending", "containsSynthetic", "AI generated", "ai_disclosure"):
        assert bad not in rec["caption"]
        assert bad not in rec["title"]
