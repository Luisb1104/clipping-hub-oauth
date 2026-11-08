"""Storyblocks YouTube is bound to the MAIN channel id. Facebook is a separate platform allow."""
from pathlib import Path
import schedule_hook as S
import server as srv

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "app.js").read_text()

TARGETS = {
    "version": 1,
    "poster": "opus",
    "targets": {
        "MAIN": {
            "name": "Clipped Motions",
            "handle": "@clippedmotions",
            "yt": S.MAIN_YOUTUBE_CHANNEL_ID,
            "opus_post_account_id": "main-opus",
            "whop": "w1",
        },
        "PAID": {
            "name": "Clips Paid",
            "handle": "@paid",
            "yt": "UC8TrAT8V-HacqYlqqqzIQKg",
            "opus_post_account_id": "paid-opus",
            "whop": "w2",
        },
        "GAMING": {
            "name": "Gaming",
            "handle": "@game",
            "yt": "UCgamingFuture00000000001",
            "opus_post_account_id": "game-opus",
            "whop": "w3",
        },
    },
}


def test_no_license_routing_unchanged():
    item = {"id": "n1", "is_ad": False, "platforms": ["TikTok Business"]}
    r = S.route_for_item(item, targets=TARGETS)
    assert r["target"] == "MAIN" and r["blocked"] is False
    item2 = {"id": "n2", "is_ad": True, "platforms": ["TikTok Business"]}
    r2 = S.route_for_item(item2, targets=TARGETS)
    assert r2["target"] == "PAID" and r2["blocked"] is False
    assert r2["paid_promotion"] is True


def test_storyblocks_main_allowed():
    item = {
        "id": "s1",
        "license": {"source": "storyblocks"},
        "platforms": ["Clipped Motions YouTube", "TikTok Business", "IG Business"],
        "is_ad": False,
    }
    r = S.route_for_item(item, targets=TARGETS)
    assert r["storyblocks"] is True
    assert r["target"] == "MAIN"
    assert r["blocked"] is False
    assert r["channel_id"] == S.MAIN_YOUTUBE_CHANNEL_ID
    rec = S.job_record({**item, "caption": "c", "title": "t", "status": "approved"}, targets=TARGETS)
    assert rec is not None and rec["target"] == "MAIN"


def test_storyblocks_paid_and_gaming_are_blocked():
    """Non-MAIN Storyblocks is refused. The target is not rewritten to MAIN."""
    for kwargs, key in (
        ({"is_ad": True, "campaign_id": ""}, "PAID"),
        ({"is_ad": False, "campaign_id": "camp_1"}, "PAID"),
        ({"is_ad": True, "campaign_id": "camp_1"}, "PAID"),
    ):
        item = {
            "id": "s2",
            "license": {"source": "StoryBlocks"},
            "platforms": ["TikTok Business", "Clipped Motions YouTube"],
            **kwargs,
        }
        r = S.route_for_item(item, targets=TARGETS)
        assert r["target"] == key, kwargs
        assert r["blocked"] is True, kwargs
        assert r["block_reason"] == "storyblocks_main_only_blocks_non_main_target"
        rec = S.job_record({**item, "caption": "c", "title": "t"}, targets=TARGETS)
        assert rec is None


def test_storyblocks_blocks_wrong_main_channel_and_non_main():
    reason = S.storyblocks_block_reason(
        {"license": {"source": "storyblocks"}},
        target_key="MAIN",
        channel_id="UCgamingFuture00000000001",
        platforms=["Clipped Motions YouTube"],
    )
    assert reason == "storyblocks_main_only_blocks_non_main_youtube"
    correct = S.storyblocks_block_reason(
        {"license": {"source": "storyblocks"}},
        target_key="MAIN",
        channel_id=S.MAIN_YOUTUBE_CHANNEL_ID,
        platforms=["Clipped Motions YouTube"],
    )
    assert correct is None
    gaming = S.storyblocks_block_reason(
        {"license": {"source": "storyblocks"}, "clip_type": "gta"},
        target_key="GAMING",
        channel_id="UC7fAgyeOwAKZYFAbcyc2Zig",
        platforms=["Clipped Motions YouTube"],
    )
    assert gaming == "storyblocks_main_only_blocks_non_main_target"
    paid = S.storyblocks_block_reason(
        {"license": {"source": "storyblocks"}, "is_ad": True},
        target_key="PAID",
        channel_id="UC8TrAT8V-HacqYlqqqzIQKg",
        platforms=["TikTok Business"],
    )
    assert paid == "storyblocks_main_only_blocks_non_main_target"


def test_storyblocks_facebook_is_legacy_blocked_until_public_flag(monkeypatch):
    # Facebook is not a global license ban. With the public flag off, the
    # pre-feature allowlist still blocks it so the label step does not upload.
    # With the flag on, FB Page alone does not block a MAIN Storyblocks item.
    item = {
        "id": "s3",
        "licenses": [{"source": "storyblocks"}],
        "platforms": ["FB Page"],
        "is_ad": False,
    }
    monkeypatch.delenv("CLIP_PUBLIC_PUBLISH", raising=False)
    blocked = S.route_for_item(item, targets=TARGETS)
    assert blocked["blocked"] is True
    assert blocked["block_reason"] == "storyblocks_main_only_blocks_platform"
    monkeypatch.setenv("CLIP_PUBLIC_PUBLISH", "true")
    r = S.route_for_item(item, targets=TARGETS)
    assert r["blocked"] is False
    assert r["target"] == "MAIN"
    unknown = {
        "id": "s3b",
        "licenses": [{"source": "storyblocks"}],
        "platforms": ["Other Network"],
        "is_ad": False,
    }
    r2 = S.route_for_item(unknown, targets=TARGETS)
    assert r2["blocked"] is True


def test_campaign_hold_does_not_change_label_step_eligibility_when_public_off(monkeypatch):
    monkeypatch.delenv("CLIP_PUBLIC_PUBLISH", raising=False)
    held = {"id": "h", "campaign_id": "HeldAlliance", "platforms": ["Clipped Motions YouTube"]}
    off = S.route_for_item(held)
    assert off["blocked"] is False
    assert off.get("held") is False
    monkeypatch.setenv("CLIP_PUBLIC_PUBLISH", "true")
    on = S.route_for_item(held)
    assert on["blocked"] is True
    assert on["held"] is True


def test_approve_storyblocks_paid_is_rejected(monkeypatch):
    monkeypatch.setattr(S, "load_targets", lambda path=None: TARGETS)
    data = {"version": 1, "items": [
        srv._clean_item({
            "id": "s4", "video": "/v.mp4", "caption": "c", "title": "t",
            "status": "pending", "is_ad": True,
            "license": {"source": "storyblocks"},
            "platforms": ["TikTok Business"],
            "ai_disclosure": False,
        })
    ]}
    assert data["items"][0]["route_blocked"] is True
    assert data["items"][0]["route_target"] == "PAID"
    assert data["items"][0]["route_block_reason"] == "storyblocks_main_only_blocks_non_main_target"
    assert data["items"][0]["storyblocks"] is True
    data, item, changed = srv.decide_approval(data, {"op": "decide", "id": "s4", "status": "approved"})
    assert changed is True
    assert item["status"] == "rejected"


def test_ui_has_storyblocks_chip():
    assert "Storyblocks: main only" in JS
