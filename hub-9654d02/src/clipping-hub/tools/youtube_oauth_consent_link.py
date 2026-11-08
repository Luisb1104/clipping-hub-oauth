#!/usr/bin/env python3
"""Draft a Google OAuth consent URL for Clipping Hub YouTube label step.

Does NOT call Google. Does NOT create an OAuth client. Prints only the URL
(and open items). Safe to run offline once client_id file exists.

Usage:
  python3 tools/youtube_oauth_consent_link.py --channel MAIN
  python3 tools/youtube_oauth_consent_link.py --channel PAID --print-open-items
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import youtube_label_step as yls  # noqa: E402

OPEN_ITEMS = """
Open items (Luis / Google Cloud) — not done by this script:
  1. Enable YouTube Data API v3 on a Google Cloud project
  2. Configure OAuth consent screen; add Luis as test user if Testing
  3. Create OAuth client (Web or Desktop) with redirect:
       {redirect}
  4. Scope: {scope}
  5. Save client id  → {cid_file}  (chmod 600)
  6. Save client secret → {secret_file} (chmod 600)
  7. Open the printed URL, grant access, hub callback stores refresh token
  8. Repeat for the other channel (MAIN vs PAID) if needed
  9. Only then consider CLIP_YOUTUBE_LABEL_STEP=true for a supervised test
""".strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--channel", choices=("MAIN", "PAID"), default="MAIN")
    ap.add_argument("--approval-id", default="consent-draft")
    ap.add_argument("--print-open-items", action="store_true")
    ap.add_argument("--redirect", default=None, help="Override redirect URI")
    args = ap.parse_args(argv)

    if args.print_open_items or not yls.read_client_id():
        print(OPEN_ITEMS.format(
            redirect=args.redirect or yls.DEFAULT_REDIRECT,
            scope=yls.SCOPE,
            cid_file=yls.CLIENT_ID_FILE,
            secret_file=yls.CLIENT_SECRET_FILE,
        ))
        if not yls.read_client_id():
            print("\nNo client_id file yet — not generating a URL.", file=sys.stderr)
            return 2

    name, yt, handle = yls.expected_yt_for_hub_channel(args.channel)
    print(
        f"# Hub channel {args.channel}: {name} ({yt})"
        + (f" · {handle}" if handle else ""),
        file=sys.stderr,
    )
    url, err = yls.build_auth_url(
        channel=args.channel,
        approval_id=args.approval_id,
        redirect_uri=args.redirect,
    )
    if err or not url:
        print("Cannot build URL:", err or "unknown", file=sys.stderr)
        return 1
    print(url)
    print(
        "\n# Draft only. Opening this URL starts Google consent in your browser.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
