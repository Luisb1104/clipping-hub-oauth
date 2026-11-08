# YouTube AI label step

**Status:** implemented in code, **flag default OFF**. No live deploy required to land this doc. Autopost stays OFF (`CLIP_AUTOPOST_ENABLED=false`).

## Design

When a clip has `ai_disclosure=true` (default):

1. Hub **Approve** records the decision and sets status **`label_pending`**, `privacy=private`.
2. Job lines (when autopost is later enabled) carry `privacy=private`, `status=label_pending`, plus the platform AI flags.
3. With **`CLIP_YOUTUBE_LABEL_STEP=true`**, that same Approve tap runs the YouTube flow end-to-end:
   - Opus upload as **private**
   - YouTube Data API `videos.update` `part=status` with `containsSyntheticMedia=true` (still private)
   - Re-read `videos.list`/`get` and confirm the flag
   - Then `privacyStatus=public`
4. TikTok + Instagram: hub sends **one** push with deep links after Approve. If the push **succeeds**, TT/IG are marked done (no hub tap). If the push **fails**, status stays `label_pending` and the existing failure alert fires.
5. Public only after labels clear (YouTube by the API step when the flag is on; TT/IG by successful push).

Flag off → steps 3–4 are skipped. Approve still leaves the card in **Label pending** so nothing is treated as public-ready.

## Scope finding (OAuth)

`videos.update` authorizes with any of:

| Scope | Notes |
|-------|--------|
| `https://www.googleapis.com/auth/youtube` | **Scope we request.** Manage your YouTube account. Sufficient for `videos.update` (status / `containsSyntheticMedia` / `privacyStatus`). Note: this scope **also permits** `videos.delete`; this hub **never calls delete**. |
| `https://www.googleapis.com/auth/youtube.force-ssl` | Also listed for `videos.update`; broader wording (edit/delete). Not required beyond `youtube` for our status-only use. |
| `https://www.googleapis.com/auth/youtubepartner` | Content ID / partner assets. Not required. |

`youtube.upload` alone is **not** listed on `videos.update`. We request **`youtube` only** (not force-ssl or partner). PKCE S256; no `include_granted_scopes`.

## Data flow

```
Approve (hub)
  ├─ status → label_pending, privacy → private
  ├─ schedule_hook job (only if CLIP_AUTOPOST_ENABLED) with privacy=private
  ├─ if CLIP_YOUTUBE_LABEL_STEP:
  │    ├─ no token for MAIN/PAID? → redirect OAuth → store refresh → Luis Approves again
  │    ├─ Opus private upload → youtube video id
  │    ├─ videos.update containsSyntheticMedia=true (private)
  │    ├─ re-read confirm
  │    ├─ videos.update privacyStatus=public
  │    └─ on any error: leave private + push alert (fail closed)
  └─ one ntfy: TikTok + IG deep links
       ├─ push ok → tiktok_label_set + instagram_label_set; leave label_pending only if YouTube still waiting
       └─ push fail → stay label_pending + failure alert (no hub tap)
```

## No hub tap for TikTok / Instagram

There is **no** “Labels set” button. TT/IG are marked done when the deep-link push is sent successfully. The hub cannot verify that Luis actually toggled the labels on those apps; the push is the handoff. If ntfy/push fails, status stays `label_pending` and the failure alert fires so Luis can retry Approve later.

## Token storage

- Directory (outside repo): `~/.config/clipping-hub/youtube-oauth/`
- Per channel: `MAIN.json`, `PAID.json` (separate YouTube channels)
- Mode **0600** on files; directory **0700**
- Env overrides: `CLIP_YT_OAUTH_DIR`, `CLIP_YT_CLIENT_ID_FILE`, `CLIP_YT_CLIENT_SECRET_FILE`
- Client id/secret files also outside the repo; **never printed**, never committed
- Refresh token saved once; reused until revoked

## OAuth callback

- Redirect: `http://127.0.0.1:8505/oauth/youtube/callback` (or Tailscale host → same hub port)
- Env: `CLIP_YT_OAUTH_REDIRECT`
- Hub route stores the refresh token and links back to Approvals. Approve again finishes the job.

## Failure modes

| Failure | Behavior |
|---------|----------|
| Flag off | No Google/Opus calls; card stays Label pending |
| Missing OAuth token | Return `oauth_url`; no upload |
| Opus upload fails | Push alert; stay private / label_pending |
| `containsSyntheticMedia` not confirmed | Push alert; stay private |
| Public flip fails | Push alert; stay private |
| Token revoked | Next Approve starts consent again |

## Rollback

1. Keep `CLIP_YOUTUBE_LABEL_STEP` unset/false (default).
2. To remove code: revert the label-step commit; tokens in `~/.config/...` are outside git.
3. Autopost remains OFF independently via `CLIP_AUTOPOST_ENABLED`.

## Open setup items (Luis / Google Cloud)

- [ ] Google Cloud project with **YouTube Data API v3** enabled
- [ ] OAuth 2.0 **Desktop** or **Web** client ID (redirect = hub callback URL)
- [ ] OAuth consent screen (External or Internal); add Luis as test user while in Testing
- [ ] Scope on consent: `https://www.googleapis.com/auth/youtube` only
- [ ] Write client id → `~/.config/clipping-hub/youtube-oauth/client_id` (mode 600)
- [ ] Write client secret → `~/.config/clipping-hub/youtube-oauth/client_secret` (mode 600)
- [ ] Run `tools/youtube_oauth_consent_link.py` **only when ready** (prints auth URL; does not call Google until Luis opens it)
- [ ] Grant once per channel (MAIN, then PAID) via Approve → consent
- [ ] Set `CLIP_YOUTUBE_LABEL_STEP=true` in the LaunchAgent **only after** tokens exist and Luis green-lights a live test
- [ ] Confirm Tailscale/localhost redirect URI is listed on the OAuth client

## Related

- `docs/AUTOPOST_HOOK.md` — job JSONL; autopost flag
- `youtube_label_step.py` — implementation
- `tools/youtube_oauth_consent_link.py` — consent URL draft helper (no network by default)

## Opus private upload (flag ON)

On Approve (AI disclosure), the hub calls Opus `POST /api/post-tasks` (MCP:
`opusclip_create_post_task`) with `privacy=private`, routed
`postAccountId` / optional `subAccountId` from `data/post_targets.json`, and
the clip's `projectId` / `clipId`. Title and description are unchanged.

### YouTube videoId finding

The Publish-a-Post response returns **`data.postId` only** — not a YouTube
`videoId` (see help.opus.pro Publish a Post; MCP schema has no videoId field).
`opusclip_list_scheduled_posts` documents **`post_url`** (platform permalink)
once the platform confirms. The hub therefore:

1. Accepts `videoId` / `youtubeVideoId` if Opus ever returns them
2. Else parses `post_url` / YouTube watch or shorts URLs for the id
3. Else **fail closed** (`opus_no_video_id` alert) — no public flip

No MCP tools that post are invoked from tests; HTTP is injected/mocked.

### Create ledger state machine

Per `job_id::youtube:create` in `data/post_ledger.jsonl` (flocked begin):

| status | begin() | new POST? | notes |
|--------|---------|-----------|-------|
| *(absent)* | ok | yes | first attempt |
| `in_flight` | refuse | no | fresh lock; if stale → reconcile only |
| `timeout_pending` | refuse | no | create timed out; reconcile exact clipId+projectId+account; never re-POST |
| `create_error` | refuse | no | non-timeout create / missing postId; one deduped alert; requires authorized unstick → `failed` before any new POST |
| `done` | refuse | no | terminal success (has opus_post_id) |
| `failed` | ok | yes | only after authorized `/api/post-ledger/unstick` |

Approve / tick share an `approvals.json` flock for read-modify-write. HTTP tick `force` accepts only `true`/`1` (bool True); authorized force still respects the 5-minute shared rate cap.
