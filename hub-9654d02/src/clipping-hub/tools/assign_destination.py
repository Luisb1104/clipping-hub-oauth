#!/usr/bin/env python3
"""Creation-time destination stamp for NEW clips (call from the clip writer before adding items to approvals.json).

  tools/assign_destination.py --in new_items.json > stamped.json      (list of items, or {"items": [...]})

Each item needs `clip_type` (horror | campaign | gta per data/post_targets.json type_routes). Items that already
have `destination`/`destination_error`, or no `clip_type`, pass through unchanged (no reassignment).
Read-only: reads post_targets.json + the synced Opus channels.json; writes only stdout. Never posts.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clipper_data as cd            # noqa: E402
import destination_routing as dr     # noqa: E402
import schedule_hook as sh           # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", help="JSON file (default stdin)")
    ap.add_argument("--targets", help="post_targets.json (default hub data/)")
    ap.add_argument("--channels", help="channels.json (default hub data/clipper/channels/)")
    a = ap.parse_args(argv)
    raw = json.loads(Path(a.inp).read_text() if a.inp else sys.stdin.read())
    items = raw.get("items") if isinstance(raw, dict) else raw
    cfg = sh.load_targets(a.targets)
    chans = cd.load_channels(a.channels)
    out = [dr.assign(i, cfg, chans) for i in (items or [])]
    for i in out:
        if isinstance(i, dict) and i.get("destination_error"):
            print("needs destination: %s (%s)" % (i.get("id"), i["destination_error"]), file=sys.stderr)
    json.dump({"items": out} if isinstance(raw, dict) else out, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
