from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def validate_id(value: str, name: str) -> str | None:
    """Return error message if value is not a numeric ID, else None."""
    if not _NUMERIC_RE.match(value):
        return f"{name} must be numeric, got: {value}"
    return None


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


def run_gaql(client: GoogleAdsClient, customer_id: str, query: str, limit: int = 0) -> list[dict]:
    """Execute a GAQL query via search_stream and return results as dicts.
    If limit > 0, appends LIMIT clause to GAQL rather than truncating client-side."""
    if limit and "LIMIT" not in query.upper():
        query = query.rstrip().rstrip(";") + f" LIMIT {limit}"
    ga_service = client.get_service("GoogleAdsService")
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            results.append(proto_to_dict(row))
    return results


def proto_to_dict(msg) -> dict:
    """Convert a protobuf message to a plain dict."""
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(type(msg).pb(msg), preserving_proto_field_name=True)
