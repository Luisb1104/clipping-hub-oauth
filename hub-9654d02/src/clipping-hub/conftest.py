# Isolate every test from live hub state, tokens, and production routing files.
# Env is set before server, youtube_label_step, schedule_hook, or post_idempotency
# are imported. Those modules bind path constants at import time.
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
_REAL_HOME = os.environ.get("HOME") or str(Path.home())
_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(
    Path(_REAL_HOME) / ".cache" / "ms-playwright"
)
_ISO = Path(tempfile.mkdtemp(prefix="ch-home-"))
_OAUTH = _ISO / "youtube-oauth"
_OAUTH.mkdir(parents=True, exist_ok=True)

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _BROWSERS
# Subprocesses (shots.py) start a new interpreter. User-site packages live under
# the original home; keep that directory on PYTHONPATH after HOME is isolated.
_USER_SITE = str(
    Path(_REAL_HOME) / ".local" / "lib" / ("python%d.%d" % sys.version_info[:2]) / "site-packages"
)
_prior_path = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
if _USER_SITE not in _prior_path:
    os.environ["PYTHONPATH"] = os.pathsep.join([_USER_SITE] + _prior_path)
os.environ["HOME"] = str(_ISO)
os.environ["CLIP_YT_OAUTH_DIR"] = str(_OAUTH)
os.environ["CLIP_YT_CLIENT_ID_FILE"] = str(_OAUTH / "client_id")
os.environ["CLIP_YT_CLIENT_SECRET_FILE"] = str(_OAUTH / "client_secret")
os.environ["CLIP_YT_OAUTH_STATE_DIR"] = str(_OAUTH / "state")
os.environ["CLIP_OPUS_API_TOKEN_FILE"] = str(_ISO / "opus-api-token")
os.environ["CLIPPING_HUB_POST_TARGETS"] = str(ROOT / "tests" / "fixtures" / "post_targets.json")
os.environ["CLIPPING_HUB_SAMPLES_DIR"] = str(ROOT / "tests" / "fixtures" / "samples")
os.environ["CLIPPING_HUB_POST_LEDGER"] = str(_ISO / "post_ledger.jsonl")
os.environ["CLIPPING_HUB_APPROVALS"] = str(_ISO / "approvals.json")
os.environ["CLIPPING_HUB_EVENTS"] = str(_ISO / "events.json")
os.environ["CLIP_YT_TICK_STATE"] = str(_ISO / "youtube_label_tick.json")
os.environ["CLIPPING_HUB_STATE"] = str(_ISO / "state.json")
os.environ["CLIPPING_HUB_NOTIFY_STATE"] = str(_ISO / "notify_state.json")
os.environ["TT_NTFY_TOPIC_FILE"] = str(_ISO / "no-topic")
os.environ["CLIPPING_HUB_CLICK_FILE"] = str(_ISO / "click-url")
os.environ["CLIPPING_HUB_CLICK_HOSTS_FILE"] = str(_ISO / "click-hosts")
# Trust is the host list, not the URL. Tests opt in to one HTTPS host.
os.environ["CLIPPING_HUB_CLICK_HOSTS"] = "hub.example.test"
os.environ["CLIPPING_HUB_CLICK"] = "https://hub.example.test/approvals"
os.environ["CLIPPING_HUB_PUBLISH_CONFIG"] = str(_ISO / "publish-config.json")

sys.path.insert(0, str(ROOT))
import server  # noqa: E402


class Live:
    def __init__(self, tmp):
        self.dir = Path(tmp)
        self.state = self.dir / "data" / "state.json"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(self.state))
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


@pytest.fixture
def live(tmp_path):
    s = Live(tmp_path)
    yield s
    s.close()
