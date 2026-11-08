"""GAMING has its own hub YouTube grant: own token file, own regrant URL, never MAIN/PAID's token. No grant is started here."""
import json
import pytest
import youtube_label_step as yls
from tests.test_server import post
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def tokdir(monkeypatch, tmp_path):
    monkeypatch.setattr(yls, "TOKEN_DIR", tmp_path)
    return tmp_path


def test_gaming_token_file_is_separate(tokdir):
    paths = {c: yls.token_path(c) for c in ("MAIN", "PAID", "GAMING")}
    assert paths["GAMING"].name == "GAMING.json" and len(set(paths.values())) == 3


def test_gaming_never_uses_main_or_paid_token(tokdir):
    (tokdir / "MAIN.json").write_text(json.dumps({"refresh_token": "m"}))
    (tokdir / "PAID.json").write_text(json.dumps({"refresh_token": "p"}))
    assert yls.load_token("GAMING") is None
    assert yls.grant_meta("GAMING")["present"] is False and yls.needs_oauth("GAMING") is True
    ok, err = yls.check_grant_alive("GAMING")
    assert not ok and err == "no_token"


def test_gaming_save_and_load_isolated(tokdir):
    assert yls.save_token("GAMING", {"refresh_token": "g"})
    assert yls.load_token("GAMING")["refresh_token"] == "g"
    assert yls.load_token("MAIN") is None and yls.load_token("PAID") is None


def test_regrant_url_and_summary_include_gaming(tokdir):
    assert yls.regrant_hub_url("GAMING").endswith("/approvals?yt_regrant=GAMING")
    s = yls.grants_summary()
    assert s["GAMING"]["channel"] == "GAMING" and s["GAMING"]["present"] is False


def test_expected_channel_for_gaming_is_gaming_row(monkeypatch):
    import schedule_hook as sh
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: {"targets": {"MAIN": {"yt": "UCgMuVjQmB9WvZtSz4e23THw"}, "GAMING": {"name": "Clipped Motions Gaming", "yt": "UC7fAgyeOwAKZYFAbcyc2Zig", "handle": ""}}})
    assert yls.expected_yt_for_hub_channel("GAMING")[1] == "UC7fAgyeOwAKZYFAbcyc2Zig"


def test_oauth_start_accepts_gaming_without_starting_a_grant(live, monkeypatch):
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    seen = []
    monkeypatch.setattr(yls, "build_auth_url", lambda **k: (seen.append(k["channel"]) or "https://accounts.google.com/x", None))
    code, body = post(live, {"channel": "GAMING"}, path="/api/youtube-oauth/start")
    assert code == 200 and body["channel"] == "GAMING" and seen == ["GAMING"] and body["regrant_url"].endswith("yt_regrant=GAMING")


def test_frontend_whitelists_gaming_regrant():
    js = (ROOT / "static" / "app.js").read_text()
    assert 'ch !== "GAMING"' in js and "unknown ?yt_regrant: never start a grant" in js


def _gaming_item():
    import destination_routing as dr
    from tests.test_destination_routing import CFG, CH, _item
    return dict(dr.assign(_item("gta"), CFG, CH), ai_disclosure=True, projectId="p", clipId="c"), CFG, CH


def test_run_after_approve_channel_comes_from_item_destination(monkeypatch, tokdir):
    """Deadbolt: run_after_approve(channel='MAIN') on a GAMING item used to refresh MAIN's token before the upload refused it."""
    import schedule_hook as sh
    item, cfg, ch = _gaming_item()
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: cfg)
    monkeypatch.setattr(sh, "_load_channels", lambda: ch)
    (tokdir / "MAIN.json").write_text(json.dumps({"refresh_token": "m"}))
    touched = []
    for name in ("refresh_access", "load_token", "needs_oauth", "build_auth_url", "opus_upload_private"):
        monkeypatch.setattr(yls, name, (lambda n: lambda *a, **k: touched.append((n, a, k)) or (None, "x"))(name))
    monkeypatch.setattr(yls, "notify_fail", lambda *a, **k: None)
    out = yls.run_after_approve(item, channel="MAIN", push_fn=lambda *a, **k: None)
    assert out["error"] == "channel_mismatch:MAIN!=GAMING" and touched == []


def test_run_after_approve_gaming_uses_only_gaming_grant(monkeypatch, tokdir):
    import schedule_hook as sh
    item, cfg, ch = _gaming_item()
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: cfg)
    monkeypatch.setattr(sh, "_load_channels", lambda: ch)
    (tokdir / "MAIN.json").write_text(json.dumps({"refresh_token": "m"}))
    (tokdir / "PAID.json").write_text(json.dumps({"refresh_token": "p"}))
    refreshed, auth = [], []
    monkeypatch.setattr(yls, "refresh_access", lambda c, **k: refreshed.append(c) or (None, "x"))
    monkeypatch.setattr(yls, "build_auth_url", lambda **k: auth.append(k["channel"]) or ("https://accounts.google.com/x", None))
    monkeypatch.setattr(yls, "notify_regrant", lambda *a, **k: None)
    out = yls.run_after_approve(item, push_fn=lambda *a, **k: None)
    assert out["need_oauth"] and auth == ["GAMING"] and refreshed == []      # no GAMING grant: fail closed, MAIN/PAID never refreshed
