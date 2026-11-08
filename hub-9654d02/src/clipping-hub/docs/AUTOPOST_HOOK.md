# Approve → schedule post hook (stub)

**Status:** stub only. Flag defaults **OFF**. Nothing is posted to Postiz, YouTube, TikTok, IG, FB, or any other platform.

## Flag

| Env | Default | Meaning |
|-----|---------|---------|
| `CLIP_AUTOPOST_ENABLED` | `false` | Must be `true` / `1` / `yes` / `on` for the stub to run. Anything else (or unset) = off. |

When off, Approvals behave as today: decide `approved` leaves `status: "approved"` and no job file is written.

When on, a successful approve (`op=decide`, `status=approved`, first time) also:

1. Appends one job line to the jobs file (below).
2. Sets that item’s `status` to `"scheduled"` in `data/approvals.json`.

Reject / change_requested never touch the jobs file.

## Jobs file (Clipper input)

| | |
|--|--|
| **Path** | `data/autopost_jobs.jsonl` |
| **Override** | `CLIPPING_HUB_AUTOPOST_JOBS` |
| **Format** | Append-only JSON Lines (one object per line, UTF-8) |
| **Writer** | Clipping Hub `schedule_hook.on_approved` (this stub) |
| **Reader** | Clipper (or a future poster). Hub never reads this file back. |

### Fields (version 1)

| Field | Type | Set by hub stub | Notes for Clipper |
|-------|------|-----------------|-------------------|
| `version` | int | yes (`1`) | Bump only with a documented schema change |
| `op` | string | yes (`schedule_post`) | Only op the hub emits |
| `id` | string | yes | Same as approvals item `id` |
| `video` | string | yes | Local path or URL from the approval row |
| `caption` | string | yes | Caption text |
| `platforms` | string[] | yes | Subset of hub platforms (YouTube / TikTok / IG / FB labels) |
| `scheduled_at` | string | yes | Requested time from Frankie (may be empty) |
| `approved_at` | string | yes | From `decided_at` |
| `queued_at` | string | yes | When the stub wrote the line |
| `status` | string | yes (`queued`) | Clipper may set `posting` / `posted` / `failed` in its own store; do not rewrite hub lines in place unless you own the file |
| `source` | string | yes (`clipping-hub-approvals`) | |
| `poster` | null | yes | Stub leaves `null`. Clipper sets e.g. `"postiz"` when wiring a real poster |
| `remote_ids` | object | yes (`{}`) | Clipper fills platform → remote id after a real post |
| `error` | null/string | yes (`null`) | Clipper sets on failure |

### Example line

```json
{"version":1,"op":"schedule_post","id":"a1","video":"/clips/friday.mp4","caption":"Friday reel","platforms":["TikTok Business"],"scheduled_at":"2026-11-07T18:00:00-05:00","approved_at":"2026-11-06T11:40:00-0500","queued_at":"2026-11-06T11:40:00-0500","status":"queued","source":"clipping-hub-approvals","poster":null,"remote_ids":{},"error":null}
```

## What Clipper plugs in later

1. Tail `data/autopost_jobs.jsonl` (or copy-out) for new `op=schedule_post` rows with `status=queued`.
2. Call your poster (Postiz / YouTube / …) **outside this repo’s server process**.
3. Record remote ids / errors in Clipper’s own state (preferred). Do not teach `server.py` to call Postiz.
4. Optionally append a hub `events.json` row (`post_scheduled` / `post_sent` / `job_failed`) via the existing authenticated `POST /api/events` path.

## Guarantees

- Default off.
- No Postiz / YouTube / network imports in `schedule_hook.py`.
- Hub process does not upload or publish.


## Routing (MAIN vs PAID)

Config file: `data/post_targets.json` (not hardcoded).

| Condition | Target | Notes |
|-----------|--------|-------|
| `is_ad == true` **or** `campaign_id` set | **PAID** | Append `#ad` if missing; `paid_promotion=true` |
| otherwise | **MAIN** | `paid_promotion=false` |

Job line extra fields: `target`, `channel_id` (YouTube UC…), `opus_post_account_id`, `paid_promotion`, `poster` (`opus`), `hashtags`, `campaign_id`, `is_ad`.

`CLIP_AUTOPOST_ENABLED` still defaults **off**. Routing is computed for the Approvals UI even when the flag is off.


## AI disclosure

Every `schedule_post` job line includes:

| field | meaning |
|-------|---------|
| `ai_disclosure` | bool, default **true** (from `meta.json` / approval item) |
| `ai_platform.youtube.altered_synthetic` | true when disclosure on |
| `ai_platform.tiktok.ai_generated` | true when disclosure on |
| `ai_platform.instagram.ai_info_label` | true when disclosure on |

Also flat mirrors: `youtube_altered_synthetic`, `tiktok_ai_generated`, `instagram_ai_info_label`.

**Never** write AI wording into `title` or `caption`. Platform labels are separate fields for the poster.

## AI disclosure / label_pending

Jobs with `ai_disclosure=true` (default) get `privacy=private` and
`status=label_pending`. Platform AI flags stay on the job line; never in
title/caption. Public only after the YouTube label step (flag
`CLIP_YOUTUBE_LABEL_STEP`, default off) and a successful TT/IG deep-link
push (no hub tap). See `docs/YOUTUBE_LABEL_STEP.md`.

