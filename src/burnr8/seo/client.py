"""Small REST clients for Google's Search Console, PageSpeed, and CrUX APIs."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import requests

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_WEBMASTERS_ROOT = "https://www.googleapis.com/webmasters/v3"
_INSPECTION_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
_PAGESPEED_URL = "https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"
_CRUX_URL = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"


class GoogleSeoApiError(RuntimeError):
    """A sanitized error from a Google SEO API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reason: str | None = None,
        service: str | None = None,
    ) -> None:
        super().__init__(message[:500])
        self.status_code = status_code
        self.reason = reason
        self.service = service

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"error": True, "message": str(self)}
        optional = {
            "http_status": self.status_code,
            "reason": self.reason,
            "service": self.service,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


class SearchConsoleClient:
    """OAuth REST client restricted to Search Console API hosts and operations."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        missing = [
            name
            for name, value in (
                ("client ID", client_id),
                ("client secret", client_secret),
                ("refresh token", refresh_token),
            )
            if not value.strip()
        ]
        if missing:
            raise OSError(f"Missing Search Console OAuth {'/'.join(missing)}.")
        if timeout <= 0:
            raise ValueError("Google SEO API timeout must be positive.")
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._timeout = timeout
        self._session = session or requests.Session()
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def list_properties(self) -> dict[str, Any]:
        return self._request("GET", f"{_WEBMASTERS_ROOT}/sites", service="search_console")

    def get_property(self, property_url: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{_WEBMASTERS_ROOT}/sites/{quote(property_url, safe='')}",
            service="search_console",
        )

    def query_search_analytics(self, property_url: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{_WEBMASTERS_ROOT}/sites/{quote(property_url, safe='')}/searchAnalytics/query",
            json_body=body,
            service="search_console",
        )

    def inspect_url(self, property_url: str, inspection_url: str, language_code: str = "en-US") -> dict[str, Any]:
        return self._request(
            "POST",
            _INSPECTION_URL,
            json_body={"inspectionUrl": inspection_url, "siteUrl": property_url, "languageCode": language_code},
            service="url_inspection",
        )

    def list_sitemaps(self, property_url: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{_WEBMASTERS_ROOT}/sites/{quote(property_url, safe='')}/sitemaps",
            service="search_console",
        )

    def submit_sitemap(self, property_url: str, sitemap_url: str) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"{_WEBMASTERS_ROOT}/sites/{quote(property_url, safe='')}/sitemaps/{quote(sitemap_url, safe='')}",
            service="search_console",
            allow_no_content=True,
        )

    def _access_token_value(self) -> str:
        if self._access_token and time.monotonic() < self._access_token_expires_at:
            return self._access_token
        with self._token_lock:
            if self._access_token and time.monotonic() < self._access_token_expires_at:
                return self._access_token
            response = self._session.request(
                "POST",
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=self._timeout,
                allow_redirects=False,
            )
            payload = _decode_response(
                response,
                "oauth",
                allow_no_content=False,
                redactions=(self._client_id, self._client_secret, self._refresh_token),
            )
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise GoogleSeoApiError(
                    "Google OAuth response did not include an access token.",
                    status_code=response.status_code,
                    service="oauth",
                )
            try:
                expires_in = max(60, int(payload.get("expires_in", 3600)))
            except (TypeError, ValueError):
                expires_in = 3600
            self._access_token = token
            self._access_token_expires_at = time.monotonic() + max(30, expires_in - 60)
            return token

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        service: str,
        allow_no_content: bool = False,
    ) -> dict[str, Any]:
        if method not in {"GET", "POST", "PUT"}:
            raise ValueError("SearchConsoleClient only supports GET, POST, and PUT.")
        access_token = self._access_token_value()
        response = self._session.request(
            method,
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=dict(json_body) if json_body is not None else None,
            timeout=self._timeout,
            allow_redirects=False,
        )
        return _decode_response(
            response,
            service,
            allow_no_content=allow_no_content,
            redactions=(self._client_id, self._client_secret, self._refresh_token, access_token),
        )


class GooglePerformanceClient:
    """Public PageSpeed and keyed CrUX client with fixed Google endpoints."""

    def __init__(
        self,
        *,
        pagespeed_api_key: str | None = None,
        crux_api_key: str | None = None,
        timeout: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Google performance API timeout must be positive.")
        self._pagespeed_api_key = pagespeed_api_key or None
        self._crux_api_key = crux_api_key or pagespeed_api_key or None
        self._timeout = timeout
        self._session = session or requests.Session()

    @property
    def crux_configured(self) -> bool:
        return self._crux_api_key is not None

    def pagespeed(
        self,
        url: str,
        *,
        strategy: str,
        categories: Sequence[str],
        locale: str = "en_US",
    ) -> dict[str, Any]:
        params: list[tuple[str, str]] = [("url", url), ("strategy", strategy), ("locale", locale)]
        params.extend(("category", category) for category in categories)
        if self._pagespeed_api_key:
            params.append(("key", self._pagespeed_api_key))
        response = self._session.request(
            "GET", _PAGESPEED_URL, params=params, timeout=self._timeout, allow_redirects=False
        )
        return _decode_response(
            response,
            "pagespeed",
            allow_no_content=False,
            redactions=(self._pagespeed_api_key or "",),
        )

    def crux(self, url: str, *, form_factor: str | None = None, origin: bool = False) -> dict[str, Any]:
        if not self._crux_api_key:
            raise OSError("GOOGLE_CRUX_API_KEY (or GOOGLE_PAGESPEED_API_KEY) is required for CrUX data.")
        body: dict[str, Any] = {"origin" if origin else "url": url}
        if form_factor:
            body["formFactor"] = form_factor
        response = self._session.request(
            "POST",
            _CRUX_URL,
            params={"key": self._crux_api_key},
            json=body,
            timeout=self._timeout,
            allow_redirects=False,
        )
        return _decode_response(
            response,
            "crux",
            allow_no_content=False,
            redactions=(self._crux_api_key,),
        )


def get_search_console_client() -> SearchConsoleClient:
    """Build a Search Console client from dedicated OAuth configuration."""
    refresh_token = os.environ.get("GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN", "")
    client_id = os.environ.get("GOOGLE_SEARCH_CONSOLE_CLIENT_ID") or os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET") or os.environ.get(
        "GOOGLE_ADS_CLIENT_SECRET", ""
    )
    if not refresh_token:
        raise OSError(
            "GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN is not configured. Authorize a refresh token with the "
            "webmasters.readonly scope (or webmasters for sitemap submission), add it to ~/.burnr8/.env, "
            "then restart the MCP server."
        )
    return SearchConsoleClient(client_id, client_secret, refresh_token)


def get_performance_client() -> GooglePerformanceClient:
    return GooglePerformanceClient(
        pagespeed_api_key=os.environ.get("GOOGLE_PAGESPEED_API_KEY"),
        crux_api_key=os.environ.get("GOOGLE_CRUX_API_KEY"),
    )


def _decode_response(
    response: requests.Response,
    service: str,
    *,
    allow_no_content: bool,
    redactions: Sequence[str] = (),
) -> dict[str, Any]:
    if allow_no_content and response.status_code == 204:
        return {}
    try:
        payload = response.json()
    except (requests.exceptions.JSONDecodeError, ValueError):
        raise GoogleSeoApiError(
            f"Google {service} returned a non-JSON response (HTTP {response.status_code}).",
            status_code=response.status_code,
            service=service,
        ) from None
    if not isinstance(payload, dict):
        raise GoogleSeoApiError(
            f"Google {service} returned an unexpected response (HTTP {response.status_code}).",
            status_code=response.status_code,
            service=service,
        )
    if 200 <= response.status_code < 300:
        return payload

    raw_error = payload.get("error")
    error = raw_error if isinstance(raw_error, Mapping) else {}
    message = error.get("message")
    reason: str | None = None
    details = error.get("errors")
    if isinstance(details, list) and details and isinstance(details[0], Mapping):
        raw_reason = details[0].get("reason")
        reason = _redact_error_text(raw_reason, redactions, 100) if raw_reason is not None else None
    safe_message = (
        _redact_error_text(message, redactions, 500)
        if message
        else f"Google {service} request failed with HTTP {response.status_code}."
    )
    raise GoogleSeoApiError(
        safe_message,
        status_code=response.status_code,
        reason=reason,
        service=service,
    )


def _redact_error_text(value: Any, secrets: Sequence[str], limit: int) -> str:
    text = str(value)
    for secret in sorted(set(secrets) - {""}, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text[:limit]
