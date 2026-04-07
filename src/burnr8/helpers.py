from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING

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

__all__ = ["run_gaql", "stream_gaql", "proto_to_dict", "micros_to_dollars", "dollars_to_micros", "validate_id", "validate_status", "validate_date_range", "require_customer_id"]


def validate_id(value: str, name: str) -> str | None:
    """Return error message if value is not a numeric ID, else None."""
    if not _NUMERIC_RE.match(value):
        return f"{name} must be numeric, got: {value}"
    return None


def require_customer_id(customer_id: str | None) -> tuple[str, dict | None]:
    """Resolve and validate customer_id in one step.

    Returns ``(customer_id, None)`` on success, or ``("", error_dict)`` on
    failure.  Combines :func:`~burnr8.session.resolve_customer_id` and
    :func:`validate_id` so callers don't need to repeat the same 5-line
    guard block.
    """
    from burnr8.session import resolve_customer_id

    customer_id = resolve_customer_id(customer_id)
    if not customer_id:
        return "", {
            "error": True,
            "message": "No customer_id provided and no active account set. Call set_active_account first.",
        }
    if err := validate_id(customer_id, "customer_id"):
        return "", {"error": True, "message": err}
    return customer_id, None


def validate_status(value: str) -> str | None:
    if value.upper() not in VALID_STATUSES:
        return f"Invalid status '{value}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
    return None


def validate_date_range(value: str) -> str | None:
    if value.upper() not in VALID_DATE_RANGES:
        return f"Invalid date_range '{value}'. Must be one of: {', '.join(sorted(VALID_DATE_RANGES))}"
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
    if limit and "LIMIT" not in query.upper():
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

    return MessageToDict(type(msg).pb(msg), preserving_proto_field_name=True)
