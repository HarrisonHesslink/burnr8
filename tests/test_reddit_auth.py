"""OAuth consent, callback validation and credential preservation."""

import os
import stat
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import pytest
from dotenv import dotenv_values

from burnr8.reddit.auth import authorization_url, callback_code, exchange_code, save_credentials
from burnr8.reddit.client import RedditAdsApiError


def test_authorization_requests_permanent_read_and_edit_with_exact_redirect():
    url = authorization_url("client", "http://localhost:8765/callback", "random-state")
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == ["adsread,adsedit"]
    assert query["duration"] == ["permanent"]
    assert query["redirect_uri"] == ["http://localhost:8765/callback"]
    assert query["state"] == ["random-state"]
    assert callback_code("state=random-state&code=opaque%2Bcode", "random-state") == "opaque+code"


@pytest.mark.parametrize(
    "query",
    [
        "code=secret",
        "state=%C3%A9&code=secret",
        "state=wrong&code=secret",
        "state=ok&state=wrong&code=secret",
        "state=ok&code=one&code=two",
        "state=ok&error=access_denied",
        "state=ok&code=",
    ],
)
def test_invalid_or_denied_callback_never_returns_code(query):
    with pytest.raises(ValueError) as error:
        callback_code(query, "ok")
    assert "secret" not in str(error.value)


def test_exchange_uses_basic_auth_and_does_not_expose_tokens():
    response = MagicMock(status_code=200)
    response.json.return_value = {"refresh_token": "refresh-secret", "scope": "adsread adsedit"}
    with patch("burnr8.reddit.auth.requests.post", return_value=response) as post:
        assert (
            exchange_code("app", "secret", "code", "http://localhost:8765/callback", "burnr8-test") == "refresh-secret"
        )
    assert post.call_args.kwargs["auth"] == ("app", "secret")
    assert post.call_args.kwargs["data"]["grant_type"] == "authorization_code"
    assert post.call_args.kwargs["allow_redirects"] is False
    assert "secret" not in post.call_args.args[0]


def test_local_callback_round_trip_does_not_log_authorization_code(monkeypatch, capsys):
    from burnr8.reddit import auth

    servers, threads, errors = [], [], []

    def make_server(address, handler):
        server = HTTPServer(("127.0.0.1", 0), handler)
        servers.append(server)
        return server

    def browser_open(url):
        state = parse_qs(urlsplit(url).query)["state"][0]
        query = urlencode({"state": state, "code": "private-authorization-code"})
        callback_url = f"http://127.0.0.1:{servers[0].server_port}/callback?{query}"

        def send_callback():
            try:
                with urlopen(callback_url, timeout=5) as response:  # noqa: S310 -- test-created loopback URL
                    assert response.status == 200
                    assert response.headers["Cache-Control"] == "no-store"
            except Exception as ex:
                errors.append(ex)

        thread = threading.Thread(target=send_callback)
        threads.append(thread)
        thread.start()
        return True

    monkeypatch.setattr(auth, "HTTPServer", make_server)
    monkeypatch.setattr(auth.webbrowser, "open", browser_open)
    result = auth.receive_code("http://localhost:8765/callback", "app", "random-state")
    for thread in threads:
        thread.join(timeout=5)
    assert not errors
    assert result == "private-authorization-code"
    captured = capsys.readouterr()
    assert "private-authorization-code" not in captured.out + captured.err


@pytest.mark.parametrize(
    "payload", [{}, {"refresh_token": "secret", "scope": "adsread"}, {"refresh_token": "", "scope": "adsread,adsedit"}]
)
def test_incomplete_oauth_grants_are_not_accepted(payload):
    response = MagicMock(status_code=200)
    response.json.return_value = payload
    with patch("burnr8.reddit.auth.requests.post", return_value=response), pytest.raises(RedditAdsApiError):
        exchange_code("app", "secret", "code", "http://localhost:8765/callback", "burnr8-test")


def test_atomic_save_preserves_other_providers_and_replaces_expired_access_token(tmp_path):
    path = tmp_path / ".burnr8" / ".env"
    path.parent.mkdir()
    path.write_text(
        "# Keep this comment\nGOOGLE_ADS_REFRESH_TOKEN='google-secret'\nMETA_ACCESS_TOKEN=meta-secret\nBURNR8_MAX_DAILY_BUDGET_DOLLARS=20\nREDDIT_ACCESS_TOKEN=expired-secret\n"
    )
    values = {
        "REDDIT_CLIENT_ID": "app",
        "REDDIT_CLIENT_SECRET": "reddit-secret",
        "REDDIT_REFRESH_TOKEN": "refresh-secret",
    }
    save_credentials(path, values)
    saved = dotenv_values(path)
    assert saved["GOOGLE_ADS_REFRESH_TOKEN"] == "google-secret"
    assert saved["META_ACCESS_TOKEN"] == "meta-secret"
    assert saved["BURNR8_MAX_DAILY_BUDGET_DOLLARS"] == "20"
    assert saved["REDDIT_REFRESH_TOKEN"] == "refresh-secret"
    assert "REDDIT_ACCESS_TOKEN" not in saved
    assert "# Keep this comment" in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob(".reddit-env-*"))


def test_failed_atomic_save_leaves_original_credentials_untouched(tmp_path):
    path = tmp_path / ".env"
    path.write_text("META_ACCESS_TOKEN=existing\n")
    with patch("burnr8.reddit.auth.set_key", side_effect=OSError("disk full")), pytest.raises(OSError):
        save_credentials(path, {"REDDIT_REFRESH_TOKEN": "new"})
    assert path.read_text() == "META_ACCESS_TOKEN=existing\n"
    assert not list(tmp_path.glob(".reddit-env-*"))


def test_general_setup_preserves_reddit_settings(tmp_path, monkeypatch):
    from burnr8 import setup

    monkeypatch.setattr(setup, "BURNR8_DIR", tmp_path)
    monkeypatch.setattr(setup, "ENV_FILE", tmp_path / ".env")
    setup._save_env(
        {
            "REDDIT_CLIENT_ID": "app",
            "REDDIT_CLIENT_SECRET": "secret",
            "REDDIT_REFRESH_TOKEN": "refresh",
            "REDDIT_AD_ACCOUNT_ID": "a2_test",
            "BURNR8_REDDIT_MAX_SPEND_CAP_DOLLARS": "100",
        }
    )
    saved = dotenv_values(tmp_path / ".env")
    assert saved["REDDIT_REFRESH_TOKEN"] == "refresh"
    assert saved["REDDIT_AD_ACCOUNT_ID"] == "a2_test"
    assert saved["BURNR8_REDDIT_MAX_SPEND_CAP_DOLLARS"] == "100"


@pytest.mark.skipif(os.name == "nt", reason="Symlink permissions vary on Windows")
def test_setup_refuses_symlink_env(tmp_path):
    original = tmp_path / "original"
    original.write_text("existing")
    link = tmp_path / ".env"
    link.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        save_credentials(link, {"REDDIT_REFRESH_TOKEN": "new"})
    assert original.read_text() == "existing"
