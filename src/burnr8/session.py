"""Session state — active account management."""

import contextvars
import os

_active_account: contextvars.ContextVar[str | None] = contextvars.ContextVar("active_account", default=None)

_default_max_daily_budget = float(os.environ.get("BURNR8_MAX_DAILY_BUDGET_DOLLARS", "10000"))
_default_max_cpc_bid = float(os.environ.get("BURNR8_MAX_CPC_BID_DOLLARS", "100"))
_default_max_bid_modifier = float(os.environ.get("BURNR8_MAX_BID_MODIFIER", "5.0"))
_default_max_target_cpa = float(os.environ.get("BURNR8_MAX_TARGET_CPA_DOLLARS", "500"))
_default_min_target_roas = float(os.environ.get("BURNR8_MIN_TARGET_ROAS", "0.5"))

_max_daily_budget = contextvars.ContextVar("max_daily_budget", default=_default_max_daily_budget)
_max_cpc_bid = contextvars.ContextVar("max_cpc_bid", default=_default_max_cpc_bid)
_max_bid_modifier = contextvars.ContextVar("max_bid_modifier", default=_default_max_bid_modifier)
_max_target_cpa = contextvars.ContextVar("max_target_cpa", default=_default_max_target_cpa)
_min_target_roas = contextvars.ContextVar("min_target_roas", default=_default_min_target_roas)

__all__ = [
    "set_active_account",
    "get_active_account",
    "resolve_customer_id",
    "set_financial_limits",
    "get_max_daily_budget",
    "get_max_cpc_bid",
    "get_max_bid_modifier",
    "get_max_target_cpa",
    "get_min_target_roas",
]


def set_active_account(customer_id: str) -> None:
    """Set the active Google Ads customer ID for the session."""
    _active_account.set(customer_id.replace("-", ""))


def get_active_account() -> str | None:
    """Get the active customer ID, or None if not set."""
    return _active_account.get()


def resolve_customer_id(customer_id: str | None) -> str | None:
    """Resolve customer_id: use the provided value, or fall back to active account."""
    if customer_id:  # None and "" both mean "not provided"
        return customer_id
    return get_active_account()


def set_financial_limits(
    max_daily_budget: float | None = None,
    max_cpc_bid: float | None = None,
    max_bid_modifier: float | None = None,
    max_target_cpa: float | None = None,
    min_target_roas: float | None = None,
) -> None:
    """Dynamically set financial safety limits for the current process/task via proxy."""
    if max_daily_budget is not None:
        _max_daily_budget.set(float(max_daily_budget))
    if max_cpc_bid is not None:
        _max_cpc_bid.set(float(max_cpc_bid))
    if max_bid_modifier is not None:
        _max_bid_modifier.set(float(max_bid_modifier))
    if max_target_cpa is not None:
        _max_target_cpa.set(float(max_target_cpa))
    if min_target_roas is not None:
        _min_target_roas.set(float(min_target_roas))


def get_max_daily_budget() -> float:
    return _max_daily_budget.get()

def get_max_cpc_bid() -> float:
    return _max_cpc_bid.get()

def get_max_bid_modifier() -> float:
    return _max_bid_modifier.get()

def get_max_target_cpa() -> float:
    return _max_target_cpa.get()

def get_min_target_roas() -> float:
    return _min_target_roas.get()
