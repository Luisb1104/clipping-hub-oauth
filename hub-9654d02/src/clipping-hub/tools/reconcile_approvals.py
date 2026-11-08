#!/usr/bin/env python3
"""Fill approvals from the private-proof, promote, and post ledgers.

Dry-run is the default and writes nothing. --apply takes the approvals lock,
copies the file into backups/, then writes. A second apply is a no-op.
A missing synthetic echo is stored as the string label_api_echo, never as a
label switched off. label_user_confirmed is a separate field.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ledger_dedupe as dedupe  # noqa: E402

FIELDS = (
    "status",
    "privacy",
    "youtube_video_id",
    "label_api_echo",
    "label_user_confirmed",
    "label_confirm_source",
    "label_confirmed_at",
)


def _fmt(present, value):
    if not present:
        return "(missing)"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value == "":
        return "''"
    return "'" + str(value) + "'"


def _approvals_path(explicit):
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("CLIPPING_HUB_APPROVALS", "").strip()
    if env:
        return Path(env).expanduser()
    return dedupe.data_dir() / "approvals.json"


def load_approvals(path):
    raw, err = dedupe._read_text(path)
    if err or raw is None:
        raise OSError(err or "ledger_unreadable")
    if not str(raw).strip():
        raise ValueError("approvals_unreadable")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError("approvals_unreadable") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("approvals_unreadable")
    return data


def plan(data, *, data_dir=None):
    """Return (changes, error). changes is a list of {id, fields, item}."""
    changes = []
    for item in data.get("items") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        item_id = str(item.get("id"))[:64]
        facts = dedupe.promote_facts(item_id, data_dir=data_dir)
        if not facts.get("ok"):
            return [], facts.get("reason") or "ledger_corrupt"
        video_id = facts.get("video_id") or ""
        if not video_id:
            continue
        proposed = {}
        if not str(item.get("youtube_video_id") or "").strip():
            proposed["youtube_video_id"] = video_id
        status = str(facts.get("status") or "")
        if status in dedupe._PROMOTE_STATUSES and item.get("status") != status:
            proposed["status"] = status
        privacy = str(facts.get("to_privacy") or "")
        if status == "readback_ok" and privacy in ("public", "private") and item.get("privacy") != privacy:
            proposed["privacy"] = privacy
        # Echo is copied only as a string. null/false/missing is not label-off.
        if facts.get("echo_seen") and isinstance(facts.get("echo"), str):
            if item.get("label_api_echo") != facts["echo"]:
                proposed["label_api_echo"] = facts["echo"]
        if video_id == dedupe.OWNER_VIDEO_ID and item_id == dedupe.OWNER_ITEM_ID:
            if item.get("label_user_confirmed") is not True:
                proposed["label_user_confirmed"] = True
            if item.get("label_confirm_source") != dedupe.OWNER_CONFIRM_SOURCE:
                proposed["label_confirm_source"] = dedupe.OWNER_CONFIRM_SOURCE
            if item.get("label_confirmed_at") != dedupe.OWNER_CONFIRMED_AT:
                proposed["label_confirmed_at"] = dedupe.OWNER_CONFIRMED_AT
        if not proposed:
            continue
        fields = {}
        for name in FIELDS:
            if name not in proposed:
                continue
            present = name in item
            fields[name] = (present, item.get(name), proposed[name])
        changes.append({"id": item_id, "fields": fields, "item": item, "proposed": proposed})
    return changes, None


def format_report(changes):
    if not changes:
        return "no changes\n"
    lines = []
    for change in changes:
        lines.append(change["id"])
        for name in FIELDS:
            if name not in change["fields"]:
                continue
            present, old, new = change["fields"][name]
            lines.append("  %s: %s -> %s" % (name, _fmt(present, old), _fmt(True, new)))
    return "\n".join(lines) + "\n"


def apply_changes(data, changes):
    for change in changes:
        change["item"].update(change["proposed"])
    return data


def _backup(path):
    dest_dir = Path(path).parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(dest_dir, 0o700)
    except OSError:
        pass
    stamp = time.strftime("%Y%m%dT%H%M%S%z")
    dest = dest_dir / ("%s.%s" % (Path(path).name, stamp))
    # A second apply in the same second still needs a distinct name if it wrote.
    n = 0
    while dest.exists():
        n += 1
        dest = dest_dir / ("%s.%s.%d" % (Path(path).name, stamp, n))
    raw, err = dedupe._read_text(path)
    if err or raw is None:
        raise OSError(err or "ledger_unreadable")
    fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, raw.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return dest


def _write(path, data):
    payload = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / (".%s.tmp" % Path(path).name)
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def run(argv):
    args = list(argv)
    apply = "--apply" in args
    approvals = _approvals_path(_grab(args, "--approvals"))
    directory = _grab(args, "--data-dir") or None
    try:
        data = load_approvals(approvals)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    changes, err = plan(data, data_dir=directory)
    if err:
        print(err, file=sys.stderr)
        return 2
    if not apply:
        sys.stdout.write(format_report(changes))
        return 0
    if not changes:
        sys.stdout.write("no changes\n")
        return 0
    import server
    with server.approvals_lock(approvals):
        # Re-read under the lock so the write matches the file we back up.
        try:
            data = load_approvals(approvals)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        changes, err = plan(data, data_dir=directory)
        if err:
            print(err, file=sys.stderr)
            return 2
        if not changes:
            sys.stdout.write("no changes\n")
            return 0
        try:
            _backup(approvals)
            apply_changes(data, changes)
            _write(approvals, data)
        except OSError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    sys.stdout.write(format_report(changes))
    return 0


def _grab(argv, flag):
    if flag not in argv:
        return ""
    i = argv.index(flag)
    return argv[i + 1] if i + 1 < len(argv) else ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv:
        print("Usage: python3 tools/reconcile_approvals.py [--approvals PATH] [--data-dir PATH] [--apply]")
        print("Default is a dry-run. --apply writes approvals.json under the approvals lock after a backup.")
        return 0
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
