# Test baseline (this import)

Command: `python3 -m pytest -q -p no:cacheprovider` on the imported tree before fixtures and before the public-publish work.

| Run | Result |
| --- | --- |
| Before `data/post_targets.json` and `static/samples/*.mp4` | 273 passed, 32 skipped, 8 failed, 8 errors |
| After adapters, with Playwright Chromium from `requirements.txt` | 343 passed, 4 skipped |

The 4 skips are `tests/test_channels_no_overlap.py` (3) and `tests/test_channels_render_from_api.py` (1). They look for `/workspace/api-channels-live.json`, which was not in the sanitized export. They are not the old browser skips. Those 32 browser tests now run and pass.

The 8 errors were one collection error (`tests/test_schedule_routing.py` reading missing `data/post_targets.json`) and seven `tests/test_samples_range.py` failures reported as errors because `static/samples/sample-a.mp4` was not in the export.

The 8 failures were YouTube grant tests. A saved token was reported as `grant_expired` / `needs_oauth` because `expected_yt_for_hub_channel` had no targets file, so the channel bind check failed closed. They pass once the synthetic targets file is present. No test was deleted or loosened to get there.

The 32 skips are the same playwright cases (no browser engine in this environment). The exported Mac run was reported as 304 passed, 9 failed, 8 errors; that count is not reproduced here and the two trees were not proven identical.

`tests/test_import_deadbolt.py` checks this tree for obvious live-secret markers and for the private click hostname that used to be hardcoded in `push_alerts.py`. The click URL is `CLIPPING_HUB_CLICK`, or the file `CLIPPING_HUB_CLICK_FILE` (default `~/.config/clipping-hub/click-url`). There is no loopback default in source. Tests set `CLIPPING_HUB_CLICK` before import. A missing click URL omits the Click header and still sends the notification.
