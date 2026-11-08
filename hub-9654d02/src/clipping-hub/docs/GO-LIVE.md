# Clipping Hub: go-live notes (PROPOSAL ONLY)

Status: **nothing here has been done.** No launchd job is installed, no plist file exists in this repo or in `~/Library/LaunchAgents`, no remote is set, nothing is pushed, nothing is connected. This file only holds the proposed text so the step can be reviewed first.

## Facts about the shell today
- Server: `server.py`, stdlib only, binds `127.0.0.1:8505` (port was free when checked; override with `CLIPPING_HUB_PORT`).
- Only file it writes: `data/state.json` (theme + local approve/skip/edit marks). Everything else is read-only. No outbound network code.
- Run by hand: `cd ~/grok-trading-work/clipping-hub && python3 server.py` (Ctrl-C to stop).
- Tests: `python -m pytest -q` (needs pytest; the Banking Hub venv has it: `~/grok-trading-work/banking-hub/.venv/bin/python -m pytest -q`).

## Proposed keepalive plist (Banking Hub pattern: RunAtLoad, KeepAlive, ThrottleInterval 10)
Would be saved as `~/Library/LaunchAgents/com.luis.clippinghub.server.plist`. It mirrors `com.luis.bankinghub.server.plist`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.luis.clippinghub.server</string>
<key>ProgramArguments</key><array><string>/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python</string><string>/Users/luis/grok-trading-work/clipping-hub/server.py</string></array>
<key>WorkingDirectory</key><string>/Users/luis/grok-trading-work/clipping-hub</string>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ThrottleInterval</key><integer>10</integer>
<key>StandardOutPath</key><string>/Users/luis/Library/Logs/clippinghub-server.log</string>
<key>StandardErrorPath</key><string>/Users/luis/Library/Logs/clippinghub-server.log</string>
</dict></plist>
```

## Before going live (checklist, nothing below has been run)
1. Re-check the port is free: `lsof -nP -iTCP:8505 -sTCP:LISTEN` should print nothing.
2. Run the full suite and confirm all pass.
3. Review the branch `exterminator/clipping-hub-shell` and merge it locally if wanted. No remote exists; nothing is pushed.
4. Save the plist text above to `~/Library/LaunchAgents/com.luis.clippinghub.server.plist`.
5. Load it: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.luis.clippinghub.server.plist`
6. Check: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8505/` prints `200`.
7. Not part of this step and not proposed here: adding the app to `keepalive.sh`, Tailscale serve/HTTPS, or any channel connection.

## Rollback
1. Stop and unload the job: `launchctl bootout gui/$(id -u)/com.luis.clippinghub.server`
2. Remove the plist: `rm ~/Library/LaunchAgents/com.luis.clippinghub.server.plist`
3. Confirm the port is free: `lsof -nP -iTCP:8505 -sTCP:LISTEN` prints nothing. If a stray run-by-hand server is left, stop it by its exact PID (`kill <pid>`), not with `pkill`.
4. Optional: remove the log `~/Library/Logs/clippinghub-server.log`. `data/state.json` can stay; deleting it only resets the theme and sample approvals.
5. The code itself can be rolled back with `git checkout <previous-branch>` (everything is local commits).
