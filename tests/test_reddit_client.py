"""HTTP contract and credential boundary tests for Reddit Ads."""

# ruff: noqa: S106 -- all credentials in this module are synthetic test values.

from unittest.mock import MagicMock, patch

import pytest
import requests

from burnr8.reddit.client import RedditAdsApiError, RedditAdsClient, get_reddit_client, validate_page_url


def response(data, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = data
    return result


def test_refresh_once_per_client_and_send_json_envelope_with_bearer_header():
    session = MagicMock()
    session.post.return_value = response({"access_token": "access-secret"})
    session.request.return_value = response({"data": {"id": "123"}})
    client = RedditAdsClient(client_id="app", client_secret="secret", refresh_token="refresh-secret", session=session)
    client.request("GET", "ad_accounts/a2_test")
    client.request("PATCH", "campaigns/123", body={"data": {"configured_status": "PAUSED"}})
    session.post.assert_called_once()
    token_kwargs = session.post.call_args.kwargs
    assert token_kwargs["auth"] == ("app", "secret")
    assert token_kwargs["data"] == {"grant_type": "refresh_token", "refresh_token": "refresh-secret"}
    assert token_kwargs["allow_redirects"] is False
    assert session.request.call_args.args == ("PATCH", "https://ads-api.reddit.com/api/v3/campaigns/123")
    kwargs = session.request.call_args.kwargs
    assert kwargs["headers"]["Authorization"] == "Bearer access-secret"
    assert kwargs["json"] == {"data": {"configured_status": "PAUSED"}}
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == 30
    assert "refresh-secret" not in repr(session.request.call_args_list)


@pytest.mark.parametrize(
    "path", ["https://evil.test", "//evil.test", "campaigns/../ads", "campaigns/1?x=1", "campaigns/1%2f2", ""]
)
def test_bad_paths_never_send_credentials(path):
    session = MagicMock()
    client = RedditAdsClient(access_token="secret", session=session)
    with pytest.raises(ValueError):
        client.request("GET", path)
    session.request.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/api/v3/campaigns/123?page.token=x",
        "https://ads-api.reddit.com.evil.test/api/v3/campaigns/123?page.token=x",
        "https://user:pass@ads-api.reddit.com/api/v3/campaigns/123?page.token=x",
        "http://ads-api.reddit.com/api/v3/campaigns/123?page.token=x",
        "https://ads-api.reddit.com/api/v3/campaigns/456?page.token=x",
        "https://ads-api.reddit.com/api/v3/campaigns/123?access_token=secret",
    ],
)
def test_pagination_rejects_cross_resource_urls_and_credential_queries(url):
    with pytest.raises(ValueError):
        validate_page_url(url, "campaigns/123")


def test_pagination_follows_exact_provider_url_without_rebuilding_query():
    session = MagicMock()
    session.request.return_value = response({"data": []})
    client = RedditAdsClient(access_token="token", session=session)
    url = "https://ads-api.reddit.com/api/v3/ad_accounts/a2_test/reports?page.token=opaque%2Bvalue&page.size=10"
    body = {"data": {"fields": ["SPEND"]}}
    client.request("POST", "ad_accounts/a2_test/reports", params={"page.size": 100}, body=body, next_url=url)
    assert session.request.call_args.args == ("POST", url)
    assert session.request.call_args.kwargs["params"] is None
    assert session.request.call_args.kwargs["json"] == body


@pytest.mark.parametrize("size", ["0", "1001", "-1", "junk", "10&page.size=20"])
def test_pagination_cannot_bypass_page_size_bound(size):
    with pytest.raises(ValueError):
        validate_page_url(f"https://ads-api.reddit.com/api/v3/campaigns/123?page.size={size}", "campaigns/123")


@pytest.mark.parametrize("status", [302, 400, 401, 403, 429, 500])
def test_provider_errors_never_echo_body_or_retry(status):
    session = MagicMock()
    session.request.return_value = response({"error": {"message": "secret-token-and-customer-data"}}, status)
    client = RedditAdsClient(access_token="secret-token", session=session)
    with pytest.raises(RedditAdsApiError) as error:
        client.request("PATCH", "campaigns/123", body={"data": {"configured_status": "PAUSED"}})
    assert "secret" not in str(error.value)
    assert error.value.status_code == status
    session.request.assert_called_once()


def test_non_json_and_missing_oauth_token_are_sanitized():
    session = MagicMock()
    session.post.return_value = response({"refresh_token": "secret-refresh"})
    client = RedditAdsClient(client_id="app", client_secret="secret", refresh_token="refresh", session=session)
    with pytest.raises(RedditAdsApiError, match="did not return an access token"):
        client.request("GET", "me")
    session.request.assert_not_called()
    session.post.return_value.json.side_effect = ValueError("secret proxy body")
    with pytest.raises(RedditAdsApiError, match="non-JSON"):
        client.request("GET", "me")


def test_missing_credentials_are_lazy_and_actionable():
    with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="burnr8-reddit-setup"):
        get_reddit_client()


def test_network_failure_is_not_retried():
    session = MagicMock()
    session.request.side_effect = requests.Timeout("secret query in upstream error")
    client = RedditAdsClient(access_token="token", session=session)
    with pytest.raises(requests.Timeout):
        client.request("POST", "ad_accounts/a2_test/campaigns")
    session.request.assert_called_once()
