# Platform posting capabilities (Opus / Postiz) — read-only research

Researched via GetDynamicTools + Opus/Postiz schemas. No posts were made.

## Linked accounts (live read)

### Opus (`opusclip_list_social_accounts`)
| Platform | Name | postAccountId | subAccountId |
|----------|------|---------------|--------------|
| YOUTUBE | Clipped Motions | 6aedeb42386c37c006241619 | — |
| YOUTUBE | Clipped Motions Clips | 6aedf5ffb09f11b7595325ed | — |
| TIKTOK_BUSINESS | Clipped Motions | 6aedec214ca796e276002993 | — |
| INSTAGRAM_BUSINESS | Clipped Motions | 6aedebd669f72aca6cb3e519 | 17841414792425881 |
| FACEBOOK_PAGE | Clipped Motions | 6aedec7b69f72aca6cb3e538 | 1462032180320911 |

### Postiz (`integrationList`)
**Empty `[]`.** No connected integrations. Postiz cannot be used as a fallback until Luis connects accounts (new auth). Not built.

## Capability matrix

| Platform | Opus can post? | Opus privacy | Opus AI label API? | Postiz (if connected) | Hub action when AI disclosure on |
|----------|----------------|--------------|--------------------|------------------------|----------------------------------|
| YouTube | Yes | `public` / `private` / `unlisted` (docs: YouTube-only) | No (use Data API `containsSyntheticMedia`) | `public`/`private`/`unlisted`; no AI field | Auto: private → label → public |
| TikTok Business | Yes | **Not documented** for TT; privacy enum is YouTube-only on Publish a Post | No | `SELF_ONLY` etc. + `video_made_with_ai`; **Business video posts discard privacy_level** | **Blocked auto-public**: `needs_manual_label` + push (no reliable private+label via Opus) |
| Instagram | Yes (needs subAccountId) | None in Opus schema | No | post/story only; no privacy; no AI label | **Blocked**: `needs_manual_label` + push |
| Facebook Page | Yes (needs subAccountId) | None in Opus schema | No | post/story; no privacy; no AI label; Postiz has `draft` type | **Blocked**: `needs_manual_label` + push |

## Policy (Luis)

AI disclosure approved ⇒ never auto-post an unlabeled public clip. Platforms without a private/draft mode **and** without a label API are not auto-posted; they are marked `needs_manual_label` and get one push with deep links.
