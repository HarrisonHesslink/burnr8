"""Session state — active account management."""

import threading

_active_account: str | None = None
_lock = threading.Lock()

__all__ = ["set_active_account", "get_active_account", "resolve_customer_id"]


def set_active_account(customer_id: str) -> None:
    """Set the active Google Ads customer ID for the session."""
    global _active_account
    with _lock:
        _active_account = customer_id.replace("-", "")


def get_active_account() -> str | None:
    """Get the active customer ID, or None if not set."""
    with _lock:
        return _active_account


def resolve_customer_id(customer_id: str | None) -> str | None:
    """Resolve customer_id: use the provided value, or fall back to active account."""
    if customer_id:
        return customer_id
    return get_active_account()
