#!/bin/bash
# Pull-only Clipper → Mac hub mirror. Hub reads data/clipper; never writes back to box.
# Box source (Clipper): /workspace/clipping-hub/{shorts,ledger}
# Mac dest:            <hub>/data/clipper/{shorts,ledger}
#
# Usage (from an agent with CopyFromBox), or when box path is mounted:
#   tools/pull_clipper_data.sh
#   CLIPPER_BOX_ROOT=/workspace/clipping-hub tools/pull_clipper_data.sh
set -euo pipefail
HUB_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${CLIPPING_HUB_CLIPPER_ROOT:-$HUB_ROOT/data/clipper}"
BOX_ROOT="${CLIPPER_BOX_ROOT:-/workspace/clipping-hub}"
STAGE="${CLIPPER_STAGE:-/tmp/clipper-pull-stage}"

mkdir -p "$DEST/shorts" "$DEST/ledger" "$DEST/channels"

# Prefer a staged tarball dropped by the agent (box-pack → CopyFromBox → here)
if [[ -f "${CLIPPER_TGZ:-$HUB_ROOT/../_fc_transfer/clipper-data.tgz}" ]]; then
  TGZ="${CLIPPER_TGZ:-$HUB_ROOT/../_fc_transfer/clipper-data.tgz}"
  rm -rf "$STAGE" && mkdir -p "$STAGE"
  tar -xzf "$TGZ" -C "$STAGE"
  # Accept either stage/{shorts,ledger} or stage/clipping-hub/{shorts,ledger}
  SRC="$STAGE"
  [[ -d "$STAGE/shorts" || -d "$STAGE/ledger" ]] || SRC="$STAGE/clipping-hub"
  if [[ -d "$SRC/shorts" ]]; then
    rsync -a --delete "$SRC/shorts/" "$DEST/shorts/"
  fi
  if [[ -d "$SRC/ledger" ]]; then
    rsync -a --delete "$SRC/ledger/" "$DEST/ledger/"
  fi
  if [[ -d "$SRC/channels" ]]; then
    rsync -a --delete "$SRC/channels/" "$DEST/channels/"
  fi
  echo "pulled from tarball into $DEST"
  exit 0
fi

# Direct copy when box filesystem is visible on this machine (rare)
if [[ -d "$BOX_ROOT/shorts" || -d "$BOX_ROOT/ledger" ]]; then
  [[ -d "$BOX_ROOT/shorts" ]] && rsync -a --delete "$BOX_ROOT/shorts/" "$DEST/shorts/"
  [[ -d "$BOX_ROOT/ledger" ]] && rsync -a --delete "$BOX_ROOT/ledger/" "$DEST/ledger/"
  [[ -d "$BOX_ROOT/channels" ]] && rsync -a --delete "$BOX_ROOT/channels/" "$DEST/channels/"
  echo "pulled from $BOX_ROOT into $DEST"
  exit 0
fi

echo "no Clipper source yet (missing tarball and $BOX_ROOT). Hub will show empty states."
exit 0
