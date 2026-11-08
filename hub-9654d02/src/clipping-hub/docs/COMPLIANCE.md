# Compliance gate (Clipping Hub shell)

**This is a reminder checklist, not legal advice.** It does not check anything, does not know any platform's rules, and does not decide whether a clip is allowed. **Nothing posts either way**: ticking everything, approving, or skipping only marks the clip on this computer.

## What it does
- A clip cannot be marked **Approve** until every item on the checklist is ticked for that clip. Until then the Approve button is disabled and the screen says "Finish the checklist first".
- The rule is enforced in two places: the button in the page, and the server. The server rejects an approve request (HTTP 400) unless that clip has the full set of ticks saved, so a hand-made request cannot skip it. The 400 reply carries a short reason, `{"ok": false, "error": "Finish the checklist first"}` (the same words as the page).
- Un-ticking any item after approval moves the clip back to **Waiting** and it has to be completed again.
- Skip, Edit and Move back to waiting do not need the checklist.
- Sample clips use the same gate.
- Ticks are saved per clip in `data/state.json` (the only file the app writes), as a list of item ids under `checks`. The checklist wording is never saved there.

## Where the wording lives
One constant block in `server.py`: `CHECKLIST` (a tuple of `(id, text)` pairs, between the "COMPLIANCE CHECKLIST" and "end of the checklist block" comments). The server sends it to the page in `/api/state`, and the page builds the list from that. To change the wording, edit only that block and restart the server.
- Keep the ids stable. Saved ticks refer to ids; an id that no longer exists is dropped on load, and an approved clip that no longer has every current item ticked goes back to Waiting.
- Adding or removing an item changes what "complete" means for every clip.
- Keep it to four to six items so it fits on one screen at 390 px.

## What the app does not claim
No platform policy, law or rule text is written into the app. The one rules-related item only asks Luis to confirm he checked the current rules himself. Nothing here has been reviewed by a lawyer.

## Layout
- Phone (390 px): a "Checklist · n of N" row on the clip card opens a bottom sheet with the items and a Done button. Esc or tapping outside also closes it. While the sheet is open its fill is fully opaque and the "Add a sample clip / Remove samples" buttons are hidden and not focusable, so nothing shows through behind the sheet text.
- Very short phones (700 px tall or less, e.g. 375x667 and 360x640): the clip card drops its thumbnail (the "SAMPLE · not a real clip" chip stays) and the card is tighter, so it fits above the nav without overlapping the sample buttons. Tests check the card at 360x640, 375x667 and 390x844, and every queue state (1 clip, 3 clips, next clip, 2 and 6 of 6, approved tab, un-ticked, skipped tab, Remove samples) at 360x640 and 375x667 with real clicks.
- Desktop (1440 px): the checklist sits inline in the clip card.
- No screen scrolls.

## Tests
`python -m pytest -q` runs 56 tests with playwright installed (a browser engine available), and 42 plus 14 skipped without playwright (the 14 real-browser tests skip themselves). Real-browser tests use Chromium by default; set `CLIPPING_HUB_BROWSER=webkit` (or `chrome` for an installed Google Chrome) to pick another engine. If the chosen engine will not launch, those tests FAIL with a message; they no longer fall back to WebKit quietly. Measured counts. They cover the server-side approve gate (400 with the reason at 0 to 5 ticks, success at 6), the page gate and un-tick in a real browser, the phone sheet being opaque with the sample buttons hidden while it is open, the disabled pager arrow contrast (3:1 or better, measured from pixels), the Channels screen fitting above the nav at 360x740 and, with all four Connect buttons clicked (chip text "Not connected yet", one line), at 390x844, 375x667, 360x740, 360x640 and 1440x900, and the screenshot tool's overflow check actually detecting overflow.

## Fit on small phones: what was wrong before this branch (measured)
Measured with Playwright WebKit (not Safari.app, not a real device), light and dark (same numbers), with real clicks, on 6bb400b, on 07201d0 and on this branch. "Past the stage" is how far the visible screen's lowest element runs below the area above the nav (the stage clips it, so the page itself never scrolled); "past the card" is how far the clip card's content runs below the card's own bottom edge.
- Channels after clicking all four Connect buttons (07201d0): 20.8 px past the stage at 390x844 (12.8 px into the nav), 24.4 px at 375x667, 81.9 px at 360x640. At 6bb400b the same clicks gave 3.3, 13.9 and 13.2 px. So the 390x844 case was only partly pre-existing: 17.5 px of it came from the longer two-line note and the longer chip text added in 07201d0. Fixed here by the shorter chip text "Not connected yet" (one line) and, at 360x640, tighter Channels rows.
- Queue (identical at 6bb400b and 07201d0, so pre-existing): at 375x667 the card's content ran 11 to 63 px past the card in every state with a clip, and 9 px past the stage after un-ticking an approved clip; at 360x640 it ran 29 to 119 px past the card and 2 to 65 px past the stage. Real clicks on "Add a sample clip" were blocked at both sizes because the card (the pager at 375x667, the "Nothing is posted" line at 360x640) lay on top of the button. Fixed here: under 700 px tall the card drops its thumbnail and is tighter.
- This branch: 0 px past the stage, 0 px past the card, no horizontal overflow, no page scroll and no blocked real click in 104 states (Channels fresh and after four Connects; queue empty, 1 and 3 clips, next clip, 2 and 6 of 6, sheet open, approved, un-ticked, skipped, edit) at 360x640, 375x667, 390x844 and 1440x900. Not checked: real Safari, real devices, landscape, text zoom.
