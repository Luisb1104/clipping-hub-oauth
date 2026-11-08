"""MAIN vs PAID routing from post_targets.json."""
import json
from pathlib import Path

import schedule_hook as S

ROOT = Path(__file__).resolve().parents[1]
TARGETS = json.loads((ROOT / "tests" / "fixtures" / "post_targets.json").read_text())


def test_targets_file_has_main_and_paid():
    assert TARGETS["poster"] == "opus"
    assert set(TARGETS["targets"]) >= {"MAIN", "PAID"}
    assert TARGETS["targets"]["MAIN"]["yt"].startswith("UC")
    assert TARGETS["targets"]["PAID"]["opus_post_account_id"]


def test_plain_routes_main():
    r = S.route_for_item({"id": "1", "caption": "x", "hashtags": ["#horror"]}, targets=TARGETS)
    assert r["target"] == "MAIN"
    assert r["paid_promotion"] is False
    assert r["poster"] == "opus"
    assert r["channel_id"] == TARGETS["targets"]["MAIN"]["yt"]
    assert r["opus_post_account_id"] == TARGETS["targets"]["MAIN"]["opus_post_account_id"]
    assert "#ad" not in [t.lower() for t in r["hashtags"]]


def test_is_ad_routes_paid_and_adds_ad_tag():
    r = S.route_for_item({"id": "1", "is_ad": True, "hashtags": ["#horror"]}, targets=TARGETS)
    assert r["target"] == "PAID"
    assert r["paid_promotion"] is True
    assert r["channel_id"] == TARGETS["targets"]["PAID"]["yt"]
    assert any(t.lower() == "#ad" for t in r["hashtags"])


def test_campaign_id_routes_paid():
    r = S.route_for_item({"id": "1", "campaign_id": "nemoris", "hashtags": ["#ad"]}, targets=TARGETS)
    assert r["target"] == "PAID" and r["paid_promotion"] is True
    assert r["hashtags"].count("#ad") == 1  # not duplicated


def test_job_record_carries_routing_fields(tmp_path):
    item = {"id": "a1", "video": "v.mp4", "caption": "c", "platforms": [],
            "is_ad": True, "campaign_id": "x", "hashtags": [], "decided_at": "t"}
    rec = S.job_record(item, now="t", targets=TARGETS)
    assert rec["poster"] == "opus"
    assert rec["target"] == "PAID"
    assert rec["channel_id"] == TARGETS["targets"]["PAID"]["yt"]
    assert rec["opus_post_account_id"] == TARGETS["targets"]["PAID"]["opus_post_account_id"]
    assert rec["paid_promotion"] is True
    assert "#ad" in rec["hashtags"]


def test_on_approved_noop_when_flag_off_but_route_still_works():
    assert S.enabled({"CLIP_AUTOPOST_ENABLED": "false"}) is False
    r = S.route_for_item({"id": "1"}, targets=TARGETS)
    assert r["target"] == "MAIN"
