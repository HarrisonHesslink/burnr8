"""Small, typed client for the Meta Marketing API.

The official SDK stores credentials in process-global state.  Burnr8 keeps the
client local to each tool invocation instead so concurrent MCP users cannot
leak credentials or account context across requests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping
from typing import Any

import requests

_GRAPH_API_ROOT = "https://graph.facebook.com"
_DEFAULT_API_VERSION = "v25.0"
_VERSION_RE = re.compile(r"^v\d+\.\d+$")


class MetaAdsApiError(RuntimeError):
    """A sanitized error returned by the Meta Graph API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str | None = None,
        code: int | None = None,
        error_subcode: int | None = None,
        is_transient: bool | None = None,
        user_title: str | None = None,
        user_message: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(message[:500])
        self.status_code = status_code
        self.error_type = error_type
        self.code = code
        self.error_subcode = error_subcode
        self.is_transient = is_transient
        self.user_title = user_title
        self.user_message = user_message
        self.trace_id = trace_id

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], status_code: int) -> MetaAdsApiError:
        raw = payload.get("error", payload)
        error = raw if isinstance(raw, Mapping) else {}
        message = error.get("message")
        return cls(
            str(message) if message else f"Meta Marketing API request failed with HTTP {status_code}",
            status_code=status_code,
            error_type=_optional_str(error.get("type")),
            code=_optional_int(error.get("code")),
            error_subcode=_optional_int(error.get("error_subcode")),
            is_transient=error.get("is_transient") if isinstance(error.get("is_transient"), bool) else None,
            user_title=_optional_str(error.get("error_user_title")),
            user_message=_optional_str(error.get("error_user_msg")),
            trace_id=_optional_str(error.get("fbtrace_id")),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return safe error metadata suitable for an MCP response."""
        result: dict[str, Any] = {"error": True, "message": str(self)}
        optional = {
            "http_status": self.status_code,
            "meta_error_type": self.error_type,
            "meta_error_code": self.code,
            "meta_error_subcode": self.error_subcode,
            "is_transient": self.is_transient,
            "user_title": self.user_title,
            "user_message": self.user_message,
            "trace_id": self.trace_id,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


class MetaAdsClient:
    """HTTP client for the subset of the Meta Marketing API used by Burnr8."""

    def __init__(
        self,
        access_token: str,
        *,
        app_secret: str | None = None,
        api_version: str = _DEFAULT_API_VERSION,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        if not access_token.strip():
            raise OSError("META_ACCESS_TOKEN is required for Meta Ads tools. Add it to ~/.burnr8/.env.")
        if not _VERSION_RE.fullmatch(api_version):
            raise ValueError("META_GRAPH_API_VERSION must look like 'v25.0'.")
        if timeout <= 0:
            raise ValueError("Meta API timeout must be positive.")
        self._access_token = access_token
        self._app_secret = app_secret or None
        self.api_version = api_version
        self.timeout = timeout
        self._session = session or requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one Graph API request and return its decoded object response."""
        normalized_method = method.upper()
        if normalized_method not in {"GET", "POST"}:
            raise ValueError("MetaAdsClient only supports GET and POST requests.")
        clean_path = path.strip("/")
        if not clean_path or "://" in clean_path:
            raise ValueError("Meta API path must be a non-empty relative Graph path.")

        encoded = {key: _encode_param(value) for key, value in (params or {}).items() if value is not None}
        if self._app_secret:
            encoded["appsecret_proof"] = hmac.new(
                self._app_secret.encode(), self._access_token.encode(), hashlib.sha256
            ).hexdigest()

        request_kwargs: dict[str, Any] = {
            "headers": {"Authorization": f"Bearer {self._access_token}"},
            "timeout": self.timeout,
            "allow_redirects": False,
        }
        if normalized_method == "GET":
            request_kwargs["params"] = encoded
        else:
            request_kwargs["data"] = encoded
            if files:
                request_kwargs["files"] = files

        response = self._session.request(
            normalized_method,
            f"{_GRAPH_API_ROOT}/{self.api_version}/{clean_path}",
            **request_kwargs,
        )
        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError:
            raise MetaAdsApiError(
                f"Meta Marketing API returned a non-JSON response (HTTP {response.status_code}).",
                status_code=response.status_code,
            ) from None
        except ValueError:
            raise MetaAdsApiError(
                f"Meta Marketing API returned a non-JSON response (HTTP {response.status_code}).",
                status_code=response.status_code,
            ) from None

        if not isinstance(payload, dict):
            raise MetaAdsApiError(
                f"Meta Marketing API returned an unexpected response (HTTP {response.status_code}).",
                status_code=response.status_code,
            )
        if "error" in payload or not 200 <= response.status_code < 300:
            safe_payload = _redact_error(
                payload, (self._access_token, self._app_secret or "", encoded.get("appsecret_proof", ""))
            )
            raise MetaAdsApiError.from_payload(safe_payload, response.status_code)
        return payload


def get_meta_client() -> MetaAdsClient:
    """Build a Meta client from credentials loaded into the environment."""
    token = os.environ.get("META_ACCESS_TOKEN", "")
    if not token:
        raise OSError(
            "META_ACCESS_TOKEN is not configured. Add a Meta user or system-user access token "
            "with ads_management permission to ~/.burnr8/.env, then restart the MCP server."
        )
    return MetaAdsClient(
        token,
        app_secret=os.environ.get("META_APP_SECRET"),
        api_version=os.environ.get("META_GRAPH_API_VERSION", _DEFAULT_API_VERSION),
    )


def _encode_param(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _redact_error(value: Any, secrets: tuple[str, ...]) -> Any:
    """Remove credentials from every provider error field before truncation."""
    if isinstance(value, str):
        for secret in sorted(set(secrets) - {""}, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {key: _redact_error(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_error(item, secrets) for item in value]
    return value


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
