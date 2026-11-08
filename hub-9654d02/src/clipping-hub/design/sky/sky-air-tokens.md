# Sky Air design tokens (DRAFT for dev)

Status: **draft mockup tokens, not a built feature.** Every value below is copied by script from `sky-air-tokens.css`, which is the same file the mockups are rendered from. Nothing here is connected to an app.

Files: `sky-air-tokens.css` (drop-in custom properties under `[data-theme=light]` and `[data-theme=dark]`), `sky.css` (component CSS of the first set), `onescreen/sky1.css` (one-screen overrides), `sky.py`, `onescreen/sky1.py` (generators), `contrast.txt` and `onescreen/contrast_pairs.json` (contrast results).

## Shared (both themes)

| Token | Value |
|---|---|
| `--font-sans` | `Inter,"Helvetica Neue",Arial,system-ui,sans-serif` |
| `--fs-eyebrow` | `11px` |
| `--fs-nav-label` | `11px` |
| `--fs-micro` | `11px` |
| `--fs-banner` | `11px` |
| `--fs-chip` | `11px` |
| `--fs-small` | `13px` |
| `--fs-body` | `14px` |
| `--fs-button` | `15px` |
| `--fs-h3` | `20px` |
| `--fs-h2` | `26px` |
| `--fs-h1` | `34px` |
| `--fw-regular` | `500` |
| `--fw-bold` | `700` |
| `--fw-heavy` | `800` |
| `--fw-black` | `900` |
| `--ls-eyebrow` | `.14em` |
| `--sp-1` | `4px` |
| `--sp-2` | `8px` |
| `--sp-3` | `12px` |
| `--sp-4` | `16px` |
| `--sp-5` | `20px` |
| `--sp-6` | `24px` |
| `--sp-8` | `32px` |
| `--r-card` | `26px` |
| `--r-inner` | `18px` |
| `--r-thumb` | `22px` |
| `--r-pill` | `999px` |
| `--r-phone` | `44px` |
| `--r-mac` | `22px` |
| `--tap` | `44px` |
| `--btn-h` | `50px` |
| `--panel-blur` | `20px` |
| `--nav-h` | `64px` |
| `--nav-item-h` | `52px` |
| `--toggle-seg-w` | `44px` |
| `--toggle-seg-h` | `44px` |
| `--toggle-pad` | `3px` |
| `--motion-fast` | `150ms` |
| `--motion-ease` | `cubic-bezier(.2,.8,.2,1)` |
| `--frame-w-phone` | `390px` |
| `--frame-h-phone` | `844px` |
| `--frame-w-mac` | `1440px` |
| `--frame-h-mac` | `900px` |
| `--card-row-card-w` | `148px` |
| `--card-row-card-h` | `196px` |
| `--card-row-gap` | `12px` |
| `--card-row-peek` | `48px` |
| `--dot-size` | `7px` |
| `--dot-active-w` | `22px` |
| `--dot-gap` | `6px` |
| `--strip-chip-h` | `44px` |
| `--strip-gap` | `8px` |
| `--pool-total-fs` | `38px` |
| `--pool-total-fs-mac` | `40px` |
| `--pool-total-fw` | `900` |
| `--pool-line-fs` | `12.5px` |
| `--pool-row-h` | `56px` |
| `--ribbon-fs` | `11px` |
| `--ribbon-h` | `30px` |

## Colour and surface tokens (light vs dark)

| Token | Light | Dark |
|---|---|---|
| `--page-bg` | `#dbe3f4` | `#060919` |
| `--bg-grad` | `radial-gradient(460px 320px at 100% 0%,rgba(167,139,250,.5),transparent),radial-gradient(460px 340px at 0% 55%,rgba(125,190,255,.5),transparent),radial-gradient(420px 300px at 90% 100%,rgba(255,190,225,.5),transparent),linear-gradient(180deg,#e6f0ff,#efe8ff)` | `radial-gradient(460px 340px at 100% 0%,rgba(124,92,255,.42),transparent),radial-gradient(460px 360px at 0% 55%,rgba(52,96,214,.34),transparent),radial-gradient(420px 300px at 90% 100%,rgba(176,84,200,.26),transparent),linear-gradient(180deg,#0b1030,#150f3d)` |
| `--frame-border` | `rgba(255,255,255,.9)` | `rgba(255,255,255,.14)` |
| `--frame-shadow` | `0 20px 50px rgba(80,90,160,.25)` | `0 20px 50px rgba(0,0,0,.5)` |
| `--panel-fill` | `rgba(255,255,255,.55)` | `rgba(255,255,255,.08)` |
| `--panel-border` | `rgba(255,255,255,.9)` | `rgba(255,255,255,.16)` |
| `--panel-shadow` | `0 10px 30px rgba(80,90,160,.14)` | `0 10px 30px rgba(0,0,0,.35)` |
| `--inner-fill` | `rgba(255,255,255,.55)` | `rgba(255,255,255,.06)` |
| `--text-1` | `#1b2140` | `#f1f3ff` |
| `--text-2` | `#3b4470` | `#d0d5f4` |
| `--text-3` | `#454e7a` | `#bcc3e8` |
| `--accent-1` | `#4553e0` | `#5a63f0` |
| `--accent-2` | `#6a45dc` | `#7a55e8` |
| `--accent-grad` | `linear-gradient(135deg,#4553e0,#6a45dc)` | `linear-gradient(135deg,#5a63f0,#7a55e8)` |
| `--accent-text` | `#ffffff` | `#ffffff` |
| `--accent-shadow` | `0 10px 24px rgba(79,92,224,.35)` | `0 10px 24px rgba(90,99,240,.35)` |
| `--accent-ink` | `#4338ca` | `#c7c9ff` |
| `--ok-text` | `#086245` | `#6ee7b7` |
| `--ok-line` | `rgba(8,98,69,.45)` | `rgba(110,231,183,.5)` |
| `--ok-fill` | `rgba(12,138,98,.10)` | `rgba(110,231,183,.12)` |
| `--warn-text` | `#7a4a00` | `#fcd34d` |
| `--warn-line` | `rgba(138,82,0,.45)` | `rgba(252,211,77,.5)` |
| `--warn-fill` | `rgba(251,191,36,.22)` | `rgba(252,211,77,.12)` |
| `--bad-text` | `#b3203d` | `#ffbfc7` |
| `--bad-line` | `rgba(179,32,61,.45)` | `rgba(255,191,199,.5)` |
| `--bad-fill` | `rgba(251,113,133,.14)` | `rgba(251,113,133,.14)` |
| `--neutral-text` | `#3b4470` | `#d0d5f4` |
| `--neutral-line` | `rgba(59,68,112,.55)` | `rgba(208,213,244,.5)` |
| `--neutral-fill` | `transparent` | `transparent` |
| `--disabled-fill` | `rgba(27,33,64,.06)` | `rgba(255,255,255,.05)` |
| `--disabled-text` | `#454e7a` | `#bcc3e8` |
| `--disabled-line` | `rgba(27,33,64,.28)` | `rgba(255,255,255,.22)` |
| `--nav-fill` | `rgba(255,255,255,.7)` | `rgba(20,24,66,.62)` |
| `--nav-border` | `rgba(255,255,255,.9)` | `rgba(255,255,255,.16)` |
| `--nav-shadow` | `0 12px 34px rgba(80,90,160,.25)` | `0 12px 34px rgba(0,0,0,.45)` |
| `--nav-active-bg` | `#1b2140` | `linear-gradient(135deg,#5a63f0,#7a55e8)` |
| `--nav-active-text` | `#ffffff` | `#ffffff` |
| `--toggle-fill` | `rgba(255,255,255,.7)` | `rgba(20,24,66,.62)` |
| `--toggle-border` | `rgba(255,255,255,.9)` | `rgba(255,255,255,.16)` |
| `--toggle-on-bg` | `#1b2140` | `linear-gradient(135deg,#5a63f0,#7a55e8)` |
| `--toggle-on-fg` | `#ffffff` | `#ffffff` |
| `--toggle-off-fg` | `#3b4470` | `#d0d5f4` |
| `--hatch-line` | `rgba(27,33,64,.10)` | `rgba(255,255,255,.12)` |
| `--dash-line` | `rgba(27,33,64,.30)` | `rgba(255,255,255,.28)` |
| `--thumb-1` | `linear-gradient(160deg,#8fd0ff,#8b9bff)` | `linear-gradient(160deg,#4a78e8,#6a4cd8)` |
| `--thumb-2` | `linear-gradient(160deg,#c3a6ff,#ff9fd0)` | `linear-gradient(160deg,#8a54e0,#c0508a)` |
| `--thumb-3` | `linear-gradient(160deg,#9be3ff,#b9a4ff)` | `linear-gradient(160deg,#3a8ad6,#6558d8)` |
| `--thumb-label-bg` | `rgba(10,14,40,.88)` | `rgba(5,8,28,.88)` |
| `--thumb-label-text` | `#ffffff` | `#ffffff` |
| `--cap-fill` | `rgba(255,255,255,.7)` | `rgba(255,255,255,.07)` |
| `--cap-border` | `rgba(255,255,255,.95)` | `rgba(255,255,255,.16)` |
| `--cap-text` | `#1b2140` | `#e4e7ff` |
| `--cap-key` | `#4338ca` | `#b9bcff` |
| `--banner-amber` | `#fbbf24` | `#fbbf24` |
| `--banner-bg` | `#15111d` | `#15111d` |

## Specs in plain words
- **Fonts:** Inter (fallbacks Helvetica Neue, Arial, system-ui). **Minimum font size in every mockup is 11px** (measured from the rendered text). Scale: eyebrow/chip/nav label/micro label/banner/ribbon 11px (eyebrow uppercase, .14em tracking, weight 800), small 13px, body 14px, button 15px/800, h3 20px/800, h2 26px/800, h1 34px/800 (44px on Mac). Big numbers 26px/900. Pooled total 38px (phone) / 40px (Mac), weight 900.
- **Panels (glass):** fill `--panel-fill`, 1px border `--panel-border`, `backdrop-filter: blur(20px)`, shadow `--panel-shadow`, radius 26px (inner boxes 18px, thumbnails 22px).
- **Spacing scale:** 4 / 8 / 12 / 16 / 20 / 24 / 32 px.
- **Tap targets:** minimum 44px everywhere (`--tap`); primary buttons 50px (54px for the main Overview action), pill radius.
- **Banner:** dark pill `--banner-bg` with `--banner-amber` (#fbbf24) text and border, 11px/900, .14em tracking; same in light and dark. The CSS uses the tokens, not literals.
- **Nav pill (phone):** floating, 14px from left/right, 16px above bottom, 6px padding, pill radius, blur 20px, items 52px high, icon 19px over an 11px bold label, active item filled with `--nav-active-bg`.
- **Nav pill (Mac):** centered top pill, 44px tabs, 14px bold labels.
- **Light/Dark toggle:** segmented pill top-right of the header. Track `--toggle-fill` + `--toggle-border`, 3px padding, two 44x44 segments (sun, moon), active segment `--toggle-on-bg` / `--toggle-on-fg`; on Mac the segments also show the words Light / Dark.
- **Chips:** 11px/800, pill, 1px border. Success, warn, danger use `ok-*`, `warn-*`, `bad-*`; neutral / Unverified / Not connected / Later / Planned use dashed borders.
- **Disabled buttons:** `--disabled-*` tokens, dashed border, no shadow. Their text meets 4.5:1 like everything else.
- **Hatched "No data yet" placeholder:** 135deg stripes of `--hatch-line` (6px on, 7px off), dashed `--dash-line` border, no line or curve. This block contains no text and is not scored.
- **Motion note:** only `transform` and `opacity` should animate, about 150ms (`--motion-fast`, `--motion-ease`). Honor `prefers-reduced-motion` (the token file ends with a reduced-motion rule). The mockups themselves have no animation.

## Toggle behavior (SUGGESTION, not built, not decided)
1. **Default:** follow the device setting via `prefers-color-scheme`.
2. **Saved choice:** if Luis taps Light or Dark, store it (for example `localStorage` key `theme`) and use it instead of the device setting. A third state "Auto" could clear the saved value.
3. **No flash on load:** set `data-theme` on `<html>` from a tiny inline script in `<head>` before first paint (read saved choice, else `matchMedia('(prefers-color-scheme: dark)')`), and set `color-scheme` so native controls match.
4. Switching should not animate layout; at most a 150ms opacity cross-fade, and none with reduced motion.

## One-screen layout tokens (`onescreen/`)
Frame sizes are fixed so nothing scrolls: phone app frame `--frame-w-phone` x `--frame-h-phone` = 390 x 844 (nav pill inside), Mac app frame 1440 x 900. The banner and caption block sit outside the frame. Content that does not fit is cut from the design, never scrolled.
- **Card row (swipeable, with peek):** card `--card-row-card-w` x `--card-row-card-h` = 148 x 196 (120 high in the pooled Overview), gap `--card-row-gap` 12px, about `--card-row-peek` 48px of the next card shows; the row bleeds to the right edge of the frame.
- **Dot indicator:** `--dot-size` 7px, active `--dot-active-w` 22px pill in `--accent-1`, gap `--dot-gap` 6px, inactive dots `--dash-line`.
- **Chip strip (platform picker):** four equal segments, `--strip-chip-h` 44px, gap `--strip-gap` 8px; selected uses `--nav-active-bg` / `--nav-active-text`.
- **Platform status strip (Overview, non-pooled):** four glass tiles at least 48px high; the YouTube tile is wider (1.4fr) so "Planned · first" fits at 11px.
- **Pinned action panel (Queue):** glass panel anchored above the nav pill.

## Pooled revenue card tokens
- **Card:** a normal glass panel (`--panel-*`, `--r-card`), padding 14px 16px (18px 20px on Mac). Whole card is a tap/click target with a chevron hint.
- **Total typography:** `--pool-total-fs` 38px (Mac `--pool-total-fs-mac` 40px), weight `--pool-total-fw` 900, tracking -.03em, colour `--text-1`. Supporting line `--pool-line-fs` 12.5px in `--text-2`. Hint line 12.5px/800 in `--accent-ink`.
- **Rows:** `--pool-row-h` 56px minimum, 36px neutral glyph tile, name 15px/800, status chip below the name, amount 16px/900 on the right; total row 18px/900 with a 2px top rule.
- **EXAMPLE stamp:** pill 11px/900 using `--warn-text`, `--warn-line`, `--warn-fill`, dashed border; placed before every example figure.
- **Ribbon (demo only):** full-width bar across the top of the card, height `--ribbon-h` 30px, 11px/900 with .12em tracking, background `--banner-bg`, text `--banner-amber` (reuses the banner tokens), text "EXAMPLE DATA, NOT REAL REVENUE".

## Contrast (computed by script)
**Measure used everywhere in this document:** WCAG 2.x contrast ratio from relative luminance, (L1+0.05)/(L2+0.05). Text colour is alpha-composited over each background pixel. The reported value is the **worst case (lowest) over sampled pixels directly behind the text**, taken from a screenshot of the real rendered mockup with the text made transparent (so panels, blur, gradients, pills and buttons are all included). Items under a CSS transform (the rotated thumbnails) are sampled only on pixels the glyphs actually cover. Body-text target: AA 4.5:1 for every text. The large-text allowance (3:1 for text >= 24px, or >= 18.66px and weight >= 700) is **not used for pass/fail**: all text in the mockups passes 4.5:1.

Raw results: `onescreen/contrast_pairs.json` (every one of the 1060 text items in all one-screen renders, with its own ratio) and `contrast.txt`. **Lowest ratio of any text in any mockup: 4.73:1.**

### A. Token-level pairs (worst case over 800 gradient samples per theme)


**Light**

| Pair | Worst ratio | AA 4.5 |
|---|---|---|
| text-1 on panel (worst of 800 backdrop samples) | 12.44:1 | PASS |
| text-1 on page gradient (no panel) | 9.13:1 | PASS |
| text-2 on panel (worst of 800 backdrop samples) | 7.41:1 | PASS |
| text-2 on page gradient (no panel) | 5.44:1 | PASS |
| text-3 on panel (worst of 800 backdrop samples) | 6.34:1 | PASS |
| text-3 on page gradient (no panel) | 4.65:1 | PASS |
| ok-text on ok chip fill over panel | 5.22:1 | PASS |
| warn-text on warn chip fill over panel | 5.50:1 | PASS |
| bad-text on bad chip fill over panel | 4.67:1 | PASS |
| neutral-text on neutral chip fill over panel | 7.41:1 | PASS |
| cap-text on caption block | 13.47:1 | PASS |
| cap-key on caption block | 6.78:1 | PASS |
| accent-text on accent-1 | 5.89:1 | PASS |
| accent-text on accent-2 | 6.00:1 | PASS |
| accent-ink (eyebrows on caption) | 6.78:1 | PASS |
| nav-active-text on #1b2140 | 15.69:1 | PASS |
| toggle-off-fg on toggle track | 8.02:1 | PASS |
| banner-amber on banner-bg (banner text) | 11.13:1 | PASS |
| thumb-label-text on thumb-label-bg over every thumbnail gradient stop | 14.75:1 | PASS |

**Dark**

| Pair | Worst ratio | AA 4.5 |
|---|---|---|
| text-1 on panel (worst of 800 backdrop samples) | 7.76:1 | PASS |
| text-1 on page gradient (no panel) | 9.70:1 | PASS |
| text-2 on panel (worst of 800 backdrop samples) | 5.92:1 | PASS |
| text-2 on page gradient (no panel) | 7.41:1 | PASS |
| text-3 on panel (worst of 800 backdrop samples) | 4.94:1 | PASS |
| text-3 on page gradient (no panel) | 6.18:1 | PASS |
| ok-text on ok chip fill over panel | 4.51:1 | PASS |
| warn-text on warn chip fill over panel | 4.75:1 | PASS |
| bad-text on bad chip fill over panel | 4.76:1 | PASS |
| neutral-text on neutral chip fill over panel | 5.92:1 | PASS |
| cap-text on caption block | 7.22:1 | PASS |
| cap-key on caption block | 4.92:1 | PASS |
| accent-text on accent-1 | 4.69:1 | PASS |
| accent-text on accent-2 | 4.89:1 | PASS |
| accent-ink (eyebrows on caption) | 5.56:1 | PASS |
| nav-active-text on #5a63f0 | 4.69:1 | PASS |
| nav-active-text on #7a55e8 | 4.89:1 | PASS |
| toggle-off-fg on toggle track | 10.04:1 | PASS |
| banner-amber on banner-bg (banner text) | 11.13:1 | PASS |
| thumb-label-text on thumb-label-bg over every thumbnail gradient stop | 17.67:1 | PASS |

### B. Every text/background pair that appears in the mockups (grouped by theme, element role, colour, size, weight; worst case across all screens)

Role = element class chain, innermost first (e.g. `chip<pn<prow` = a chip inside a pooled-row name). "Count" = how many text items share the pair.


**Light**

| Role | Colour | Size/weight | Worst ratio | Count | Example text (screen) | Pass (need) |
|---|---|---|---|---|---|---|
| `chip<row<glass` | `rgb(179, 32, 61)` | 11px/800 | 4.96:1 | 1 | EXAMPLE · Rose (phone-flags) | PASS (4.5) |
| `blk<in<phone` | `rgb(122, 74, 0)` | 12.5px/800 | 5.03:1 | 3 | Resolve open flags first (phone-flags) | PASS (4.5) |
| `btn<in<phone` | `rgb(69, 78, 122)` | 15px/800 | 5.07:1 | 2 | Approve all (phone-overview) | PASS (4.5) |
| `chip<pat<glass` | `rgb(179, 32, 61)` | 11px/800 | 5.13:1 | 1 | EXAMPLE · Mismatch (phone-earnings) | PASS (4.5) |
| `chip<fl<glass` | `rgb(179, 32, 61)` | 11px/800 | 5.17:1 | 3 | EXAMPLE · Rose (mac-more) | PASS (4.5) |
| `btn<bt<glass` | `rgb(179, 32, 61)` | 14px/800 | 5.23:1 | 1 | Reject (phone-queue) | PASS (4.5) |
| `chip<pat<m2` | `rgb(179, 32, 61)` | 11px/800 | 5.31:1 | 1 | EXAMPLE · Mismatch (mac-more) | PASS (4.5) |
| `blk<glass<g3` | `rgb(122, 74, 0)` | 12.5px/800 | 5.55:1 | 2 | Resolve open flags first (mac-overview) | PASS (4.5) |
| `chip<pn<prow` | `rgb(8, 98, 69)` | 11px/800 | 5.65:1 | 1 | Connected (example) (phone-pooled-example) | PASS (4.5) |
| `chip<pat<glass` | `rgb(8, 98, 69)` | 11px/800 | 5.78:1 | 1 | EXAMPLE · Match (phone-earnings) | PASS (4.5) |
| `btn<btns<glass` | `rgb(255, 255, 255)` | 15px/800 | 5.91:1 | 2 | Review one by one (mac-overview) | PASS (4.5) |
| `btn<glass<in` | `rgb(255, 255, 255)` | 15px/800 | 5.92:1 | 2 | Next: connect a channel (phone-earnings-empty) | PASS (4.5) |
| `btn<in<phone` | `rgb(255, 255, 255)` | 16px/900 | 5.93:1 | 2 | Review one by one (phone-overview-pooled) | PASS (4.5) |
| `reel<mhdr<in` | `rgb(255, 255, 255)` | 16px/900 | 5.97:1 | 3 | C (mac-more) | PASS (4.5) |
| `reel<hdr<in` | `rgb(255, 255, 255)` | 16px/900 | 5.99:1 | 12 | C (phone-connect) | PASS (4.5) |
| `chip<pat<m2` | `rgb(8, 98, 69)` | 11px/800 | 6.02:1 | 1 | EXAMPLE · Match (mac-more) | PASS (4.5) |
| `chip<chips<glass` | `rgb(122, 74, 0)` | 11px/800 | 6.03:1 | 1 | Flag · music (EXAMPLE) (phone-queue) | PASS (4.5) |
| `chip<row<glass` | `rgb(122, 74, 0)` | 11px/800 | 6.04:1 | 1 | EXAMPLE · Amber (phone-flags) | PASS (4.5) |
| `exl<ptot<glass` | `rgb(122, 74, 0)` | 11px/900 | 6.04:1 | 1 | EXAMPLE (phone-pooled-example) | PASS (4.5) |
| `dotrow<in<phone` | `rgb(59, 68, 112)` | 11.5px/700 | 6.05:1 | 3 | ‹ (phone-queue) | PASS (4.5) |
| `exl<pa<prow` | `rgb(122, 74, 0)` | 11px/900 | 6.06:1 | 2 | EXAMPLE (phone-pooled-example) | PASS (4.5) |
| `chip<rowh<in` | `rgb(59, 68, 112)` | 11px/800 | 6.07:1 | 1 | Example clip 2 of 3 (phone-queue) | PASS (4.5) |
| `btn<bt<glass` | `rgb(69, 78, 122)` | 14px/800 | 6.11:1 | 1 | Approve (phone-queue) | PASS (4.5) |
| `pwr<in<phone` | `rgb(59, 68, 112)` | 11px/400 | 6.14:1 | 1 | Planned tools (not connected): OpusClip · Postiz · TubeAlfred · Remoti (phone-costs) | PASS (4.5) |
| `chip<fl<glass` | `rgb(122, 74, 0)` | 11px/800 | 6.15:1 | 3 | EXAMPLE · Amber (mac-overview) | PASS (4.5) |
| `k<rowh<in` | `rgb(59, 68, 112)` | 11px/800 | 6.28:1 | 2 | Example clips (phone-overview-pooled) | PASS (4.5) |
| `safe<in<phone` | `rgb(59, 68, 112)` | 11.5px/500 | 6.33:1 | 3 | Approve = send to Postiz as a draft only (phone-connect) | PASS (4.5) |
| `btn<glass<in` | `rgb(69, 78, 122)` | 15px/800 | 6.34:1 | 1 | Approve batch (phone-queue) | PASS (4.5) |
| `sub<in<phone` | `rgb(59, 68, 112)` | 13px/400 | 6.42:1 | 2 | Example warnings to fix before approving (phone-flags) | PASS (4.5) |
| `swp<rowh<in` | `rgb(59, 68, 112)` | 12px/800 | 6.54:1 | 2 | swipe › (phone-overview) | PASS (4.5) |
| `cap` | `rgb(67, 56, 202)` | 11px/700 | 6.56:1 | 30 | What you're looking at: (mac-more) | PASS (4.5) |
| `hl<in<phone` | `rgb(59, 68, 112)` | 13.5px/700 | 6.63:1 | 2 | · Example: ~30 sec (phone-overview) | PASS (4.5) |
| `blk<glass<in` | `rgb(122, 74, 0)` | 12.5px/800 | 6.63:1 | 1 | Resolve open flags first (phone-queue) | PASS (4.5) |
| `btn<btns<glass` | `rgb(69, 78, 122)` | 15px/800 | 6.64:1 | 2 | Approve all (mac-overview) | PASS (4.5) |
| `reel<hdr<in` | `rgb(59, 68, 112)` | 11.5px/400 | 6.77:1 | 12 | Planned helper (phone-connect) | PASS (4.5) |
| `phint<glass<g3` | `rgb(67, 56, 202)` | 12.5px/800 | 6.93:1 | 1 | Click for per-platform split (mac-overview-pooled) | PASS (4.5) |
| `phint<glass<in` | `rgb(67, 56, 202)` | 12.5px/800 | 6.96:1 | 1 | Tap for per-platform split (phone-overview-pooled) | PASS (4.5) |
| `pwr<in<mac` | `rgb(59, 68, 112)` | 11px/400 | 7.68:1 | 3 | Planned tools (not connected): OpusClip · Postiz · TubeAlfred · Remoti (mac-more) | PASS (4.5) |
| `k<g3<in` | `rgb(59, 68, 112)` | 11px/800 | 7.68:1 | 1 | Platforms (mac-overview) | PASS (4.5) |
| `k<glass<in` | `rgb(59, 68, 112)` | 11px/800 | 7.89:1 | 6 | Earnings · by platform (mac-more) | PASS (4.5) |
| `sub<glass<in` | `rgb(59, 68, 112)` | 13px/400 | 7.89:1 | 3 | Example shape only. No real revenue yet. (phone-costs) | PASS (4.5) |
| `glass<in<phone` | `rgb(59, 68, 112)` | 15px/400 | 7.89:1 | 3 | Earnings will show up here once a channel is connected and its revenue (phone-earnings-empty) | PASS (4.5) |
| `glass<in<phone` | `rgb(59, 68, 112)` | 13px/400 | 7.89:1 | 2 | YouTube may limit monetization of clips from someone else’s video unle (phone-flags) | PASS (4.5) |
| `ft<glass<in` | `rgb(59, 68, 112)` | 12.5px/400 | 7.97:1 | 1 | Remove it or replace it with a licensed track before approving. Rules  (phone-queue) | PASS (4.5) |
| `chip<chips<nm` | `rgb(59, 68, 112)` | 11px/800 | 7.98:1 | 8 | Not connected (phone-connect) | PASS (4.5) |
| `chip<pn<prow` | `rgb(59, 68, 112)` | 11px/800 | 7.98:1 | 9 | Planned (mac-overview-pooled) | PASS (4.5) |
| `sub<g3<in` | `rgb(59, 68, 112)` | 15px/400 | 8.03:1 | 2 | Your example clips are ready. (mac-overview) | PASS (4.5) |
| `pp<pat<glass` | `rgb(59, 68, 112)` | 13px/700 | 8.05:1 | 2 | $— = $— (phone-earnings) | PASS (4.5) |
| `chip<nm<er` | `rgb(59, 68, 112)` | 11px/500 | 8.07:1 | 4 | Revenue data: Unverified (mac-more) | PASS (4.5) |
| `sub<fl<glass` | `rgb(59, 68, 112)` | 12.5px/400 | 8.08:1 | 6 | Remove it or replace it with a licensed track before approving. Rules  (mac-overview) | PASS (4.5) |
| `reel<mhdr<in` | `rgb(59, 68, 112)` | 11.5px/400 | 8.10:1 | 3 | Planned helper (mac-more) | PASS (4.5) |
| `seg<in<phone` | `rgb(59, 68, 112)` | 12.5px/800 | 8.10:1 | 3 | TikTok (phone-earnings) | PASS (4.5) |
| `big<glass<in` | `rgb(59, 68, 112)` | 22px/900 | 8.12:1 | 1 | No data yet (phone-costs) | PASS (3.0) |
| `chip<row<glass` | `rgb(59, 68, 112)` | 11px/800 | 8.14:1 | 2 | Example clip 3 (phone-flags) | PASS (4.5) |
| `chip<ptop<glass` | `rgb(59, 68, 112)` | 11px/800 | 8.15:1 | 3 | Revenue data: Unverified (phone-overview-pooled) | PASS (4.5) |
| `tg<mhdr<in` | `rgb(59, 68, 112)` | 13px/800 | 8.18:1 | 3 | Dark (mac-more) | PASS (4.5) |
| `pline<glass<in` | `rgb(59, 68, 112)` | 12.5px/400 | 8.20:1 | 3 | 1 of 4 channels connected (example) · Planned channels count as $0 (phone-pooled-example) | PASS (4.5) |
| `pline<glass<g3` | `rgb(59, 68, 112)` | 12.5px/400 | 8.21:1 | 1 | 0 of 4 channels connected · Planned channels count as $0 (mac-overview-pooled) | PASS (4.5) |
| `k<glass<stack` | `rgb(59, 68, 112)` | 11px/800 | 8.22:1 | 4 | Policy flags · examples (mac-overview) | PASS (4.5) |
| `off<pstrip<in` | `rgb(59, 68, 112)` | 11px/700 | 8.25:1 | 3 | Later (phone-overview) | PASS (4.5) |
| `safe<glass<in` | `rgb(59, 68, 112)` | 11.5px/500 | 8.25:1 | 1 | Approve = send to Postiz as a draft only (phone-queue) | PASS (4.5) |
| `sub<glass<in` | `rgb(59, 68, 112)` | 12px/400 | 8.27:1 | 1 | Example shape only. No real revenue yet. (phone-earnings) | PASS (4.5) |
| `chip<top<glass` | `rgb(59, 68, 112)` | 11px/800 | 8.31:1 | 1 | Revenue data: Unverified (phone-earnings) | PASS (4.5) |
| `k<ptop<glass` | `rgb(59, 68, 112)` | 11px/800 | 8.31:1 | 4 | Pooled revenue (phone-pooled-split) | PASS (4.5) |
| `chip<plc<glass` | `rgb(59, 68, 112)` | 11px/800 | 8.34:1 | 4 | Postiz (phone-costs) | PASS (4.5) |
| `k<glass<m3` | `rgb(59, 68, 112)` | 11px/800 | 8.38:1 | 3 | Connect channels (mac-more) | PASS (4.5) |
| `pl<vp<g3` | `rgb(59, 68, 112)` | 11px/700 | 8.40:1 | 3 | Later (mac-overview) | PASS (4.5) |
| `sub<m2<glass` | `rgb(59, 68, 112)` | 13px/400 | 8.51:1 | 1 | Concept only: compares what a platform says it paid with what lands in (mac-more) | PASS (4.5) |
| `chip<glass<g3` | `rgb(59, 68, 112)` | 11px/800 | 8.53:1 | 1 | Revenue data: Unverified (mac-overview-pooled) | PASS (4.5) |
| `dur<glass<g3` | `rgb(59, 68, 112)` | 15px/700 | 8.55:1 | 2 | Example: ~30 sec (mac-overview) | PASS (4.5) |
| `navC<phone` | `rgb(59, 68, 112)` | 11px/700 | 8.61:1 | 49 | Earnings (phone-connect) | PASS (4.5) |
| `va<er<m2` | `rgb(59, 68, 112)` | 16px/900 | 8.66:1 | 4 | $— (mac-more) | PASS (4.5) |
| `pp<pat<m2` | `rgb(59, 68, 112)` | 13px/700 | 8.66:1 | 2 | $— ≠ $— (mac-more) | PASS (4.5) |
| `v<bx<bank` | `rgb(59, 68, 112)` | 22px/900 | 8.67:1 | 2 | $— (phone-earnings) | PASS (3.0) |
| `k<bx<bank` | `rgb(59, 68, 112)` | 11px/800 | 8.69:1 | 4 | Payout reported (phone-earnings) | PASS (4.5) |
| `safe<glass<g3` | `rgb(59, 68, 112)` | 11.5px/500 | 8.70:1 | 2 | Approve = send to Postiz as a draft only (mac-overview) | PASS (4.5) |
| `tabsM<mhdr<in` | `rgb(59, 68, 112)` | 14px/700 | 8.88:1 | 13 | Earnings (mac-more) | PASS (4.5) |
| `sub<bx<cv` | `rgb(59, 68, 112)` | 13px/400 | 9.02:1 | 6 | Example shape only. No real revenue yet. (mac-overview) | PASS (4.5) |
| `k<bx<cv` | `rgb(59, 68, 112)` | 11px/800 | 9.06:1 | 6 | Costs · example (mac-overview) | PASS (4.5) |
| `big<bx<cv` | `rgb(59, 68, 112)` | 20px/900 | 9.06:1 | 3 | No data yet (mac-overview) | PASS (3.0) |
| `v<bx<bank` | `rgb(59, 68, 112)` | 20px/900 | 9.06:1 | 2 | $— (mac-more) | PASS (3.0) |
| `safe<in<phone` | `rgb(27, 33, 64)` | 13px/700 | 9.91:1 | 3 | Nothing posts until you approve (draft only) (phone-connect) | PASS (4.5) |
| `t<in<phone` | `rgb(27, 33, 64)` | 27px/800 | 10.07:1 | 11 | Hi Luis, your example clips are ready (phone-overview) | PASS (3.0) |
| `reel<hdr<in` | `rgb(27, 33, 64)` | 13px/700 | 10.52:1 | 12 | Clip helper (name TBD) (phone-connect) | PASS (4.5) |
| `hl<in<phone` | `rgb(27, 33, 64)` | 17px/800 | 10.92:1 | 2 | Approve your example clips (phone-overview-pooled) | PASS (4.5) |
| `stamp` | `rgb(251, 191, 36)` | 11px/900 | 11.13:1 | 27 | EXAMPLE DATA · DRAFT MOCKUP · NOT LIVE · NO ACCOUNTS CONNECTED, BUTTON (mac-more) | PASS (4.5) |
| `ribbon<glass<in` | `rgb(251, 191, 36)` | 11px/900 | 11.13:1 | 1 | EXAMPLE DATA, NOT REAL REVENUE (phone-pooled-example) | PASS (4.5) |
| `t<rowh<in` | `rgb(27, 33, 64)` | 27px/800 | 11.32:1 | 1 | Approvals (phone-queue) | PASS (3.0) |
| `t<in<mac` | `rgb(27, 33, 64)` | 30px/800 | 11.46:1 | 1 | Flags, costs, earnings & channels (mac-more) | PASS (3.0) |
| `pat<glass<in` | `rgb(27, 33, 64)` | 13px/700 | 13.25:1 | 2 | Pattern A (phone-earnings) | PASS (4.5) |
| `nm<glass<in` | `rgb(27, 33, 64)` | 15px/800 | 13.26:1 | 4 | YouTube (phone-connect) | PASS (4.5) |
| `glass<in<phone` | `rgb(27, 33, 64)` | 24px/800 | 13.27:1 | 3 | No clips yet (phone-queue-empty) | PASS (3.0) |
| `glass<in<phone` | `rgb(27, 33, 64)` | 18px/800 | 13.36:1 | 3 | Reused-content risk. (phone-flags) | PASS (4.5) |
| `pn<prow<glass` | `rgb(27, 33, 64)` | 15px/800 | 13.38:1 | 12 | Instagram (phone-pooled-example) | PASS (4.5) |
| `chip<chips<nm` | `rgb(27, 33, 64)` | 11px/800 | 13.41:1 | 2 | Planned · first (phone-connect) | PASS (4.5) |
| `nm<er<m2` | `rgb(27, 33, 64)` | 15px/800 | 13.41:1 | 4 | YouTube (mac-more) | PASS (4.5) |
| `fl<glass<stack` | `rgb(27, 33, 64)` | 14px/700 | 13.46:1 | 4 | Possible copyrighted music. (mac-overview) | PASS (4.5) |
| `big<glass<in` | `rgb(27, 33, 64)` | 22px/900 | 13.48:1 | 2 | ~$30–75/month (phone-costs) | PASS (3.0) |
| `pl<vp<g3` | `rgb(27, 33, 64)` | 14px/800 | 13.49:1 | 4 | TikTok (mac-overview) | PASS (4.5) |
| `t<g3<in` | `rgb(27, 33, 64)` | 38px/800 | 13.50:1 | 2 | Hi Luis (mac-overview) | PASS (3.0) |
| `ft<glass<in` | `rgb(27, 33, 64)` | 12.5px/700 | 13.52:1 | 1 | Possible copyrighted music. (phone-queue) | PASS (4.5) |
| `back<rowh<in` | `rgb(27, 33, 64)` | 14px/800 | 13.56:1 | 2 | Back to Overview (phone-pooled-example) | PASS (4.5) |
| `reel<mhdr<in` | `rgb(27, 33, 64)` | 13px/700 | 13.57:1 | 3 | Clip helper (name TBD) (mac-more) | PASS (4.5) |
| `chip<pn<prow` | `rgb(27, 33, 64)` | 11px/800 | 13.63:1 | 2 | Planned · first (mac-overview-pooled) | PASS (4.5) |
| `top<glass<in` | `rgb(27, 33, 64)` | 18px/800 | 13.65:1 | 1 | YouTube (phone-earnings) | PASS (4.5) |
| `chip<chips<glass` | `rgb(27, 33, 64)` | 11px/800 | 13.65:1 | 1 | YouTube · planned (phone-queue) | PASS (4.5) |
| `off<pstrip<in` | `rgb(27, 33, 64)` | 12px/800 | 13.68:1 | 3 | Instagram (phone-overview) | PASS (4.5) |
| `pn<prow<glass` | `rgb(27, 33, 64)` | 16px/800 | 13.68:1 | 3 | Total (phone-pooled-split) | PASS (4.5) |
| `plan<pstrip<in` | `rgb(27, 33, 64)` | 12px/800 | 13.75:1 | 1 | YouTube (phone-overview) | PASS (4.5) |
| `plan<pstrip<in` | `rgb(27, 33, 64)` | 11px/700 | 13.75:1 | 1 | Planned · first (phone-overview) | PASS (4.5) |
| `safe<glass<in` | `rgb(27, 33, 64)` | 13px/700 | 13.94:1 | 1 | Nothing posts until you approve (draft only) (phone-queue) | PASS (4.5) |
| `ptot<glass<in` | `rgb(27, 33, 64)` | 38px/900 | 13.95:1 | 3 | $0.00 (phone-overview-pooled) | PASS (3.0) |
| `ptot<glass<g3` | `rgb(27, 33, 64)` | 40px/900 | 13.96:1 | 1 | $0.00 (mac-overview-pooled) | PASS (3.0) |
| `pa<prow<glass` | `rgb(27, 33, 64)` | 16px/900 | 13.96:1 | 12 | $0.00 (mac-overview-pooled) | PASS (4.5) |
| `pa<prow<glass` | `rgb(27, 33, 64)` | 18px/900 | 14.01:1 | 3 | $0.00 (phone-pooled-split) | PASS (4.5) |
| `cap` | `rgb(27, 33, 64)` | 14px/400 | 14.09:1 | 30 | Flags, Costs vs Earnings, Connect channels and Earnings together on on (mac-more) | PASS (4.5) |
| `fl<glass<m3` | `rgb(27, 33, 64)` | 14px/700 | 14.19:1 | 2 | Reused-content risk. (mac-more) | PASS (4.5) |
| `pl<vp<g3` | `rgb(27, 33, 64)` | 11px/700 | 14.47:1 | 1 | Planned · first (mac-overview) | PASS (4.5) |
| `pat<m2<glass` | `rgb(27, 33, 64)` | 13px/700 | 14.61:1 | 2 | Pattern A (mac-more) | PASS (4.5) |
| `glass<g3<in` | `rgb(27, 33, 64)` | 26px/800 | 14.61:1 | 2 | Approve your example clips (mac-overview) | PASS (3.0) |
| `safe<glass<g3` | `rgb(27, 33, 64)` | 13px/700 | 14.61:1 | 2 | Nothing posts until you approve (draft only) (mac-overview) | PASS (4.5) |
| `btn<glass<in` | `rgb(27, 33, 64)` | 15px/800 | 14.73:1 | 3 | Back to Overview (phone-flags-empty) | PASS (4.5) |
| `btn<glass<in` | `rgb(27, 33, 64)` | 14px/800 | 14.75:1 | 4 | Connect (phone-connect) | PASS (4.5) |
| `btn<bt<glass` | `rgb(27, 33, 64)` | 14px/800 | 14.85:1 | 1 | Edit (phone-queue) | PASS (4.5) |
| `nm<glass<glass` | `rgb(27, 33, 64)` | 14px/800 | 15.04:1 | 4 | Facebook (mac-more) | PASS (4.5) |
| `big<bx<cv` | `rgb(27, 33, 64)` | 20px/900 | 15.20:1 | 6 | Example: (mac-overview) | PASS (3.0) |
| `th<cards<in` | `rgb(255, 255, 255)` | 11px/800 | 15.25:1 | 6 | Example clip 3 (phone-overview-pooled) | PASS (4.5) |
| `th<fan<glass` | `rgb(255, 255, 255)` | 11px/800 | 15.38:1 | 6 | Example clip 3 (mac-overview) | PASS (4.5) |
| `th<glass<in` | `rgb(255, 255, 255)` | 11px/800 | 15.41:1 | 1 | Example clip 2 of 3 · flagged (phone-queue) | PASS (4.5) |
| `btn<glass<glass` | `rgb(27, 33, 64)` | 14px/800 | 15.44:1 | 4 | Connect (mac-more) | PASS (4.5) |
| `on<seg<in` | `rgb(255, 255, 255)` | 12.5px/800 | 15.54:1 | 1 | YouTube (phone-earnings) | PASS (4.5) |
| `on<tg<mhdr` | `rgb(255, 255, 255)` | 13px/800 | 15.69:1 | 3 | Light (mac-more) | PASS (4.5) |
| `on<tabsM<mhdr` | `rgb(255, 255, 255)` | 14px/700 | 15.69:1 | 2 | Overview (mac-overview) | PASS (4.5) |
| `on<navC<phone` | `rgb(255, 255, 255)` | 11px/700 | 15.69:1 | 11 | Costs (phone-costs) | PASS (4.5) |

**Dark**

| Role | Colour | Size/weight | Worst ratio | Count | Example text (screen) | Pass (need) |
|---|---|---|---|---|---|---|
| `btn<btns<glass` | `rgb(255, 255, 255)` | 15px/800 | 4.73:1 | 2 | Review one by one (mac-overview) | PASS (4.5) |
| `btn<glass<in` | `rgb(255, 255, 255)` | 15px/800 | 4.73:1 | 2 | Next: connect a channel (phone-earnings-empty) | PASS (4.5) |
| `btn<in<phone` | `rgb(255, 255, 255)` | 16px/900 | 4.73:1 | 2 | Review one by one (phone-overview-pooled) | PASS (4.5) |
| `on<navC<phone` | `rgb(255, 255, 255)` | 11px/700 | 4.75:1 | 11 | Overview (phone-overview) | PASS (4.5) |
| `on<tabsM<mhdr` | `rgb(255, 255, 255)` | 14px/700 | 4.76:1 | 2 | Overview (mac-overview) | PASS (4.5) |
| `reel<mhdr<in` | `rgb(255, 255, 255)` | 16px/900 | 4.78:1 | 3 | C (mac-more) | PASS (4.5) |
| `reel<hdr<in` | `rgb(255, 255, 255)` | 16px/900 | 4.80:1 | 12 | C (phone-connect) | PASS (4.5) |
| `on<seg<in` | `rgb(255, 255, 255)` | 12.5px/800 | 4.81:1 | 1 | YouTube (phone-earnings) | PASS (4.5) |
| `on<tg<mhdr` | `rgb(255, 255, 255)` | 13px/800 | 4.82:1 | 3 | Dark (mac-more) | PASS (4.5) |
| `btn<bt<glass` | `rgb(188, 195, 232)` | 14px/800 | 5.64:1 | 1 | Approve (phone-queue) | PASS (4.5) |
| `btn<glass<glass` | `rgb(241, 243, 255)` | 14px/800 | 5.78:1 | 4 | Connect (mac-more) | PASS (4.5) |
| `chip<pn<prow` | `rgb(110, 231, 183)` | 11px/800 | 5.93:1 | 1 | Connected (example) (phone-pooled-example) | PASS (4.5) |
| `btn<glass<in` | `rgb(188, 195, 232)` | 15px/800 | 6.19:1 | 1 | Approve batch (phone-queue) | PASS (4.5) |
| `chip<row<glass` | `rgb(255, 191, 199)` | 11px/800 | 6.26:1 | 1 | EXAMPLE · Rose (phone-flags) | PASS (4.5) |
| `chip<chips<nm` | `rgb(208, 213, 244)` | 11px/800 | 6.33:1 | 8 | Not connected (mac-more) | PASS (4.5) |
| `chip<pat<glass` | `rgb(110, 231, 183)` | 11px/800 | 6.49:1 | 1 | EXAMPLE · Match (phone-earnings) | PASS (4.5) |
| `v<bx<bank` | `rgb(208, 213, 244)` | 22px/900 | 6.52:1 | 2 | $— (phone-earnings) | PASS (3.0) |
| `k<bx<bank` | `rgb(208, 213, 244)` | 11px/800 | 6.57:1 | 4 | Payout reported (phone-earnings) | PASS (4.5) |
| `exl<pa<prow` | `rgb(252, 211, 77)` | 11px/900 | 6.69:1 | 2 | EXAMPLE (phone-pooled-example) | PASS (4.5) |
| `chip<row<glass` | `rgb(252, 211, 77)` | 11px/800 | 6.74:1 | 1 | EXAMPLE · Amber (phone-flags) | PASS (4.5) |
| `chip<chips<glass` | `rgb(252, 211, 77)` | 11px/800 | 6.76:1 | 1 | Flag · music (EXAMPLE) (phone-queue) | PASS (4.5) |
| `exl<ptot<glass` | `rgb(252, 211, 77)` | 11px/900 | 6.77:1 | 1 | EXAMPLE (phone-pooled-example) | PASS (4.5) |
| `chip<pat<glass` | `rgb(255, 191, 199)` | 11px/800 | 6.78:1 | 1 | EXAMPLE · Mismatch (phone-earnings) | PASS (4.5) |
| `chip<fl<glass` | `rgb(255, 191, 199)` | 11px/800 | 6.91:1 | 3 | EXAMPLE · Rose (mac-more) | PASS (4.5) |
| `btn<bt<glass` | `rgb(255, 191, 199)` | 14px/800 | 7.13:1 | 1 | Reject (phone-queue) | PASS (4.5) |
| `chip<fl<glass` | `rgb(252, 211, 77)` | 11px/800 | 7.22:1 | 3 | EXAMPLE · Amber (mac-overview) | PASS (4.5) |
| `chip<pat<m2` | `rgb(255, 191, 199)` | 11px/800 | 7.28:1 | 1 | EXAMPLE · Mismatch (mac-more) | PASS (4.5) |
| `chip<pat<m2` | `rgb(110, 231, 183)` | 11px/800 | 7.38:1 | 1 | EXAMPLE · Match (mac-more) | PASS (4.5) |
| `btn<in<phone` | `rgb(188, 195, 232)` | 15px/800 | 7.50:1 | 2 | Approve all (phone-overview) | PASS (4.5) |
| `btn<btns<glass` | `rgb(188, 195, 232)` | 15px/800 | 7.56:1 | 2 | Approve all (mac-overview) | PASS (4.5) |
| `sub<glass<in` | `rgb(208, 213, 244)` | 13px/400 | 7.57:1 | 3 | Example shape only. No real revenue yet. (phone-costs) | PASS (4.5) |
| `glass<in<phone` | `rgb(208, 213, 244)` | 15px/400 | 7.57:1 | 3 | Earnings will show up here once a channel is connected and its revenue (phone-earnings-empty) | PASS (4.5) |
| `glass<in<phone` | `rgb(208, 213, 244)` | 13px/400 | 7.57:1 | 2 | YouTube may limit monetization of clips from someone else’s video unle (phone-flags) | PASS (4.5) |
| `k<glass<in` | `rgb(208, 213, 244)` | 11px/800 | 7.70:1 | 6 | Earnings · by platform (mac-more) | PASS (4.5) |
| `phint<glass<g3` | `rgb(199, 201, 255)` | 12.5px/800 | 7.70:1 | 1 | Click for per-platform split (mac-overview-pooled) | PASS (4.5) |
| `ft<glass<in` | `rgb(208, 213, 244)` | 12.5px/400 | 7.72:1 | 1 | Remove it or replace it with a licensed track before approving. Rules  (phone-queue) | PASS (4.5) |
| `chip<pn<prow` | `rgb(208, 213, 244)` | 11px/800 | 7.84:1 | 9 | Planned (phone-pooled-example) | PASS (4.5) |
| `phint<glass<in` | `rgb(199, 201, 255)` | 12.5px/800 | 7.98:1 | 1 | Tap for per-platform split (phone-overview-pooled) | PASS (4.5) |
| `pp<pat<glass` | `rgb(208, 213, 244)` | 13px/700 | 8.07:1 | 2 | $— = $— (phone-earnings) | PASS (4.5) |
| `sub<fl<glass` | `rgb(208, 213, 244)` | 12.5px/400 | 8.08:1 | 6 | Remove it or replace it with a licensed track before approving. Rules  (mac-overview) | PASS (4.5) |
| `chip<nm<er` | `rgb(208, 213, 244)` | 11px/500 | 8.15:1 | 4 | Revenue data: Unverified (mac-more) | PASS (4.5) |
| `big<glass<in` | `rgb(208, 213, 244)` | 22px/900 | 8.22:1 | 1 | No data yet (phone-costs) | PASS (3.0) |
| `chip<ptop<glass` | `rgb(208, 213, 244)` | 11px/800 | 8.22:1 | 3 | Revenue data: Unverified (phone-overview-pooled) | PASS (4.5) |
| `nm<glass<glass` | `rgb(241, 243, 255)` | 14px/800 | 8.28:1 | 4 | Instagram (mac-more) | PASS (4.5) |
| `sub<bx<cv` | `rgb(208, 213, 244)` | 13px/400 | 8.40:1 | 6 | Example shape only. No real revenue yet. (mac-overview) | PASS (4.5) |
| `chip<row<glass` | `rgb(208, 213, 244)` | 11px/800 | 8.40:1 | 2 | Example clip 2 (phone-flags) | PASS (4.5) |
| `safe<glass<in` | `rgb(208, 213, 244)` | 11.5px/500 | 8.43:1 | 1 | Approve = send to Postiz as a draft only (phone-queue) | PASS (4.5) |
| `pline<glass<in` | `rgb(208, 213, 244)` | 12.5px/400 | 8.45:1 | 3 | 1 of 4 channels connected (example) · Planned channels count as $0 (phone-pooled-example) | PASS (4.5) |
| `off<pstrip<in` | `rgb(208, 213, 244)` | 11px/700 | 8.49:1 | 3 | Later (phone-overview) | PASS (4.5) |
| `blk<glass<in` | `rgb(252, 211, 77)` | 12.5px/800 | 8.54:1 | 1 | Resolve open flags first (phone-queue) | PASS (4.5) |
| `btn<glass<in` | `rgb(241, 243, 255)` | 15px/800 | 8.57:1 | 3 | Back to Overview (phone-flags-empty) | PASS (4.5) |
| `k<glass<stack` | `rgb(208, 213, 244)` | 11px/800 | 8.67:1 | 4 | Policy flags · examples (mac-overview) | PASS (4.5) |
| `chip<chips<nm` | `rgb(241, 243, 255)` | 11px/800 | 8.68:1 | 2 | Planned · first (mac-more) | PASS (4.5) |
| `btn<glass<in` | `rgb(241, 243, 255)` | 14px/800 | 8.71:1 | 4 | Connect (phone-connect) | PASS (4.5) |
| `sub<glass<in` | `rgb(208, 213, 244)` | 12px/400 | 8.71:1 | 1 | Example shape only. No real revenue yet. (phone-earnings) | PASS (4.5) |
| `pline<glass<g3` | `rgb(208, 213, 244)` | 12.5px/400 | 8.71:1 | 1 | 0 of 4 channels connected · Planned channels count as $0 (mac-overview-pooled) | PASS (4.5) |
| `k<ptop<glass` | `rgb(208, 213, 244)` | 11px/800 | 8.82:1 | 4 | Pooled revenue (phone-overview-pooled) | PASS (4.5) |
| `chip<rowh<in` | `rgb(208, 213, 244)` | 11px/800 | 8.84:1 | 1 | Example clip 2 of 3 (phone-queue) | PASS (4.5) |
| `chip<plc<glass` | `rgb(208, 213, 244)` | 11px/800 | 8.89:1 | 4 | TubeAlfred (phone-costs) | PASS (4.5) |
| `k<bx<cv` | `rgb(208, 213, 244)` | 11px/800 | 8.90:1 | 6 | Earnings (mac-overview) | PASS (4.5) |
| `big<bx<cv` | `rgb(208, 213, 244)` | 20px/900 | 8.90:1 | 3 | No data yet (mac-overview) | PASS (3.0) |
| `v<bx<bank` | `rgb(208, 213, 244)` | 20px/900 | 8.90:1 | 2 | $— (mac-more) | PASS (3.0) |
| `blk<glass<g3` | `rgb(252, 211, 77)` | 12.5px/800 | 8.92:1 | 2 | Resolve open flags first (mac-overview) | PASS (4.5) |
| `chip<top<glass` | `rgb(208, 213, 244)` | 11px/800 | 8.99:1 | 1 | Revenue data: Unverified (phone-earnings) | PASS (4.5) |
| `btn<bt<glass` | `rgb(241, 243, 255)` | 14px/800 | 9.02:1 | 1 | Edit (phone-queue) | PASS (4.5) |
| `seg<in<phone` | `rgb(208, 213, 244)` | 12.5px/800 | 9.07:1 | 3 | TikTok (phone-earnings) | PASS (4.5) |
| `sub<m2<glass` | `rgb(208, 213, 244)` | 13px/400 | 9.19:1 | 1 | Concept only: compares what a platform says it paid with what lands in (mac-more) | PASS (4.5) |
| `pl<vp<g3` | `rgb(208, 213, 244)` | 11px/700 | 9.22:1 | 3 | Later (mac-overview) | PASS (4.5) |
| `pwr<in<phone` | `rgb(208, 213, 244)` | 11px/400 | 9.46:1 | 1 | Planned tools (not connected): OpusClip · Postiz · TubeAlfred · Remoti (phone-costs) | PASS (4.5) |
| `chip<glass<g3` | `rgb(208, 213, 244)` | 11px/800 | 9.49:1 | 1 | Revenue data: Unverified (mac-overview-pooled) | PASS (4.5) |
| `cap` | `rgb(185, 188, 255)` | 11px/700 | 9.62:1 | 30 | What you do here: (mac-more) | PASS (4.5) |
| `sub<in<phone` | `rgb(208, 213, 244)` | 13px/400 | 9.83:1 | 2 | Example warnings to fix before approving (phone-flags) | PASS (4.5) |
| `swp<rowh<in` | `rgb(208, 213, 244)` | 12px/800 | 9.85:1 | 2 | swipe › (phone-overview) | PASS (4.5) |
| `k<glass<m3` | `rgb(208, 213, 244)` | 11px/800 | 9.87:1 | 3 | Connect channels (mac-more) | PASS (4.5) |
| `pat<glass<in` | `rgb(241, 243, 255)` | 13px/700 | 9.92:1 | 2 | Pattern A (phone-earnings) | PASS (4.5) |
| `hl<in<phone` | `rgb(208, 213, 244)` | 13.5px/700 | 10.03:1 | 2 | · Example: ~30 sec (phone-overview) | PASS (4.5) |
| `glass<in<phone` | `rgb(241, 243, 255)` | 24px/800 | 10.07:1 | 3 | No clips yet (phone-queue-empty) | PASS (3.0) |
| `glass<in<phone` | `rgb(241, 243, 255)` | 18px/800 | 10.09:1 | 3 | Reused-content risk. (phone-flags) | PASS (4.5) |
| `pp<pat<m2` | `rgb(208, 213, 244)` | 13px/700 | 10.11:1 | 2 | $— ≠ $— (mac-more) | PASS (4.5) |
| `pn<prow<glass` | `rgb(241, 243, 255)` | 15px/800 | 10.12:1 | 12 | Instagram (phone-pooled-split) | PASS (4.5) |
| `safe<in<phone` | `rgb(208, 213, 244)` | 11.5px/500 | 10.13:1 | 3 | Approve = send to Postiz as a draft only (phone-connect) | PASS (4.5) |
| `pl<vp<g3` | `rgb(241, 243, 255)` | 14px/800 | 10.27:1 | 4 | TikTok (mac-overview) | PASS (4.5) |
| `reel<hdr<in` | `rgb(208, 213, 244)` | 11.5px/400 | 10.30:1 | 12 | Planned helper (phone-connect) | PASS (4.5) |
| `fl<glass<stack` | `rgb(241, 243, 255)` | 14px/700 | 10.33:1 | 4 | Possible copyrighted music. (mac-overview) | PASS (4.5) |
| `va<er<m2` | `rgb(208, 213, 244)` | 16px/900 | 10.40:1 | 4 | $— (mac-more) | PASS (4.5) |
| `blk<in<phone` | `rgb(252, 211, 77)` | 12.5px/800 | 10.42:1 | 3 | Resolve open flags first (phone-overview) | PASS (4.5) |
| `ft<glass<in` | `rgb(241, 243, 255)` | 12.5px/700 | 10.44:1 | 1 | Possible copyrighted music. (phone-queue) | PASS (4.5) |
| `safe<glass<g3` | `rgb(208, 213, 244)` | 11.5px/500 | 10.47:1 | 2 | Approve = send to Postiz as a draft only (mac-overview) | PASS (4.5) |
| `dotrow<in<phone` | `rgb(208, 213, 244)` | 11.5px/700 | 10.48:1 | 3 | ‹ (phone-queue) | PASS (4.5) |
| `k<rowh<in` | `rgb(208, 213, 244)` | 11px/800 | 10.51:1 | 2 | Example clips (phone-overview-pooled) | PASS (4.5) |
| `nm<er<m2` | `rgb(241, 243, 255)` | 15px/800 | 10.52:1 | 4 | YouTube (mac-more) | PASS (4.5) |
| `dur<glass<g3` | `rgb(208, 213, 244)` | 15px/700 | 10.53:1 | 2 | Example: ~30 sec (mac-overview) | PASS (4.5) |
| `big<glass<in` | `rgb(241, 243, 255)` | 22px/900 | 10.53:1 | 2 | ~$30–75/month (phone-costs) | PASS (3.0) |
| `nm<glass<in` | `rgb(241, 243, 255)` | 15px/800 | 10.55:1 | 4 | YouTube (phone-connect) | PASS (4.5) |
| `chip<pn<prow` | `rgb(241, 243, 255)` | 11px/800 | 10.75:1 | 2 | Planned · first (mac-overview-pooled) | PASS (4.5) |
| `tg<mhdr<in` | `rgb(208, 213, 244)` | 13px/800 | 10.79:1 | 3 | Light (mac-more) | PASS (4.5) |
| `top<glass<in` | `rgb(241, 243, 255)` | 18px/800 | 10.80:1 | 1 | YouTube (phone-earnings) | PASS (4.5) |
| `back<rowh<in` | `rgb(241, 243, 255)` | 14px/800 | 10.83:1 | 2 | Back to Overview (phone-pooled-example) | PASS (4.5) |
| `pn<prow<glass` | `rgb(241, 243, 255)` | 16px/800 | 10.85:1 | 3 | Total (phone-pooled-split) | PASS (4.5) |
| `chip<chips<glass` | `rgb(241, 243, 255)` | 11px/800 | 10.91:1 | 1 | YouTube · planned (phone-queue) | PASS (4.5) |
| `plan<pstrip<in` | `rgb(241, 243, 255)` | 12px/800 | 10.95:1 | 1 | YouTube (phone-overview) | PASS (4.5) |
| `navC<phone` | `rgb(208, 213, 244)` | 11px/700 | 11.02:1 | 49 | Earnings (phone-connect) | PASS (4.5) |
| `off<pstrip<in` | `rgb(241, 243, 255)` | 12px/800 | 11.08:1 | 3 | Facebook (phone-overview) | PASS (4.5) |
| `safe<glass<in` | `rgb(241, 243, 255)` | 13px/700 | 11.10:1 | 1 | Nothing posts until you approve (draft only) (phone-queue) | PASS (4.5) |
| `stamp` | `rgb(251, 191, 36)` | 11px/900 | 11.13:1 | 27 | EXAMPLE DATA · DRAFT MOCKUP · NOT LIVE · NO ACCOUNTS CONNECTED, BUTTON (mac-more) | PASS (4.5) |
| `ribbon<glass<in` | `rgb(251, 191, 36)` | 11px/900 | 11.13:1 | 1 | EXAMPLE DATA, NOT REAL REVENUE (phone-pooled-example) | PASS (4.5) |
| `plan<pstrip<in` | `rgb(241, 243, 255)` | 11px/700 | 11.21:1 | 1 | Planned · first (phone-overview) | PASS (4.5) |
| `pa<prow<glass` | `rgb(241, 243, 255)` | 18px/900 | 11.39:1 | 3 | $123.45 (phone-pooled-example) | PASS (4.5) |
| `t<in<phone` | `rgb(241, 243, 255)` | 27px/800 | 11.40:1 | 11 | Hi Luis, your example clips are ready (phone-overview) | PASS (3.0) |
| `ptot<glass<in` | `rgb(241, 243, 255)` | 38px/900 | 11.62:1 | 3 | $0.00 (phone-overview-pooled) | PASS (3.0) |
| `big<bx<cv` | `rgb(241, 243, 255)` | 20px/900 | 11.71:1 | 6 | Example: (mac-overview) | PASS (3.0) |
| `ptot<glass<g3` | `rgb(241, 243, 255)` | 40px/900 | 11.84:1 | 1 | $0.00 (mac-overview-pooled) | PASS (3.0) |
| `pa<prow<glass` | `rgb(241, 243, 255)` | 16px/900 | 11.84:1 | 12 | $0.00 (mac-overview-pooled) | PASS (4.5) |
| `tabsM<mhdr<in` | `rgb(208, 213, 244)` | 14px/700 | 11.99:1 | 13 | Earnings (mac-more) | PASS (4.5) |
| `pwr<in<mac` | `rgb(208, 213, 244)` | 11px/400 | 12.11:1 | 3 | Planned tools (not connected): OpusClip · Postiz · TubeAlfred · Remoti (mac-more) | PASS (4.5) |
| `k<g3<in` | `rgb(208, 213, 244)` | 11px/800 | 12.14:1 | 1 | Platforms (mac-overview) | PASS (4.5) |
| `fl<glass<m3` | `rgb(241, 243, 255)` | 14px/700 | 12.22:1 | 2 | Reused-content risk. (mac-more) | PASS (4.5) |
| `sub<g3<in` | `rgb(208, 213, 244)` | 15px/400 | 12.39:1 | 2 | Your example clips are ready. (mac-overview) | PASS (4.5) |
| `reel<hdr<in` | `rgb(241, 243, 255)` | 13px/700 | 12.48:1 | 12 | Clip helper (name TBD) (phone-connect) | PASS (4.5) |
| `hl<in<phone` | `rgb(241, 243, 255)` | 17px/800 | 12.53:1 | 2 | Approve your example clips (phone-overview) | PASS (4.5) |
| `reel<mhdr<in` | `rgb(208, 213, 244)` | 11.5px/400 | 12.79:1 | 3 | Planned helper (mac-more) | PASS (4.5) |
| `pl<vp<g3` | `rgb(241, 243, 255)` | 11px/700 | 13.45:1 | 1 | Planned · first (mac-overview) | PASS (4.5) |
| `safe<in<phone` | `rgb(241, 243, 255)` | 13px/700 | 13.47:1 | 3 | Nothing posts until you approve (draft only) (phone-connect) | PASS (4.5) |
| `pat<m2<glass` | `rgb(241, 243, 255)` | 13px/700 | 13.68:1 | 2 | Pattern B (mac-more) | PASS (4.5) |
| `glass<g3<in` | `rgb(241, 243, 255)` | 26px/800 | 13.68:1 | 2 | Approve your example clips (mac-overview) | PASS (3.0) |
| `t<rowh<in` | `rgb(241, 243, 255)` | 27px/800 | 13.69:1 | 1 | Approvals (phone-queue) | PASS (3.0) |
| `safe<glass<g3` | `rgb(241, 243, 255)` | 13px/700 | 13.71:1 | 2 | Nothing posts until you approve (draft only) (mac-overview) | PASS (4.5) |
| `cap` | `rgb(228, 231, 255)` | 14px/400 | 14.12:1 | 30 | Scan only. Nothing is connected; buttons do nothing. (mac-more) | PASS (4.5) |
| `t<in<mac` | `rgb(241, 243, 255)` | 30px/800 | 16.71:1 | 1 | Flags, costs, earnings & channels (mac-more) | PASS (3.0) |
| `t<g3<in` | `rgb(241, 243, 255)` | 38px/800 | 16.73:1 | 2 | Hi Luis (mac-overview) | PASS (3.0) |
| `reel<mhdr<in` | `rgb(241, 243, 255)` | 13px/700 | 16.80:1 | 3 | Clip helper (name TBD) (mac-more) | PASS (4.5) |
| `th<cards<in` | `rgb(255, 255, 255)` | 11px/800 | 17.95:1 | 6 | Example clip 3 (phone-overview-pooled) | PASS (4.5) |
| `th<fan<glass` | `rgb(255, 255, 255)` | 11px/800 | 18.06:1 | 6 | Example clip 3 (mac-overview) | PASS (4.5) |
| `th<glass<in` | `rgb(255, 255, 255)` | 11px/800 | 18.06:1 | 1 | Example clip 2 of 3 · flagged (phone-queue) | PASS (4.5) |

### C. Non-text elements (not scored as text, stated explicitly)
Icons and glyph shapes, the play triangles, the hatched placeholder stripes, dashed/solid borders, dots and the toggle sun/moon icons carry no text. Their meaning is always repeated in adjacent text that is scored in section B. The contact sheets (`clip-sky1-contact-*.png`, `clip-sky2-contact-*.png`, `clip-sky1-light-vs-dark.png`) have annotation text outside the app frames: #1b2140 on #eef1fb 13.91:1, #f4f4f8 on #0b0d16 17.67:1, #fbbf24 on #15111d (banner pill) 11.13:1, #cfd3ea on #10121c 12.58:1, #f4f4f8 on #10121c 17.01:1.

### D. Fix history
- First round: light `--text-2` `#454e7a` -> `#3b4470`, `--text-3` `#4f5885` -> `#454e7a`; `--ok-text` `#0a7050` -> `#086245`; accent gradient darkened so white button text passes. Dark: `--text-3` -> `#bcc3e8`, `--text-2` -> `#d0d5f4`, `--bad-text` -> `#ffbfc7`, accent `#5a63f0 -> #7a55e8`.
- Fact Check round: thumbnail "Example clip" labels measured 3.59:1 and 3.44:1 in light mode (translucent pill, 62% opaque). `--thumb-label-bg` is now `rgba(10,14,40,.88)` (light) and `rgba(5,8,28,.88)` (dark): worst case 14.75:1 over every thumbnail gradient stop in light and 17.67:1 in dark (token-level), and 15.38:1 / 18.06:1 measured on the real renders. The earlier "not scored" and "disabled text exempt" exceptions are removed; those texts are now in section B.
- Banner amber `#fbbf24` is now `--banner-amber` (with `--banner-bg` `#15111d`) in both themes and used by the CSS. All labels that were 10px / 10.5px (banner, nav labels, eyebrows, thumbnail labels, status tiles, inline chips) are now 11px.
