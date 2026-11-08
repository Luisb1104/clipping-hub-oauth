# Clipper data auto-refresh

Hub reads `data/clipper/{ledger,channels,shorts}` only. It never calls Opus, ElevenLabs, or Whop itself.

## Refresh path (box → Mac)

1. On the **box** (or any agent with connectors), gather:
   - Opus credits: `opusclip_get_usage` (read-only)
   - Opus channels: `opusclip_list_social_accounts` (read-only)
   - Campaigns: Clipper ledger **or** `content-rewards/APPLY-PACK.md`
   - Script queue: Clipper `ledger/script-queue.json` when Clipper writes it
   - ElevenLabs usage: **blocked** — ElevenLabs MCP has no subscription/usage tool yet. Plan ceiling stays 30k; remaining stays null until a tool exists.
2. Run: `python3 tools/refresh_clipper_ledger.py --file payload.json`
3. Copy files onto the Mac hub `data/clipper/`.

## Routine needed?

**Yes.** The Mac LaunchAgent cannot call MCP connectors unattended. Create a routine that refreshes from the box on a schedule and pushes ledger/channels JSON to the Mac.

## Honesty rules

- Never invent spent/remaining numbers
- Show empty / unavailable when a source cannot run
- Every file carries `as_of`
