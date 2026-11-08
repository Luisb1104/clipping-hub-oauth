"""ai_disclosure default true; platform map; caption/title never get AI wording."""
from pathlib import Path
import json
import schedule_hook as S
import server as srv

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "app.js").read_text()
SW = (ROOT / "static" / "sw.js").read_text()


def test_ai_disclosure_defaults_true():
    assert S.parse_ai_disclosure({}) is True
    assert S.parse_ai_disclosure({"caption": "x"}) is True
    assert S.parse_ai_disclosure({"ai_disclosure": False}) is False
    assert S.parse_ai_disclosure({"ai_disclosure": "false"}) is False
    assert S.parse_ai_disclosure({"ai_disclosure": True}) is True


def test_ai_platform_map_on_and_off():
    on = S.ai_platform_map(True)
    assert on["youtube"]["altered_synthetic"] is True
    assert on["tiktok"]["ai_generated"] is True
    assert on["instagram"]["ai_info_label"] is True
    off = S.ai_platform_map(False)
    assert off["youtube"]["altered_synthetic"] is False
    assert off["tiktok"]["ai_generated"] is False
    assert off["instagram"]["ai_info_label"] is False


def test_job_record_includes_ai_fields_default_on():
    item = {
        "id": "ai1",
        "video": "/samples/a.mp4",
        "caption": "Friday horror tip",
        "title": "Tip cut",
        "platforms": ["TikTok Business"],
        "hashtags": ["#horror"],
        "is_ad": False,
        "status": "approved",
    }
    rec = S.job_record(item)
    assert rec["ai_disclosure"] is True
    assert rec["ai_platform"]["youtube"]["altered_synthetic"] is True
    assert rec["ai_platform"]["tiktok"]["ai_generated"] is True
    assert rec["ai_platform"]["instagram"]["ai_info_label"] is True
    assert rec["youtube_altered_synthetic"] is True
    assert rec["tiktok_ai_generated"] is True
    assert rec["instagram_ai_info_label"] is True


def test_caption_and_title_unchanged_no_ai_words_injected():
    caption = "Watch the full episode — link in bio."
    title = "Backrooms Nemoris cut"
    item = {
        "id": "ai2",
        "video": "/x.mp4",
        "caption": caption,
        "title": title,
        "platforms": ["YouTube Shorts"],
        "ai_disclosure": True,
        "status": "approved",
    }
    rec = S.job_record(item)
    assert rec["caption"] == caption
    assert rec["title"] == title
    for bad in ("ai_disclosure", "altered_synthetic", "ai_generated", "ai_info_label", "#ai", "AI generated", "AI label"):
        assert bad.lower() not in rec["caption"].lower()
        assert bad.lower() not in rec["title"].lower()
    # cleaned approval item also leaves caption/title alone
    cleaned = srv._clean_item({**item, "status": "pending"})
    assert cleaned["caption"] == caption
    assert cleaned["title"] == title
    assert cleaned["ai_disclosure"] is True


def test_job_respects_explicit_false():
    item = {"id": "ai3", "video": "v", "caption": "plain", "title": "t", "ai_disclosure": False, "status": "approved"}
    rec = S.job_record(item)
    assert rec["ai_disclosure"] is False
    assert rec["ai_platform"]["youtube"]["altered_synthetic"] is False
    assert rec["tiktok_ai_generated"] is False


def test_approval_card_shows_ai_label_chip():
    assert "AI label:" in JS
    assert 'AI label: \' + (aiOn ? "on" : "off")' in JS or "AI label: " in JS


def test_shell_bumped_for_ai_chip():
    assert "clipping-hub-shell-v35" in SW


def test_ai_job_privacy_and_label_pending():
    rec = S.job_record({"id": "ai9", "caption": "c", "title": "t", "ai_disclosure": True, "status": "approved"})
    assert rec["privacy"] == "private"
    assert rec["status"] == "label_pending"
