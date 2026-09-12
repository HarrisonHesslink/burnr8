"""Tests for Google Search Console and performance REST clients."""

from unittest.mock import MagicMock, patch

import pytest

from burnr8.seo.client import (
    GooglePerformanceClient,
    GoogleSeoApiError,
    SearchConsoleClient,
    get_search_console_client,
)
from burnr8.seo.session import (
    normalize_search_console_property,
    require_search_console_property,
    set_active_search_console_property,
    validate_url_for_property,
)


def _response(payload, *, status=200, ok=True):
    response = MagicMock()
    response.json.return_value = payload
    response.status_code = status
    response.ok = ok
    return response


def test_search_console_refreshes_oauth_and_encodes_property_path():
    session = MagicMock()
    session.request.side_effect = [
        _response({"access_token": "access-123", "expires_in": 3600}),
        _response({"rows": []}),
        _response({"siteUrl": "sc-domain:studywithlily.com"}),
    ]
    client = SearchConsoleClient("client-id", "client-secret", "refresh-token", session=session)

    result = client.query_search_analytics(
        "sc-domain:studywithlily.com",
        {"startDate": "2026-06-01", "endDate": "2026-06-30", "dimensions": ["query"]},
    )
    client.get_property("sc-domain:studywithlily.com")

    assert result == {"rows": []}
    oauth = session.request.call_args_list[0]
    assert oauth.args[:2] == ("POST", "https://oauth2.googleapis.com/token")
    assert oauth.kwargs["data"]["refresh_token"] == "refresh-token"
    assert all(call.kwargs["allow_redirects"] is False for call in session.request.call_args_list)
    analytics = session.request.call_args_list[1]
    assert analytics.args[0] == "POST"
    assert "/sites/sc-domain%3Astudywithlily.com/searchAnalytics/query" in analytics.args[1]
    assert analytics.kwargs["headers"] == {"Authorization": "Bearer access-123"}
    assert session.request.call_count == 3  # OAuth token is reused for the second API request.


def test_sitemap_submit_accepts_google_204_response():
    session = MagicMock()
    session.request.side_effect = [
        _response({"access_token": "access", "expires_in": 3600}),
        _response({}, status=204),
    ]
    client = SearchConsoleClient("id", "secret", "refresh", session=session)

    assert client.submit_sitemap("https://studywithlily.com/", "https://studywithlily.com/sitemap.xml") == {}
    submit = session.request.call_args_list[1]
    assert submit.args[0] == "PUT"
    assert "https%3A%2F%2Fstudywithlily.com%2Fsitemap.xml" in submit.args[1]


def test_google_api_error_redacts_all_credentials():
    session = MagicMock()
    session.request.side_effect = [
        _response({"access_token": "access-secret", "expires_in": 3600}),
        _response(
            {
                "error": {
                    "message": "bad client-secret refresh-secret access-secret",
                    "errors": [{"reason": "forbidden"}],
                }
            },
            status=403,
            ok=False,
        ),
    ]
    client = SearchConsoleClient("client-id", "client-secret", "refresh-secret", session=session)

    with pytest.raises(GoogleSeoApiError) as exc_info:
        client.list_properties()

    rendered = repr(exc_info.value.as_dict())
    assert "client-secret" not in rendered
    assert "refresh-secret" not in rendered
    assert "access-secret" not in rendered
    assert exc_info.value.reason == "forbidden"


def test_performance_client_keeps_pagespeed_and_crux_independent():
    session = MagicMock()
    session.request.side_effect = [_response({"lighthouseResult": {}}), _response({"record": {}})]
    client = GooglePerformanceClient(pagespeed_api_key="speed-key", crux_api_key="crux-key", session=session)

    client.pagespeed("https://studywithlily.com/", strategy="mobile", categories=["PERFORMANCE", "SEO"])
    client.crux("https://studywithlily.com/", form_factor="PHONE")

    psi = session.request.call_args_list[0]
    assert ("category", "PERFORMANCE") in psi.kwargs["params"]
    assert ("key", "speed-key") in psi.kwargs["params"]
    crux = session.request.call_args_list[1]
    assert crux.kwargs["params"] == {"key": "crux-key"}
    assert crux.kwargs["json"]["formFactor"] == "PHONE"
    assert psi.kwargs["allow_redirects"] is False
    assert crux.kwargs["allow_redirects"] is False


def test_google_error_redacts_reason_and_truncation_boundaries():
    token = "private-access-value"
    session = MagicMock()
    session.request.side_effect = [
        _response({"access_token": token}),
        _response({"error": {"message": "x" * 495 + token, "errors": [{"reason": token}]}}, status=403, ok=False),
    ]
    client = SearchConsoleClient("client-id", "client-secret", "refresh-secret", session=session)
    with pytest.raises(GoogleSeoApiError) as caught:
        client.list_properties()
    assert str(caught.value) == "x" * 495 + "[REDA"
    assert caught.value.reason == "[REDACTED]"


def test_oauth_redirect_does_not_forward_refresh_credentials():
    session = MagicMock()
    session.request.return_value = _response({}, status=307)
    client = SearchConsoleClient("client-id", "client-secret", "refresh-secret", session=session)
    with pytest.raises(GoogleSeoApiError):
        client.list_properties()
    assert session.request.call_count == 1
    assert session.request.call_args.kwargs["allow_redirects"] is False


def test_missing_search_console_refresh_token_is_actionable():
    with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN"):
        get_search_console_client()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sc-domain:StudyWithLily.com", "sc-domain:studywithlily.com"),
        ("https://StudyWithLily.com", "https://studywithlily.com/"),
        ("https://studywithlily.com/blog", "https://studywithlily.com/blog/"),
    ],
)
def test_property_normalization(raw, expected):
    assert normalize_search_console_property(raw) == expected


def test_property_resolution_and_url_ownership():
    with patch.dict("os.environ", {"GOOGLE_SEARCH_CONSOLE_PROPERTY": "sc-domain:example.com"}, clear=True):
        assert require_search_console_property(None) == "sc-domain:example.com"
    set_active_search_console_property("https://studywithlily.com/blog/")
    assert require_search_console_property(None) == "https://studywithlily.com/blog/"
    assert (
        validate_url_for_property("https://studywithlily.com/blog/study-tips", "https://studywithlily.com/blog/")
        == "https://studywithlily.com/blog/study-tips"
    )
    with pytest.raises(ValueError, match="does not belong"):
        validate_url_for_property("https://evil.test/blog/", "https://studywithlily.com/blog/")


def test_domain_property_accepts_subdomains_but_not_suffix_confusion():
    assert validate_url_for_property("https://app.studywithlily.com/daily", "sc-domain:studywithlily.com")
    with pytest.raises(ValueError, match="does not belong"):
        validate_url_for_property("https://studywithlily.com.evil.test/", "sc-domain:studywithlily.com")
