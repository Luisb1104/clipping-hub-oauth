"""Type -> destination at clip creation (MAIN/PAID/GAMING). Fail closed; never reassign; no fallback; gates unchanged."""
import copy, json
import pytest
import destination_routing as dr
import schedule_hook as sh
import server
import multi_platform_publish as mpp
import youtube_label_step as yls
from tests.test_server import post

CFG = {"poster": "opus", "targets": {
    "MAIN": {"name": "Clipped Motions", "handle": "@clippedmotions", "yt": "UCgMuVjQmB9WvZtSz4e23THw", "opus_post_account_id": "6aedeb42386c37c006241619"},
    "PAID": {"name": "Clipped Motions Clips", "handle": "@clippedmotionsclips", "yt": "UC8TrAT8V-HacqYlqqqzIQKg", "opus_post_account_id": "6aedf5ffb09f11b7595325ed"},
    "GAMING": {"name": "Clipped Motions Gaming", "handle": "", "yt": "UC7fAgyeOwAKZYFAbcyc2Zig", "opus_post_account_id": "6aee516c386c37c006246b12"}},
    "type_routes": {"horror": "MAIN", "campaign": "PAID", "gta": "GAMING"}}
CH = {"channels": [
    {"post_account_id": "6aedeb42386c37c006241619", "platform": "YOUTUBE", "name": "Clipped Motions", "profile_url": "https://www.youtube.com/channel/UCgMuVjQmB9WvZtSz4e23THw"},
    {"post_account_id": "6aedf5ffb09f11b7595325ed", "platform": "YOUTUBE", "name": "Clipped Motions Clips ", "profile_url": "https://www.youtube.com/channel/UC8TrAT8V-HacqYlqqqzIQKg"},
    {"post_account_id": "6aee516c386c37c006246b12", "platform": "YOUTUBE", "name": "Clipped Motions Gaming", "profile_url": "https://www.youtube.com/channel/UC7fAgyeOwAKZYFAbcyc2Zig"},
    {"post_account_id": "6aedec214ca796e276002993", "platform": "TIKTOK_BUSINESS", "name": "Clipped Motions", "profile_url": ""}]}


def _item(t, **kw):
    d = {"id": "c-" + str(t), "status": "pending", "clip_type": t, "platforms": ["Clipped Motions YouTube"]}
    d.update(kw); return d


@pytest.mark.parametrize("t,key,yt,opus", [
    ("horror", "MAIN", "UCgMuVjQmB9WvZtSz4e23THw", "6aedeb42386c37c006241619"),
    ("campaign", "PAID", "UC8TrAT8V-HacqYlqqqzIQKg", "6aedf5ffb09f11b7595325ed"),
    ("GTA", "GAMING", "UC7fAgyeOwAKZYFAbcyc2Zig", "6aee516c386c37c006246b12")])
def test_each_type_gets_its_channel(t, key, yt, opus):
    it = dr.assign(_item(t, campaign_id="cmp1" if key == "PAID" else ""), CFG, CH, now="T")
    d = it["destination"]
    assert (d["target"], d["yt"], d["opus_post_account_id"]) == (key, yt, opus) and "destination_error" not in it
    r = sh.route_for_item(it, targets=CFG, channels=CH)
    assert r["target"] == key and r["channel_id"] == yt and r["opus_post_account_id"] == opus and not r["blocked"]


@pytest.mark.parametrize("item,cfg,ch,reason", [
    (_item("cooking"), CFG, CH, "unknown_type:cooking"),
    (_item(""), CFG, CH, "missing_type"),
    (_item("horror"), dict(CFG, type_routes={}), CH, "mapping_missing"),
    (_item("gta"), {"targets": {k: v for k, v in CFG["targets"].items() if k != "GAMING"}, "type_routes": CFG["type_routes"]}, CH, "target_missing:GAMING"),
    (_item("gta"), CFG, {"channels": [c for c in CH["channels"] if c["post_account_id"] != "6aee516c386c37c006246b12"]}, "not_connected_in_opus:GAMING"),
    (_item("gta"), CFG, {"channels": [dict(c, profile_url="https://www.youtube.com/channel/UCgMuVjQmB9WvZtSz4e23THw") if c["post_account_id"] == "6aee516c386c37c006246b12" else c for c in CH["channels"]]}, "id_mismatch:GAMING"),
], ids=["unknown-type", "empty-type", "missing-mapping", "missing-target", "disconnected", "mismatched-ids"])
def test_fail_closed_no_fallback(item, cfg, ch, reason):
    it = dr.assign(item, cfg, ch)
    assert "destination" not in it and it["destination_error"] == reason
    r = sh.route_for_item(it, targets=cfg, channels=ch)
    assert r["needs_destination"] and r["blocked"] and r["target"] == "" and r["channel_id"] == "" and r["opus_post_account_id"] == ""


def test_stamp_reverified_at_read_time_disconnect_after_creation():
    it = dr.assign(_item("gta"), CFG, CH)
    gone = {"channels": [c for c in CH["channels"] if c["post_account_id"] != "6aee516c386c37c006246b12"]}
    r = sh.route_for_item(it, targets=CFG, channels=gone)
    assert r["needs_destination"] and r["target"] == "" and it["destination"]["target"] == "GAMING"   # stamp kept, not reassigned


def test_campaign_gate_kept():
    paid_no_cmp = dr.assign(_item("campaign"), CFG, CH)
    assert sh.route_for_item(paid_no_cmp, targets=CFG, channels=CH)["destination_reason"] == "campaign_id_missing"
    ad_to_main = dr.assign(_item("horror", is_ad=True), CFG, CH)
    assert sh.route_for_item(ad_to_main, targets=CFG, channels=CH)["destination_reason"] == "campaign_requires_PAID"
    ok = sh.route_for_item(dr.assign(_item("campaign", campaign_id="x"), CFG, CH), targets=CFG, channels=CH)
    assert ok["paid_promotion"] and "#ad" in ok["hashtags"]


def test_existing_items_never_reassigned_or_changed():
    legacy = {"id": "old", "status": "pending", "is_ad": True, "campaign_id": "c"}
    stamped = dr.assign(_item("horror"), CFG, CH)
    failed = dr.assign(_item("nope"), CFG, CH)
    for x in (legacy, stamped, failed):
        before = copy.deepcopy(x)
        assert dr.assign(x, dict(CFG, type_routes={"horror": "GAMING", "nope": "MAIN"}), CH) == before and x == before
    assert sh.route_for_item(legacy, targets=CFG)["target"] == "PAID"     # legacy MAIN/PAID routing unchanged


def test_existing_live_queue_items_route_exactly_as_before(tmp_path):
    items = [{"id": "a", "status": "pending", "ai_disclosure": False, "is_ad": True, "campaign_id": "k"},
             {"id": "b", "status": "pending", "ai_disclosure": True},
             {"id": "c", "status": "change_requested", "note": "x", "is_ad": True}]
    ap = tmp_path / "approvals.json"; ap.write_text(json.dumps({"version": 1, "items": items}))
    got = {i["id"]: i for i in server.load_approvals(ap)["items"]}
    assert [got[k]["route_target"] for k in "abc"] == ["PAID", "MAIN", "PAID"]
    assert not any(got[k].get("needs_destination") for k in "abc") and not any("destination" in got[k] for k in "abc")
    assert json.loads(ap.read_text())["items"] == items                     # file untouched by reads


def test_approve_refused_for_needs_destination_and_item_unchanged(monkeypatch):
    it = server._clean_item(dict(_item("cooking"), destination_error="unknown_type:cooking"))
    assert it["needs_destination"] and it["route_blocked"]
    data = {"items": [it]}; before = copy.deepcopy(it)
    with pytest.raises(server.BadRequest):
        server.decide_approval(data, {"op": "decide", "id": it["id"], "status": "approved"})
    assert data["items"][0] == before                                        # not rejected, not touched


def test_gaming_without_gaming_grant_never_reaches_opus(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    monkeypatch.setattr(yls, "TOKEN_DIR", tmp_path)
    (tmp_path / "MAIN.json").write_text(json.dumps({"refresh_token": "main-only"}))   # a MAIN grant must NOT be reused
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: CFG)
    monkeypatch.setattr(sh, "_load_channels", lambda: CH)
    calls = []
    monkeypatch.setattr(yls, "opus_http_create_post", lambda *a, **k: calls.append("opus"))
    monkeypatch.setattr(yls, "notify_fail", lambda *a, **k: None)
    monkeypatch.setattr(yls, "notify_regrant", lambda *a, **k: None)
    monkeypatch.setattr(yls, "build_auth_url", lambda **k: ("https://accounts.google.com/o/oauth2/v2/auth?x=" + k["channel"], None))
    g = dict(dr.assign(_item("gta"), CFG, CH), ai_disclosure=True, projectId="p", clipId="c")
    res = mpp.publish_after_approve(g, push_fn=lambda *a, **k: None)
    assert calls == [] and res.get("oauth_url", "").endswith("x=GAMING"), res


def test_creation_tool_stamps_and_passes_through(tmp_path):
    import subprocess, sys
    t = tmp_path / "t.json"; t.write_text(json.dumps(CFG)); c = tmp_path / "c.json"; c.write_text(json.dumps(CH))
    inp = tmp_path / "in.json"; inp.write_text(json.dumps({"items": [_item("gta"), _item("zzz"), {"id": "legacy"}]}))
    r = subprocess.run([sys.executable, "tools/assign_destination.py", "--in", str(inp), "--targets", str(t), "--channels", str(c)], capture_output=True, text=True, check=True)
    out = json.loads(r.stdout)["items"]
    assert out[0]["destination"]["target"] == "GAMING" and out[1]["destination_error"] == "unknown_type:zzz" and out[2] == {"id": "legacy"}
    assert "needs destination: c-zzz" in r.stderr


def test_approvals_card_shows_exact_destination_and_blocks(live, monkeypatch):
    sync_api = pytest.importorskip("playwright.sync_api")
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: CFG)
    monkeypatch.setattr(sh, "_load_channels", lambda: CH)
    ap = live.state.parent / "approvals.json"; ap.parent.mkdir(parents=True, exist_ok=True)
    ap.write_text(json.dumps({"version": 1, "items": [dict(dr.assign(_item("gta"), CFG, CH), caption="g", ai_disclosure=False),
                                                      dict(dr.assign(_item("cooking"), CFG, CH), caption="u")]}))
    from tests.test_server import _browser
    with sync_api.sync_playwright() as p:
        b = _browser(p); pg = b.new_context(viewport={"width": 1280, "height": 800}, service_workers="block").new_page()
        pg.goto(live.base + "/approvals"); pg.wait_for_timeout(700)
        g = pg.inner_text('[data-pane=approvals] [data-appr-id="c-gta"] .dest-line')
        u = pg.inner_text('[data-pane=approvals] [data-appr-id="c-cooking"] .dest-line')
        dis = pg.get_attribute('[data-pane=approvals] [data-appr-id="c-cooking"] .bt .btn.pri', "disabled")
        live_btn = pg.query_selector_all('[data-pane=approvals] [data-appr-id="c-cooking"] [data-appr-act="approved"]')
        b.close()
    assert "Clipped Motions Gaming" in g and "UC7fAgyeOwAKZYFAbcyc2Zig" in g and "6aee516c386c37c006246b12" in g and "no handle on file" in g
    assert u.startswith("Needs destination") and dis is not None and live_btn == []
