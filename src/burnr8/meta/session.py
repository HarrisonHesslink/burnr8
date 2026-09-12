"""Request-local Meta ad account selection."""

from __future__ import annotations

import contextvars
import os

_active_meta_ad_account: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_meta_ad_account", default=None
)


def normalize_meta_ad_account_id(account_id: str) -> str:
    """Normalize an account ID to digits without Meta's optional ``act_`` prefix."""
    normalized = account_id.strip()
    if normalized.lower().startswith("act_"):
        normalized = normalized[4:]
    if not normalized or not normalized.isdigit():
        raise ValueError("Meta ad account ID must contain digits only, with an optional 'act_' prefix.")
    return normalized


def set_active_meta_ad_account(account_id: str) -> str:
    normalized = normalize_meta_ad_account_id(account_id)
    _active_meta_ad_account.set(normalized)
    return normalized


def get_active_meta_ad_account() -> str | None:
    return _active_meta_ad_account.get()


def require_meta_ad_account_id(account_id: str | None) -> str:
    """Resolve explicit, request-local, then environment-default ad account ID."""
    candidate = account_id or get_active_meta_ad_account() or os.environ.get("META_AD_ACCOUNT_ID")
    if not candidate:
        raise ValueError(
            "No Meta ad account selected. Pass account_id, call meta_set_active_ad_account, or set META_AD_ACCOUNT_ID."
        )
    return normalize_meta_ad_account_id(candidate)
