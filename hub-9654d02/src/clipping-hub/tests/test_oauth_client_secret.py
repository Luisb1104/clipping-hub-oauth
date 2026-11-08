"""read_client_secret falls back to client_secret.json web.client_secret only when its client_id matches (missing_client hotfix)."""
import json
import pytest
import youtube_label_step as Y

CID = "123-abc.apps.googleusercontent.com"


@pytest.fixture
def d(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "CLIENT_ID_FILE", tmp_path / "client_id")
    monkeypatch.setattr(Y, "CLIENT_SECRET_FILE", tmp_path / "client_secret")
    (tmp_path / "client_id").write_text(CID + "\n")
    return tmp_path


def _json(d, cid=CID, secret="json-secret"):
    (d / "client_secret.json").write_text(json.dumps({"web": {"client_id": cid, "client_secret": secret}}))


def test_plain_file_only(d):
    (d / "client_secret").write_text("plain-secret\n")
    assert Y.read_client_secret() == "plain-secret"


def test_json_only_matching_client_id(d):
    _json(d)
    assert Y.read_client_secret() == "json-secret"


def test_json_client_id_mismatch_stays_missing(d):
    _json(d, cid="999-other.apps.googleusercontent.com")
    assert Y.read_client_secret() is None
    assert Y.exchange_code("c", http_post=lambda *a: pytest.fail("no POST")) == (None, "missing_client")


def test_neither_file(d):
    assert Y.read_client_secret() is None
    assert Y.exchange_code("c", http_post=lambda *a: pytest.fail("no POST")) == (None, "missing_client")


def test_exchange_posts_client_fields_from_json(d):
    _json(d)
    sent = []
    data, err = Y.exchange_code("the-code", redirect_uri="https://x/cb", code_verifier="v",
                                http_post=lambda url, body: sent.append((url, body)) or {"refresh_token": "r", "access_token": "a"})
    assert err is None and data["refresh_token"] == "r"
    url, body = sent[0]
    assert url == Y.TOKEN_URI and body["client_id"] == CID and body["client_secret"] == "json-secret"
    assert body["grant_type"] == "authorization_code" and body["code"] == "the-code" and body["code_verifier"] == "v"


@pytest.mark.parametrize("ch", ["MAIN", "PAID"])
def test_refresh_uses_same_client_path(d, monkeypatch, ch):
    _json(d)
    monkeypatch.setattr(Y, "grant_meta", lambda *a, **k: {"expired": False})
    monkeypatch.setattr(Y, "load_token", lambda c: {"refresh_token": "rt-" + c})
    monkeypatch.setattr(Y, "save_token", lambda *a, **k: None)
    monkeypatch.setattr(Y, "token_bind_ok", lambda *a, **k: True)
    sent = []
    Y.refresh_access(ch, http_post=lambda url, body: sent.append(body) or {"access_token": "a", "expires_in": 3600})
    assert sent and sent[0]["client_secret"] == "json-secret" and sent[0]["refresh_token"] == "rt-" + ch
