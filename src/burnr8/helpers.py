from __future__ import annotations

import math
import re
from collections.abc import Iterator
from typing import TYPE_CHECKING

from pydantic import validate_call

from burnr8.session import (
    get_max_bid_modifier,
    get_max_cpc_bid,
    get_max_daily_budget,
    get_max_target_cpa,
    get_min_target_roas,
)

if TYPE_CHECKING:
    import proto
    from google.ads.googleads.client import GoogleAdsClient

VALID_STATUSES = {"ENABLED", "PAUSED", "REMOVED"}
VALID_DATE_RANGES = {
    "TODAY",
    "YESTERDAY",
    "LAST_7_DAYS",
    "LAST_14_DAYS",
    "LAST_30_DAYS",
    "THIS_WEEK_MON_TODAY",
    "THIS_WEEK_SUN_TODAY",
    "LAST_WEEK_MON_SUN",
    "LAST_WEEK_SUN_SAT",
    "THIS_MONTH",
    "LAST_MONTH",
    "LAST_BUSINESS_WEEK",
}
_NUMERIC_RE = re.compile(r"^\d+$")


__all__ = [
    "run_gaql", "stream_gaql", "proto_to_dict", "micros_to_dollars", "dollars_to_micros",
    "validate_id", "validate_status", "validate_date_range", "validate_budget_amount",
    "validate_daily_budget", "validate_cpc_bid", "validate_bid_modifier", "validate_target_cpa", "validate_target_roas",
    "require_customer_id", "escape_gaql_string", "validate_gaql_query",
    "validate_recent_errors_limit",
]


def validate_id(value: str, name: str) -> str | None:
    """Return error message if value is not a numeric ID, else None."""
    if not isinstance(value, str) or not _NUMERIC_RE.match(value):
        return f"{name} must be a numeric string, got: {value}"
    return None


def validate_recent_errors_limit(value: int) -> str | None:
    """Return error message if value is not a positive integer <= 5, else None."""
    if not isinstance(value, int) or value <= 0:
        return f"limit must be a positive integer, got: {value}"
    if value > 5:
        return f"limit must be 5 or less to prevent excessive memory usage, got: {value}"
    return None


def escape_gaql_string(value: str) -> str:
    """
    Escape a string for safe inclusion inside single quotes in a GAQL query.
    Prevents GAQL injection by escaping existing backslashes and single quotes.
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


def validate_gaql_query(query: str, customer_id: str) -> None:
    """Validate a GAQL query for safety: strict SELECT, DML blocklist, and id routing."""
    upper_query = query.lstrip().upper()
    if not upper_query.startswith("SELECT"):
        raise ValueError("GAQL queries must be read-only and begin with SELECT.")

    forbidden = {"INSERT", "UPDATE", "DELETE", "SET", "REMOVE", "DROP", "ALTER", "CREATE"}
    if match := re.search(r"\b(" + "|".join(forbidden) + r")\b", upper_query):
        raise ValueError(f"GAQL queries must be read-only. Forbidden keyword found: {match.group(1)}")

    # Cross-tenant check: ensure customer.id or customer_client.id filters match the active session.
    # We match: field, optional whitespace/multispace, operator (including !=), RHS (digits, quotes, spaces)
    pattern = r"(?i)(customer\.id|customer_client\.id)\s*(!=|<>|=|>=|<=|>|<|IN|NOT\s+IN)\s*[^A-Za-z0-9_]*([\d\s,'\"]+)"
    for match in re.finditer(pattern, query):
        rhs_digits = re.findall(r"\d+", match.group(3))
        for d in rhs_digits:
            if d != customer_id:
                raise ValueError(
                    f"GAQL queries cannot explicitly query a customer ID ({d}) that does not match the active session ({customer_id})."
                )


def require_customer_id(customer_id: str | None) -> tuple[str, dict | None]:
    """Resolve and validate customer_id in one step.

    Returns ``(customer_id, None)`` on success, or ``("", error_dict)`` on
    failure.  Combines :func:`~burnr8.session.resolve_customer_id` and
    :func:`validate_id` so callers don't need to repeat the same 5-line
    guard block.
    """
    from burnr8.session import resolve_customer_id

    customer_id = resolve_customer_id(customer_id)
    if customer_id is None:
        return "", {
            "error": True,
            "message": "No customer_id provided and no active account set. Call set_active_account first.",
        }
    if err := validate_id(customer_id, "customer_id"):
        return "", {"error": True, "message": err}
    return customer_id, None


@validate_call
def validate_status(value: str) -> str | None:
    if value.upper() not in VALID_STATUSES:
        return f"Invalid status '{value}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
    return None


@validate_call
def validate_date_range(value: str) -> str | None:
    if value.upper() not in VALID_DATE_RANGES:
        return f"Invalid date_range '{value}'. Must be one of: {', '.join(sorted(VALID_DATE_RANGES))}"
    return None


def validate_budget_amount(amount: float) -> str | None:
    """Return error message if amount is not a positive number, else None."""
    if isinstance(amount, bool):
        return f"Amount must be a number, got: {amount}"
    if not isinstance(amount, (int, float)):
        return f"Amount must be a number, got: {amount}"
    if amount <= 0:
        return f"Amount must be greater than zero, got: {amount}"
    return None


@validate_call
def validate_daily_budget(amount: float | int) -> str | None:
    """Validates a daily budget amount against the configurable hard-cap.

    Returns an error string if invalid, else None.
    """
    if not math.isfinite(amount):
        return f"Daily budget must be a finite number, got: {amount}"
    if amount == 0:
        return None  # $0 budgets are valid (pause spend without pausing campaign)
    if amount <= 0:
        return f"Daily budget must be greater than zero, got: {amount}"
    limit = get_max_daily_budget()
    if amount > limit:
        return (
            f"Daily budget ${amount:,.2f} exceeds the safety cap of "
            f"${limit:,.2f}. Raise the limit via proxy configuration if this is intentional."
        )
    return None


@validate_call
def validate_cpc_bid(amount: float | int) -> str | None:
    """Validates a CPC bid amount against the configurable hard-cap.

    Returns an error string if invalid, else None.
    """
    if not math.isfinite(amount):
        return f"CPC bid must be a finite number, got: {amount}"
    if amount < 0:
        return f"CPC bid cannot be negative, got: {amount}"
    limit = get_max_cpc_bid()
    if amount > limit:
        return (
            f"CPC bid ${amount:,.2f} exceeds the safety cap of "
            f"${limit:,.2f}. Raise the limit via proxy configuration if this is intentional."
        )
    return None


@validate_call
def validate_bid_modifier(amount: float | int) -> str | None:
    """Validates a bid modifier against the configurable hard-cap."""
    if not math.isfinite(amount):
        return f"Bid modifier must be a finite number, got: {amount}"
    if amount < 0.1 and amount != 0.0:
        return f"Bid modifier cannot be less than 0.1 (except 0.0 to exclude), got: {amount}"
    limit = get_max_bid_modifier()
    if amount > limit:
        return (
            f"Bid modifier {amount} exceeds the safety cap of "
            f"{limit}. Raise the limit via proxy configuration if this is intentional."
        )
    return None


@validate_call
def validate_target_cpa(amount: float | int) -> str | None:
    """Validates a Target CPA against the configurable hard-cap."""
    if not math.isfinite(amount):
        return f"Target CPA must be a finite number, got: {amount}"
    if amount <= 0:
        return f"Target CPA must be greater than zero, got: {amount}"
    limit = get_max_target_cpa()
    if amount > limit:
        return (
            f"Target CPA ${amount:,.2f} exceeds the safety cap of "
            f"${limit:,.2f}. Raise the limit via proxy configuration if this is intentional."
        )
    return None


@validate_call
def validate_target_roas(amount: float | int) -> str | None:
    """Validates a Target ROAS against the configurable safety floor."""
    if not math.isfinite(amount):
        return f"Target ROAS must be a finite number, got: {amount}"
    limit = get_min_target_roas()
    if amount < limit:
        return (
            f"Target ROAS {amount} is below the safety floor of "
            f"{limit}. Lower the limit via proxy configuration if this is intentional."
        )
    return None


def micros_to_dollars(micros: int) -> float:
    return micros / 1_000_000


def dollars_to_micros(dollars: float) -> int:
    return round(dollars * 1_000_000)


def stream_gaql(client: GoogleAdsClient, customer_id: str, query: str, limit: int = 0) -> Iterator[dict]:
    """Yield dicts one-at-a-time from a GAQL search_stream.

    Use this instead of ``run_gaql`` when you want to process rows without
    materializing the entire result set in memory (e.g. large search-term or
    keyword-performance queries).

    If *limit* > 0, appends a LIMIT clause to the GAQL string.
    """
    validate_gaql_query(query, customer_id)
    if limit and not re.search(r"(?i)\bLIMIT\s+\d+(\s+OFFSET\s+\d+)?\s*;?$", query):
        query = query.rstrip().rstrip(";") + f" LIMIT {limit}"
    ga_service = client.get_service("GoogleAdsService")
    stream = ga_service.search_stream(customer_id=customer_id, query=query, timeout=120)
    for batch in stream:
        for row in batch.results:
            yield proto_to_dict(row)


def run_gaql(client: GoogleAdsClient, customer_id: str, query: str, limit: int = 0) -> list[dict]:
    """Execute a GAQL query via search_stream and return results as dicts.

    This is the eager wrapper around :func:`stream_gaql` — it materializes all
    rows into a list so existing callers keep working unchanged.

    If *limit* > 0, appends LIMIT clause to GAQL rather than truncating
    client-side.
    """
    return list(stream_gaql(client, customer_id, query, limit))


def proto_to_dict(msg: proto.Message) -> dict:
    """Convert a protobuf message to a plain dict."""
    from google.protobuf.json_format import MessageToDict

    return dict(MessageToDict(type(msg).pb(msg), preserving_proto_field_name=True))
