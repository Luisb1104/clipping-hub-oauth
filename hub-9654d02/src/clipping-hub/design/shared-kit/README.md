# shared-kit motion (v2)

Files: `motion.css` (2140 B raw, 1701 B minified, 673 B min+gzip), `motion.js` (914 B, 595 B gz, optional), `motion.v1.css` (backup of the original), `demo.html`, `bench.py`, `bench-results.json`, `bench/blank.*` (control files so on/off runs fetch the same number of files).
Rules: transform/opacity only (one exception: `.m-draw`), everything one-shot, no infinite animations, all durations <= 450 ms, no `will-change`. One `@media (prefers-reduced-motion: reduce)` block turns all animation/transition off; elements then sit in their final state.

## Classes
| Class | What it does |
|---|---|
| `.m-up` | fade + 10px rise, 400 ms (unchanged from v1) |
| `.m-spring` | same with spring easing, 420 ms (unchanged) |
| `.m-tab` | page/tab swap: opacity + 6px translateY, 180 ms. Re-apply on the new pane (add it to the pane you reveal) |
| `.m-i` + `style="--i:N"` | staggered entrance: `animation-delay = min(N,7) * 40ms`, so max 280 ms delay; N>7 is capped |
| `.m-stagger` (parent) | v1 nth-child stagger, extended to 8 steps (no `--i` needed) |
| `.m-num` | `tabular-nums` so digits don't jitter while counting |
| `data-count="1234.5"` + `motion.js` | count-up, 500 ms ease-out, once. No JS = the number you wrote in the element simply shows |
| `.m-draw` on `<path pathLength="1">` | one-shot line draw 450 ms via stroke-dashoffset. **Paint-only, not transform/opacity**; SVG-small. Needs `pathLength="1"` on the path, otherwise the rule does not match and the line is shown normally |
| `.m-hover` | scale 1.02 on hover (only inside `@media (hover:hover)`), 0.98 on press, 150 ms |
| `.m-press` | press only: scale 0.98 (v1 was .97) |
| `.m-glow` | one-shot soft pulse via `::after` opacity, 450 ms (v1 was 900 ms, shortened to meet the <=450 ms rule). Add the class once on a state change; to replay: remove it, force reflow, add it again |

## Count-up details (`motion.js`)
- Put the real, final text in the element and the plain number in `data-count`: `<b data-count="12345.67">$12,345.67</b>`. The first number in the text is replaced while counting; the original text is written back verbatim at the end, so the final value is never changed.
- Skips when `prefers-reduced-motion: reduce`, when the value isn't numeric, or when it already ran (`data-m-done`). Locks min-width first to avoid layout shift.
- Auto-runs at DOMContentLoaded. For nodes added later call `mCount(rootElement)`.

## (a) Plain HTML apps (Banking Hub, Danny)
```html
<link rel="stylesheet" href="shared-kit/motion.css">
<div class="cards">
  <div class="card m-i m-hover" style="--i:0">...</div>
  <div class="card m-i m-hover" style="--i:1">...</div>
</div>
<b class="m-num" data-count="1234.5">1,234.5</b>
<svg viewBox="0 0 200 60"><path class="m-draw" pathLength="1" d="..." fill="none" stroke="#5ef2a6"/></svg>
<script src="shared-kit/motion.js" defer></script>  <!-- optional -->
```
Tab switch: add `m-tab` to the pane you show (remove/re-add or render a fresh node). State change: `el.classList.add('m-glow')` once.

## (b) Streamlit (Terminal)
Streamlit runs no script from `st.markdown`, so use CSS only; the number simply shows (the no-JS fallback).
```python
import streamlit as st
st.markdown("<style>" + open("shared-kit/motion.css").read() + "</style>", unsafe_allow_html=True)  # or paste the minified CSS inline
st.markdown('<div class="m-i m-hover" style="--i:2">Card</div>', unsafe_allow_html=True)
st.markdown('<b class="m-num" data-count="1234.5">1,234.5</b>', unsafe_allow_html=True)
```
Caveat: Streamlit reruns re-insert nodes, so entrance animations replay on every rerun. Use `.m-i`/`.m-up` only on first-load blocks (gate with `st.session_state`), not on elements that rerun constantly. Optional count-up: inject motion.js with `st.components.v1.html("<script>"+js+"</script>", height=0)` and call `window.parent.mCount(window.parent.document)` after defining it in the parent; skip if you don't need it.
Streamlit `st.markdown` may strip some attributes (`pathLength`, `style="--i"`); if so use `st.html` (newer Streamlit) instead.

## Validation (headless Chrome 156, 7 runs each, medians; file:// demo, see bench-results.json)
| | first paint (FCP) | DOMContentLoaded | load | CLS | long tasks |
|---|---|---|---|---|---|
| kit off (blank control files) | 24 ms | 17.5 ms | 17.6 ms | 0 | 0 |
| kit on | 32 ms | 19.4 ms | 19.5 ms | 0 | 0 |
| kit on, reduced-motion | 28 ms | 19.1 ms | 19.1 ms | 0 | 0 |

FCP is quantized to ~4 ms frames and per-run spread (20-44 ms) is larger than the on/off gap, so ~2 ms DCL / ~4-8 ms FCP is within noise: no cost worth dropping any feature. Count-up sampled mid-flight: $3,345.68 -> ... -> $12,345.67 (final text identical to the HTML text). CSS parses cleanly with tinycss2 (no errors).
