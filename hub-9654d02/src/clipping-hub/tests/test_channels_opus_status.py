"""Channels pane: Opus connected vs hub YouTube grant missing (no false connected)."""
from pathlib import Path
import json

import clipper_data as cd

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static/index.html").read_text()
JS = (ROOT / "static/app.js").read_text()


def test_channels_api_loads_opus_rows(tmp_path):
    p = tmp_path / "channels.json"
    p.write_text(json.dumps([
        {"post_account_id": "a", "platform": "YOUTUBE", "name": "Clipped Motions",
         "profile_url": "https://www.youtube.com/channel/UCgMuVjQmB9WvZtSz4e23THw"},
        {"post_account_id": "b", "platform": "TIKTOK_BUSINESS", "name": "Clipped Motions", "profile_url": ""},
    ]))
    out = cd.load_channels(p)
    assert out["empty"] is False
    assert len(out["channels"]) == 2
    assert out["channels"][0]["platform"] == "YOUTUBE"


def test_ui_renders_opus_and_hub_grant_chips():
    assert "Connected in Opus" in JS
    assert "Hub YouTube grant missing" in JS
    assert "renderChannelsPane" in JS
    assert "hubYtGrantForOpusRow" in JS
    assert 'id="channels-slots"' in HTML
    # Must not claim falsely connected via static placeholder
    assert "Not connected yet" not in HTML
    assert "Connect channel" not in HTML
