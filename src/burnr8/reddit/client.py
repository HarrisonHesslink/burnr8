"""Request-local Reddit Ads client. Credentials never enter query strings."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests

API_ROOT = "https://ads-api.reddit.com/api/v3"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
DEFAULT_USER_AGENT = "burnr8/0.7.1 (Reddit Ads API)"
_PATH = re.compile(r"[a-z0-9_]+(?:/[A-Za-z0-9_-]+)*")


class RedditAdsApiError(RuntimeError):
    """Provider failure without echoing response bodies or credentials."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def decode_response(response: requests.Response, service: str) -> dict[str, Any]:
    """Decode JSON while keeping auth failures and proxy bodies out of logs."""
    if not 200 <= response.status_code < 300:
        hint = {
            400: "Check the request fields against Reddit's v3 API documentation.",
            401: "Reauthorize the Reddit application.",
            403: "Check OAuth scopes and access to the selected ad account.",
            429: "Rate limit reached; wait before retrying.",
        }.get(response.status_code, "Check Reddit's service status before retrying.")
        raise RedditAdsApiError(f"{service} returned HTTP {response.status_code}. {hint}", response.status_code)
    try:
        payload = response.json()
    except ValueError:
        raise RedditAdsApiError(f"{service} returned a non-JSON response.", response.status_code) from None
    if not isinstance(payload, dict) or "error" in payload:
        raise RedditAdsApiError(f"{service} returned an invalid response.", response.status_code)
    return payload


def validate_page_url(url: str, path: str) -> str:
    """Follow Reddit's opaque pagination URL only on the same API resource."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "ads-api.reddit.com"
        or parsed.path != f"/api/v3/{path}"
        or parsed.fragment
        or any(ord(c) < 32 for c in url)
    ):
        raise ValueError("Reddit pagination URL must point to the same API resource.")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) - {
        "page.token",
        "page.size",
        "query",
        "campaign_id",
        "id",
        "ids",
        "role",
        "ad_account_id",
        "source",
        "creative_asset_ids",
    }:
        raise ValueError("Reddit pagination URL contains unsupported query parameters.")
    sizes = query.get("page.size", [])
    maximum = 700 if path == "me/businesses" else 1000
    if re.fullmatch(r"ad_accounts/[^/]+/profiles|profiles/[^/]+/structured_posts", path):
        maximum = 100
    if sizes and (len(sizes) != 1 or not sizes[0].isdigit() or not 1 <= int(sizes[0]) <= maximum):
        raise ValueError("Reddit pagination page size exceeds the supported bound.")
    return url


class RedditAdsClient:
    """Small v3 REST client; no mutation retries or cross-request token cache."""

    def __init__(
        self,
        *,
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        access_token: str = "",
        user_agent: str = DEFAULT_USER_AGENT,
        session: requests.Session | None = None,
    ) -> None:
        if not access_token and not (client_id and client_secret and refresh_token):
            raise OSError(
                "Reddit Ads credentials are missing. Run burnr8-reddit-setup, or set REDDIT_CLIENT_ID, "
                "REDDIT_CLIENT_SECRET and REDDIT_REFRESH_TOKEN in ~/.burnr8/.env, then restart the MCP server."
            )
        if not user_agent.strip() or any(ord(c) < 32 for c in user_agent):
            raise ValueError("REDDIT_USER_AGENT must be a non-empty single-line value.")
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token = access_token
        self._user_agent = user_agent
        self._session = session or requests.Session()

    def _token(self) -> str:
        if not self._access_token:
            response = self._session.post(
                TOKEN_URL,
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
                headers={"User-Agent": self._user_agent},
                timeout=30,
                allow_redirects=False,
            )
            payload = decode_response(response, "Reddit OAuth")
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise RedditAdsApiError("Reddit OAuth did not return an access token.")
            self._access_token = token
        return self._access_token

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        next_url: str | None = None,
    ) -> dict[str, Any]:
        """Send a single bounded request to the fixed Reddit Ads origin."""
        if method not in {"GET", "POST", "PATCH"} or not _PATH.fullmatch(path):
            raise ValueError("Unsupported Reddit API method or resource path.")
        url = validate_page_url(next_url, path) if next_url else f"{API_ROOT}/{path}"
        response = self._session.request(
            method,
            url,
            params=None if next_url else params,
            json=body,
            headers={"Authorization": f"Bearer {self._token()}", "User-Agent": self._user_agent},
            timeout=30,
            allow_redirects=False,
        )
        return decode_response(response, "Reddit Ads API")


def get_reddit_client() -> RedditAdsClient:
    """Load only Reddit credentials; Google and Meta tokens cannot be reused."""
    return RedditAdsClient(
        client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
        refresh_token=os.environ.get("REDDIT_REFRESH_TOKEN", ""),
        access_token=os.environ.get("REDDIT_ACCESS_TOKEN", ""),
        user_agent=os.environ.get("REDDIT_USER_AGENT", DEFAULT_USER_AGENT),
    )
