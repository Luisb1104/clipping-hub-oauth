"""Approve All: pending-only, explicit per-item actions, same per-item server path, idempotent batch id, honest partial results,
no surprise uploads, sheet fits 393x852 standalone and 1280."""
import json
import os
from pathlib import Path
import pytest
from tests.test_server import post, _browser
from tests.test_queue_layout_and_approve_copy import _page

import destination_routing as dr
import schedule_hook as sh
from tests.test_destination_routing import CFG, CH, _item


@pytest.fixture(autouse=True)
def _routes(monkeypatch):
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: CFG)
    monkeypatch.setattr(sh, "_load_channels", lambda: CH)


def _c(cid, t, caption, ai, status="pending", **kw):
    it = dr.assign(_item(t, campaign_id="cmp1" if t == "campaign" else ""), CFG, CH, now="T")
    it.update(id=cid, caption=caption, ai_disclosure=ai, status=status, video="", platforms=["youtube"], **kw)
    return it


def _seed(live, items):
    ap = live.state.parent / "approvals.json"; ap.parent.mkdir(parents=True, exist_ok=True)
    ap.write_text(json.dumps({"version": 1, "items": items}))
    return ap


def _mix():
    return [_c("p1", "horror", "Plain one", False),
            _c("p2", "campaign", "Plain two", False),
            _c("ai1", "gta", "AI clip", True),
            _c("held", "horror", "Held for revision", False, status="change_requested", note="revise captions"),
            _c("chg", "horror", "Change asked", False, status="change_requested", note="fix"),
            _c("done", "horror", "Already approved", False, status="approved"),
            _c("nodest", "zzz-unknown", "No destination", False)]


def _batch(live, bid, items):
    return post(live, {"op": "approve_batch", "batch_id": bid, "items": items}, path="/api/approvals")


def _statuses(ap):
    return {i["id"]: i["status"] for i in json.loads(ap.read_text())["items"]}


def test_batch_partial_failures_reported_per_item_and_ineligible_untouched(live, monkeypatch):
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "0")
    ap = _seed(live, _mix())
    st, body = _batch(live, "batch-0001", [{"id": "p1", "action": "manual"}, {"id": "held", "action": "manual"},
                                              {"id": "chg", "action": "manual"}, {"id": "done", "action": "manual"},
                                              {"id": "nodest", "action": "manual"}, {"id": "ghost", "action": "manual"},
                                              {"id": "ai1", "action": "manual"}])          # stale action: sheet said manual, server says private
    assert st == 200, body
    b = body["batch"]; r = {x["id"]: x for x in b["results"]}
    assert b["approved"] == 1 and b["failed"] == 6
    assert r["p1"]["ok"] and r["held"]["error"] == "not_pending:change_requested" and r["chg"]["error"] == "not_pending:change_requested"
    assert r["done"]["error"] == "not_pending:approved" and r["nodest"]["error"].startswith("not_eligible")
    assert r["ghost"]["error"] == "unknown id" and r["ai1"]["error"] == "action_changed:manual->private_no_upload"
    s = _statuses(ap)
    assert s == {"p1": "approved", "p2": "pending", "ai1": "pending", "held": "change_requested", "chg": "change_requested", "done": "approved", "nodest": "pending"}


def test_double_tap_same_batch_id_approves_once(live, monkeypatch):
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "0")
    import schedule_hook
    calls = []
    real = schedule_hook.on_approved
    monkeypatch.setattr(schedule_hook, "on_approved", lambda it: calls.append(it["id"]) or real(it))
    ap = _seed(live, _mix())
    req = [{"id": "p1", "action": "manual"}, {"id": "p2", "action": "manual"}]
    one = _batch(live, "tap-tap-01", req)[1]["batch"]
    two = _batch(live, "tap-tap-01", req)[1]["batch"]
    assert one["approved"] == 2 and two["replayed"] is True and two["approved"] == 2
    assert calls == ["p1", "p2"]                                               # hooks ran once, not twice
    assert _statuses(ap)["p1"] == "approved"


def test_bad_batch_requests_refused(live):
    _seed(live, _mix())
    assert _batch(live, "x", [{"id": "p1", "action": "manual"}])[0] == 400
    assert _batch(live, "batch-0002", [])[0] == 400
    assert _batch(live, "batch-0003", [{"id": "p1", "action": "manual"}] * 51)[0] == 400


def test_ai_false_never_uploads_and_ai_true_uses_per_item_gate(live, monkeypatch):
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    import multi_platform_publish as mpp
    seen = []
    monkeypatch.setattr(mpp, "publish_after_approve", lambda it, **k: seen.append(it["id"]) or {"ok": False, "error": "need_oauth", "platforms": []})
    ap = _seed(live, _mix())
    b = _batch(live, "batch-ai-01", [{"id": "p1", "action": "manual"}, {"id": "ai1", "action": "private_upload"}])[1]["batch"]
    r = {x["id"]: x for x in b["results"]}
    assert seen == ["ai1"]                                                    # ai_disclosure:false never reaches the upload path
    assert r["ai1"]["ok"] and r["ai1"]["warning"] == "need_oauth" and _statuses(ap)["ai1"] == "label_pending"


SIZES = [(393, 852, 59, 34), (1280, 800, 0, 0)]
FIT = """() => { const c = document.querySelector('#aa-sheet .aa-card').getBoundingClientRect();
  const bt = [...document.querySelectorAll('#aa-sheet .aa-bt .btn')].filter(b => !b.hidden).map(b => b.getBoundingClientRect());
  const hit = b => { const e = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2); return !!e && !!e.closest('.aa-bt'); };
  return {c: {top: c.top, bottom: c.bottom, left: c.left, right: c.right}, vw: innerWidth, vh: innerHeight, btOk: bt.every(hit), nbt: bt.length,
          docW: document.scrollingElement.scrollWidth}; }"""


@pytest.mark.parametrize("w,h,top,bot", SIZES, ids=["393x852-standalone", "1280x800"])
def test_approve_all_sheet_flow_fits_and_reports(live, monkeypatch, w, h, top, bot):
    monkeypatch.setenv("CLIP_YOUTUBE_LABEL_STEP", "1")
    import multi_platform_publish as mpp
    monkeypatch.setattr(mpp, "publish_after_approve", lambda it, **k: {"ok": False, "error": "need_oauth", "platforms": []})
    items = _mix() + [_c("p%d" % n, "horror", "Filler clip %d with a long caption to wrap the row" % n, False) for n in range(3, 12)]
    ap = _seed(live, items)
    sync_api = pytest.importorskip("playwright.sync_api")
    shots = os.environ.get("AA_SHOTS")
    with sync_api.sync_playwright() as p:
        browser = _browser(p); ctx, pg = _page(browser, live, w, h, top, bot)
        posts = []
        pg.on("request", lambda rq: rq.method == "POST" and "/api/approvals" in rq.url and posts.append(rq.post_data))
        pg.goto(live.base + "/approvals"); pg.wait_for_timeout(700)
        assert pg.inner_text("#appr-all") == "Approve all (12)"
        pg.click("#appr-all"); pg.wait_for_timeout(300)
        assert pg.inner_text("#aa-count") == "12 clips" and pg.inner_text("#aa-confirm") == "Approve 12"
        skips = pg.eval_on_selector_all("#aa-sheet [data-aa-skip]", "es => es.map(e => e.dataset.aaSkip + ':' + e.dataset.aaReason)")
        assert "nodest:needs_destination" in skips or any(s.startswith("nodest:") for s in skips), skips
        assert any(s.startswith("held:") for s in skips) and any(s.startswith("chg:") for s in skips), skips
        ids = pg.eval_on_selector_all("#aa-sheet [data-aa-id]", "es => es.map(e => e.dataset.aaId + ':' + e.dataset.aaAction)")
        assert sorted(ids) == sorted(["p1:manual", "p2:manual", "ai1:private_upload"] + ["p%d:manual" % n for n in range(3, 12)])
        assert pg.eval_on_selector("#aa-body", "b => b.firstElementChild.dataset.aaId") == "ai1"   # private upload listed first, visible without scrolling
        priv = pg.text_content('#aa-sheet .aa-priv[data-aa-id="ai1"]')
        assert "PRIVATE YouTube upload" in priv and "GAMING" in priv and CFG["targets"]["GAMING"]["yt"] in priv
        assert CFG["targets"]["PAID"]["handle"] in pg.inner_text('#aa-sheet li[data-aa-id="p2"]')
        m = pg.evaluate(FIT)
        assert m["c"]["top"] >= top - 0.5 and m["c"]["bottom"] <= m["vh"] - bot + 0.5 and m["btOk"] and m["nbt"] == 2 and m["docW"] <= m["vw"], m
        if shots: pg.screenshot(path="%s/approve-all-sheet-%dx%d.png" % (shots, w, h))
        pg.dblclick("#aa-confirm"); pg.wait_for_timeout(900)                    # double tap: one POST
        assert len(posts) == 1, posts
        sent = json.loads(posts[0]); assert sent["op"] == "approve_batch" and len(sent["items"]) == 12
        res = pg.inner_text("#aa-result")
        assert res.startswith("12 approved") and "ai1: approved; need_oauth" in res, res
        assert pg.is_hidden("#aa-confirm") and pg.inner_text("#aa-cancel") == "Close"
        vis = pg.evaluate("() => { const r = document.querySelector('#aa-result'), li = r.querySelector('li'); if (!li) return false;"
                          " const a = r.getBoundingClientRect(), b = li.getBoundingClientRect(); return b.height > 0 && b.top >= a.top - 0.5 && b.bottom <= a.bottom + 0.5; }")
        assert vis, "per-item result line must be visible, not squashed"
        if shots: pg.screenshot(path="%s/approve-all-result-%dx%d.png" % (shots, w, h))
        pg.click("#aa-cancel"); pg.wait_for_timeout(300)
        assert pg.is_hidden("#aa-sheet") and pg.inner_text("#appr-all") == "Approve all (0)"
        pg.click("#appr-all"); pg.wait_for_timeout(300)
        assert pg.is_disabled("#aa-confirm")
        assert "Skipped" in pg.inner_text("#aa-sheet")
        pg.click("#aa-cancel")
        browser.close()
    s = _statuses(ap)
    assert s["held"] == "change_requested" and s["chg"] == "change_requested" and s["nodest"] == "pending" and s["ai1"] == "label_pending"


def test_public_batch_partial_is_not_fully_approved(live, monkeypatch):
    import post_idempotency as idem
    import public_publish as P
    ledger = live.dir / "batch-ledger.jsonl"
    monkeypatch.setattr(idem, "LEDGER_PATH", ledger)
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(ledger))
    monkeypatch.setenv("CLIP_PUBLIC_PUBLISH", "true")
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: json.loads(
        (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "post_targets.json").read_text()
    ))
    monkeypatch.setattr(P, "_armed", lambda key, channel: key == "youtube")
    calls = []

    def runner(item, row):
        calls.append(row.get("key"))
        return {
            "ok": True, "called": True, "permalink": "https://www.youtube.com/watch?v=abcdefghijk",
            "video_id": "abcdefghijk", "youtube_label": True,
        }

    monkeypatch.setattr(P, "external_runners", lambda: {"youtube": runner})
    item = dr.assign(_item("horror"), CFG, CH, now="T")
    item.update(
        id="mixpub01", caption="Ready and blocked", title="T", ai_disclosure=True, rights_ok=True,
        status="pending", video="/samples/sample-a.mp4",
        platforms=["Clipped Motions YouTube", "TikTok Business"],
    )
    ap = _seed(live, [item])
    import server
    preview = server.load_approvals(ap)["items"][0]["public_preview"]
    assert preview["will_dispatch_any"] is True
    rows = [{"key": r["key"], "row_hash": r["row_hash"]} for r in preview["platforms"]]
    st, body = _batch(live, "batch-mix-01", [{
        "id": "mixpub01", "action": "public_review",
        "manifest_hash": preview["manifest_hash"], "platform_rows": rows,
    }])
    assert st == 200, body
    b = body["batch"]
    row = b["results"][0]
    assert b["approved"] == 0 and b["partial"] == 1 and b["success"] == 0
    assert row["ok"] is False and row["outcome"] == "partial" and row["posted"] is True
    plats = {p["key"]: p for p in row["public_publish"]["platforms"]}
    assert plats["youtube"]["status"] == "done"
    assert plats["tiktok"]["status"] == "blocked"
    saved = json.loads(ap.read_text())["items"][0]
    assert not saved.get("youtube_video_id")
    assert calls == ["youtube"]


def test_all_blocked_batch_counts_blocked_and_headline_says_so(live, monkeypatch):
    import post_idempotency as idem
    import public_publish as P
    ledger = live.dir / "blocked-ledger.jsonl"
    monkeypatch.setattr(idem, "LEDGER_PATH", ledger)
    monkeypatch.setenv("CLIPPING_HUB_POST_LEDGER", str(ledger))
    monkeypatch.setenv("CLIP_PUBLIC_PUBLISH", "true")
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: json.loads(
        (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "post_targets.json").read_text()
    ))
    monkeypatch.setattr(P, "_armed", lambda key, channel: key == "youtube")
    monkeypatch.setattr(P, "external_runners", lambda: {
        "youtube": lambda item, row: {"ok": False, "called": False, "reason": "media_missing"},
    })
    item = dr.assign(_item("horror"), CFG, CH, now="T")
    item.update(
        id="block01", caption="Blocked horror", title="T", ai_disclosure=True, rights_ok=True,
        status="pending", video="/samples/sample-a.mp4", platforms=["Clipped Motions YouTube"],
    )
    ap = _seed(live, [item])
    import server
    preview = server.load_approvals(ap)["items"][0]["public_preview"]
    rows = [{"key": r["key"], "row_hash": r["row_hash"]} for r in preview["platforms"]]
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        ctx, pg = _page(browser, live, 1280, 800, 0, 0)
        pg.goto(live.base + "/approvals")
        pg.wait_for_selector("#appr-all:not([hidden])")
        assert pg.inner_text("#appr-all") == "Approve all (1)"
        pg.click("#appr-all")
        pg.wait_for_selector("#aa-confirm")
        pg.click("#aa-confirm")
        pg.wait_for_selector("#aa-result:not([hidden])")
        text = pg.inner_text("#aa-result")
        assert "1 blocked" in text, text
        assert not text.startswith("1 approved"), text
        browser.close()
    body = json.loads((ap.parent / "approve_batches.json").read_text())
    batch = next(iter(body["batches"].values()))
    assert batch["blocked"] == 1 and batch["approved"] == 0 and batch["success"] == 0
    assert batch["results"][0]["outcome"] == "blocked"


def test_public_sheet_shows_one_ready_row_and_the_skip(live, monkeypatch):
    import public_publish as P
    monkeypatch.setenv("CLIP_PUBLIC_PUBLISH", "true")
    monkeypatch.setattr(sh, "load_targets", lambda *a, **k: json.loads(
        (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "post_targets.json").read_text()
    ))
    monkeypatch.setattr(P, "_armed", lambda key, channel: key == "youtube")
    ready = dr.assign(_item("horror"), CFG, CH, now="T")
    ready.update(
        id="ready01", caption="Ready horror", title="T", ai_disclosure=True, rights_ok=True,
        status="pending", video="/samples/sample-a.mp4", platforms=["Clipped Motions YouTube"],
    )
    skipped = dr.assign(_item("campaign", campaign_id="cmp1"), CFG, CH, now="T")
    skipped.update(
        id="skip01", caption="No rights", title="T", ai_disclosure=True, status="pending",
        video="/samples/sample-a.mp4", platforms=["Clipped Motions YouTube"],
    )
    ap = _seed(live, [ready, skipped])
    import server
    loaded = {i["id"]: i for i in server.load_approvals(ap)["items"]}
    assert loaded["ready01"]["public_preview"]["will_dispatch_any"] is True
    assert server.approve_action(loaded["ready01"]) == "public_review"
    assert server.approve_action(loaded["skip01"]) == ""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        ctx, pg = _page(browser, live, 1280, 800, 0, 0)
        pg.goto(live.base + "/approvals")
        pg.wait_for_selector("#appr-all:not([hidden])")
        assert pg.inner_text("#appr-all") == "Approve all (1)"
        pg.click("#appr-all")
        pg.wait_for_selector("#aa-sheet [data-aa-skip='skip01']")
        body = pg.inner_text("#aa-sheet")
        assert "UCgMuVjQmB9WvZtSz4e23THw" in body
        assert "ready01" in pg.eval_on_selector_all("#aa-sheet [data-aa-id]", "es => es.map(e => e.dataset.aaId)")
        skip = pg.eval_on_selector("#aa-sheet [data-aa-skip='skip01']", "e => e.dataset.aaReason")
        assert "youtube_paid_label_unverified" in skip or "rights_unconfirmed" in skip or "campaign_config_absent" in skip
        assert pg.inner_text("#aa-confirm") == "Confirm 1"
        assert pg.is_enabled("#aa-confirm")
        browser.close()
