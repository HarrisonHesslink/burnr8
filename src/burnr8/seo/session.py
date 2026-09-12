"""Request-local Search Console property selection and ownership checks."""

from __future__ import annotations

import contextvars
import os
import re
from urllib.parse import urlsplit, urlunsplit

_active_search_console_property: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_search_console_property", default=None
)
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I
)


def normalize_search_console_property(property_url: str) -> str:
    candidate = property_url.strip()
    if candidate.lower().startswith("sc-domain:"):
        domain = candidate.split(":", 1)[1].strip().lower().rstrip(".")
        if not _DOMAIN_RE.fullmatch(domain):
            raise ValueError("Search Console domain properties must look like 'sc-domain:example.com'.")
        return f"sc-domain:{domain}"

    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Search Console URL-prefix properties must be absolute HTTP(S) URLs.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Search Console properties cannot contain credentials, a query, or a fragment.")
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Search Console property contains an invalid port.") from None
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def set_active_search_console_property(property_url: str) -> str:
    normalized = normalize_search_console_property(property_url)
    _active_search_console_property.set(normalized)
    return normalized


def get_active_search_console_property() -> str | None:
    return _active_search_console_property.get()


def require_search_console_property(property_url: str | None) -> str:
    candidate = property_url or get_active_search_console_property() or os.environ.get("GOOGLE_SEARCH_CONSOLE_PROPERTY")
    if not candidate:
        raise ValueError(
            "No Search Console property selected. Pass property_url, call gsc_set_active_property, "
            "or set GOOGLE_SEARCH_CONSOLE_PROPERTY."
        )
    return normalize_search_console_property(candidate)


def validate_url_for_property(url: str, property_url: str) -> str:
    normalized_property = normalize_search_console_property(property_url)
    candidate = url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL must be an absolute public HTTP(S) URL without embedded credentials.")
    host = parsed.hostname.lower().rstrip(".")
    if normalized_property.startswith("sc-domain:"):
        domain = normalized_property.split(":", 1)[1]
        if host != domain and not host.endswith(f".{domain}"):
            raise ValueError(f"URL does not belong to Search Console property {normalized_property}.")
    else:
        prefix = urlsplit(normalized_property)
        prefix_port = prefix.port or (443 if prefix.scheme == "https" else 80)
        candidate_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        prefix_path = prefix.path
        candidate_path = parsed.path or "/"
        if (
            parsed.scheme.lower() != prefix.scheme
            or host != prefix.hostname
            or candidate_port != prefix_port
            or not candidate_path.startswith(prefix_path)
        ):
            raise ValueError(f"URL does not belong to Search Console property {normalized_property}.")
    return candidate
