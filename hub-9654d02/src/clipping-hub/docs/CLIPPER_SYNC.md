# Clipper → Hub sync (pull-only)

| | Box (Clipper writes) | Mac hub (read-only) |
|--|--|--|
| Shorts | `/workspace/clipping-hub/shorts/<id>/{final.mp4,thumb.png,script.md,meta.json}` | `data/clipper/shorts/<id>/…` |
| Ledger | `/workspace/clipping-hub/ledger/{credits,campaigns,script-queue}.json` | `data/clipper/ledger/…` |

**Flow:** agent packs box dirs → `CopyFromBox` to `~/grok-trading-work/_fc_transfer/clipper-data.tgz` → `tools/pull_clipper_data.sh` extracts into `data/clipper/`.

Hub APIs only **read** `data/clipper`. If Clipper has not written files, loaders return `empty: true` with a reason — never invented balances or campaigns.

Revenue in the UI stays **$0 / Not connected** until a real payout connector exists.
