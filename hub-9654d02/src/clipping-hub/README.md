# Clipping Hub (shell)

Private draft imported from sanitized source `16ba1e4` (138 files, no git history). This tree is not proven identical to the live Mac tree `4930dc3`. `CLIP_PUBLIC_PUBLISH` defaults **off**. Nothing in this draft posts, schedules, or calls a live platform.

A local, one-screen app shell: **Home, Clips queue (compliance gate), Approvals (Frankie inbox), Channels, Revenue, Trend Watcher**. Sky Air look (light/dark toggle, remembered), tabs and taps instead of scrolling, bottom thumb nav on phone.

This is a SHELL. Nothing is posted, nothing is connected, nothing is spent, no outbound network.

- `server.py`: stdlib server on 127.0.0.1:8505. Writes only under `data/`: `state.json` (theme + clip marks), `approvals.json` (Frankie inbox decisions), `events.json` (read-only for the hub; Frankie/jobs append), `hub-token`.
- Approvals inbox (`/approvals`): Luis decides pending items. **Approving records your go. Frankie schedules it.** The hub never posts and never calls platforms.
- Alerts: opt-in local `showNotification` via the service worker while the hub is open. **No push server, no keys.** Remote web-push is not wired (Danny/Terminal-style push is not in this repo).
- `static/`: `index.html`, `app.css`, `app.js`, `sw.js`, Sky Air tokens, shared motion kit, `logo.svg` (the one logo slot).
- `tests/`: pytest suite. `tools/shots.py` and `tools/shots_compliance.py`: screenshots + one-screen checks (vertical and horizontal overflow) against a running local server; both take optional size/screen filters (see each file's header). Both exit 1 (and name the shots) when any shot overflows, so a run with overflow can no longer pass.
- `design/`: Sky Air tokens/mockups and the shared motion kit as received (PNG mockups are on disk but git-ignored).
- `docs/COMPLIANCE.md`: the compliance gate (a clip can't be Approved until its checklist is fully ticked; reminder only, not legal advice, nothing posts). Wording lives in one constant, `CHECKLIST` in `server.py`. It also lists the small-phone overflow measured before this branch and what fixed it.
- `docs/GO-LIVE.md`: proposed keepalive plist text and rollback. Nothing installed.

Run: `python3 server.py` then open http://127.0.0.1:8505/ . Override the port with `CLIPPING_HUB_PORT`. Test: `python -m pytest -q`.

Synthetic fixtures (no tokens), not production state: `tests/fixtures/post_targets.json`, `tests/fixtures/horror-sample07.json`, `tests/fixtures/samples/sample-a.mp4`, `tests/fixtures/samples/sample07.mp4`. `data/post_targets.json` and `static/samples/` are gitignored so a checkout does not replace a live copy. Public-publish rules and the capability matrix are in `docs/PUBLIC_PUBLISH.md`. The measured baseline on this import is in `docs/TEST_BASELINE.md`. Exact reviewer command on Luis's Mac (no venv in this tree; uses the banking-hub venv, which has pytest + playwright, and installed Google Chrome): `cd <this tree> && CLIPPING_HUB_BROWSER=chrome ~/grok-trading-work/banking-hub/.venv/bin/python -m pytest -q -p no:cacheprovider` (measured: 71 passed). Measured count: 71 tests with playwright installed (a browser engine available), 42 plus 14 skipped without playwright (the 14 real-browser tests skip themselves). Real-browser tests use Chromium by default; set `CLIPPING_HUB_BROWSER=webkit` (or `chrome` for an installed Google Chrome) to pick another engine. If the chosen engine will not launch, those tests FAIL with a message; they no longer fall back to WebKit quietly.

Logo: swap `static/logo.svg` (or point the single `<img id="logo">` in `static/index.html` at a new file). Nothing else references it.


## Approvals queue (`data/approvals.json`)

Frankie writes this file. The hub only records Luis's decision (atomic temp-file-then-rename). Schema:

```json
{
  "version": 1,
  "items": [
    {
      "id": "appr-1",
      "video": "/samples/sample-a.mp4",
      "caption": "Plain-English caption",
      "platforms": ["Clipped Motions YouTube", "TikTok Business", "IG Business", "FB Page"],
      "scheduled_at": "2026-11-07T18:00:00-05:00",
      "status": "pending",
      "note": "",
      "decided_at": null
    }
  ]
}
```

`status`: `pending` | `approved` | `rejected` | `change_requested`.  
`platforms`: only those four names. `video` is a same-origin path (e.g. `/samples/…`); remote platform URLs are not fetched.  
See `data/approvals.example.json`.

## Events (`data/events.json`)

Frankie or jobs **append** events. The hub reads them for the badge list and local alerts:

```json
{
  "version": 1,
  "events": [
    {
      "id": "ev-1",
      "type": "approval_waiting",
      "at": "2026-11-06T10:00:00-05:00",
      "title": "Clip waiting",
      "body": "…",
      "ref": "appr-1"
    }
  ]
}
```

`type`: `approval_waiting` | `post_sent` | `post_scheduled` | `job_failed` | `payout`.  
**Payout events do not change the Revenue card** today (sources stay `$0` / Not connected). Later, a real connected source could sum `payout` events; until then the card stays honest. See `data/events.example.json`.
