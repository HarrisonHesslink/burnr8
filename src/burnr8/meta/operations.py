"""Shared validation and response helpers for Meta Ads management tools."""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from burnr8.meta.client import MetaAdsClient
from burnr8.meta.session import normalize_meta_ad_account_id

META_CAMPAIGN_EFFECTIVE_STATUSES = frozenset({"ACTIVE", "ARCHIVED", "DELETED", "IN_PROCESS", "PAUSED", "WITH_ISSUES"})
META_AD_SET_EFFECTIVE_STATUSES = META_CAMPAIGN_EFFECTIVE_STATUSES | {"CAMPAIGN_PAUSED"}
META_AD_EFFECTIVE_STATUSES = META_AD_SET_EFFECTIVE_STATUSES | {
    "ADSET_PAUSED",
    "DISAPPROVED",
    "PENDING_BILLING_INFO",
    "PENDING_REVIEW",
    "PREAPPROVED",
}
META_EFFECTIVE_STATUSES = META_AD_EFFECTIVE_STATUSES
META_MUTABLE_STATUSES = frozenset({"ACTIVE", "PAUSED"})
META_INSIGHT_LEVELS = frozenset({"account", "campaign", "adset", "ad"})
META_INSIGHT_SCOPES = frozenset({"account", "campaign", "adset", "ad"})
META_DATE_PRESETS = frozenset(
    {
        "data_maximum",
        "last_3d",
        "last_7d",
        "last_14d",
        "last_28d",
        "last_30d",
        "last_90d",
        "last_month",
        "last_quarter",
        "last_week_mon_sun",
        "last_week_sun_sat",
        "last_year",
        "maximum",
        "this_month",
        "this_quarter",
        "this_week_mon_today",
        "this_week_sun_today",
        "this_year",
        "today",
        "yesterday",
    }
)
META_INSIGHT_BREAKDOWNS = frozenset(
    {
        "age",
        "country",
        "device_platform",
        "dma",
        "gender",
        "impression_device",
        "platform_position",
        "publisher_platform",
        "region",
    }
)
META_AD_PREVIEW_FORMATS = frozenset(
    {
        "DESKTOP_FEED_STANDARD",
        "FACEBOOK_REELS_MOBILE",
        "FACEBOOK_STORY_MOBILE",
        "INSTAGRAM_REELS",
        "INSTAGRAM_STANDARD",
        "INSTAGRAM_STORY",
        "MOBILE_FEED_STANDARD",
    }
)

CAMPAIGN_FIELDS = ",".join(
    (
        "id",
        "account_id",
        "name",
        "objective",
        "buying_type",
        "status",
        "effective_status",
        "daily_budget",
        "lifetime_budget",
        "budget_remaining",
        "spend_cap",
        "start_time",
        "stop_time",
        "created_time",
        "updated_time",
        "issues_info",
    )
)
AD_SET_FIELDS = ",".join(
    (
        "id",
        "account_id",
        "campaign_id",
        "name",
        "status",
        "effective_status",
        "daily_budget",
        "lifetime_budget",
        "budget_remaining",
        "bid_amount",
        "bid_strategy",
        "billing_event",
        "optimization_goal",
        "destination_type",
        "start_time",
        "end_time",
        "targeting",
        "created_time",
        "updated_time",
        "issues_info",
    )
)
AD_FIELDS = ",".join(
    (
        "id",
        "account_id",
        "campaign_id",
        "adset_id",
        "name",
        "status",
        "effective_status",
        "created_time",
        "updated_time",
        "issues_info",
        "creative{id,name,thumbnail_url,image_url,object_story_spec}",
    )
)
INSIGHT_FIELDS = ",".join(
    (
        "account_currency",
        "account_id",
        "account_name",
        "campaign_id",
        "campaign_name",
        "adset_id",
        "adset_name",
        "ad_id",
        "ad_name",
        "date_start",
        "date_stop",
        "spend",
        "impressions",
        "reach",
        "frequency",
        "clicks",
        "unique_clicks",
        "inline_link_clicks",
        "outbound_clicks",
        "ctr",
        "cpc",
        "cpm",
        "cpp",
        "actions",
        "action_values",
        "cost_per_action_type",
        "cost_per_unique_action_type",
    )
)

_RESOURCE_FIELDS = {
    "campaign": CAMPAIGN_FIELDS,
    "adset": AD_SET_FIELDS,
    "ad": AD_FIELDS,
}
_RESOURCE_EFFECTIVE_STATUSES = {
    "campaign": META_CAMPAIGN_EFFECTIVE_STATUSES,
    "adset": META_AD_SET_EFFECTIVE_STATUSES,
    "ad": META_AD_EFFECTIVE_STATUSES,
}
_SCOPE_ALLOWED_LEVELS = {
    "account": META_INSIGHT_LEVELS,
    "campaign": frozenset({"campaign", "adset", "ad"}),
    "adset": frozenset({"adset", "ad"}),
    "ad": frozenset({"ad"}),
}
_ACTION_STAT_FIELDS = ("actions", "action_values", "cost_per_action_type", "cost_per_unique_action_type")
_MAX_PAGES = 25
_PAGE_SIZE = 100


def validate_meta_resource_id(value: str, field: str) -> str:
    """Return a normalized numeric Meta object ID or raise a clear error."""
    if not isinstance(value, str) or not value.strip().isdigit():
        raise ValueError(f"{field} must contain digits only.")
    return value.strip()


def validate_effective_statuses(statuses: list[str] | None, resource_type: str | None = None) -> list[str] | None:
    """Normalize optional effective-status filters."""
    if statuses is None:
        return None
    if not isinstance(statuses, list) or not statuses:
        raise ValueError("effective_statuses must contain at least one status when provided.")
    if resource_type is not None and resource_type not in _RESOURCE_EFFECTIVE_STATUSES:
        raise ValueError("resource_type must be campaign, adset, or ad.")
    allowed_statuses = META_EFFECTIVE_STATUSES if resource_type is None else _RESOURCE_EFFECTIVE_STATUSES[resource_type]
    if len(statuses) > len(allowed_statuses):
        raise ValueError("effective_statuses contains too many values.")
    normalized: list[str] = []
    for status in statuses:
        if not isinstance(status, str) or status.upper() not in allowed_statuses:
            allowed = ", ".join(sorted(allowed_statuses))
            raise ValueError(f"Unsupported effective status '{status}'. Choose from: {allowed}.")
        upper = status.upper()
        if upper not in normalized:
            normalized.append(upper)
    return normalized


def validate_mutable_status(status: str) -> str:
    """Allow only reversible delivery states; deletion is intentionally excluded."""
    if not isinstance(status, str) or status.upper() not in META_MUTABLE_STATUSES:
        raise ValueError("status must be ACTIVE or PAUSED. Deletion and archiving are not exposed by Burnr8.")
    return status.upper()


def validate_preview_format(ad_format: str) -> str:
    if not isinstance(ad_format, str) or ad_format.upper() not in META_AD_PREVIEW_FORMATS:
        allowed = ", ".join(sorted(META_AD_PREVIEW_FORMATS))
        raise ValueError(f"Unsupported ad_format '{ad_format}'. Choose from: {allowed}.")
    return ad_format.upper()


def validate_cursor(after: str | None) -> str | None:
    if after is None:
        return None
    if not isinstance(after, str) or not after or len(after) > 2048 or any(ord(char) < 33 for char in after):
        raise ValueError("after must be a non-empty Meta paging cursor without whitespace or control characters.")
    return after


def collect_edge(
    client: MetaAdsClient,
    path: str,
    *,
    params: Mapping[str, Any],
    label: str,
    max_results: int,
    after: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    """Collect a bounded Graph edge using cursors without returning token-bearing URLs."""
    if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 2000:
        raise ValueError("max_results must be between 1 and 2000.")
    cursor = validate_cursor(after)
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    pages = 0
    has_more = False
    next_cursor: str | None = None

    while len(rows) < max_results and pages < _MAX_PAGES:
        request_params = dict(params)
        request_params["limit"] = min(_PAGE_SIZE, max_results - len(rows))
        if cursor:
            request_params["after"] = cursor
        payload = client.request("GET", path, params=request_params)
        pages += 1
        page_rows = _extract_data(payload, label)
        rows.extend(page_rows[: max_results - len(rows)])
        if summary is None and isinstance(payload.get("summary"), Mapping):
            summary = dict(payload["summary"])

        paging = payload.get("paging")
        if not isinstance(paging, Mapping):
            has_more = False
            next_cursor = None
            break
        cursors = paging.get("cursors")
        raw_after = cursors.get("after") if isinstance(cursors, Mapping) else None
        candidate = validate_cursor(str(raw_after)) if raw_after is not None else None
        has_more = bool(paging.get("next")) and bool(candidate)
        next_cursor = candidate if has_more else None
        if not has_more or next_cursor == cursor:
            break
        cursor = next_cursor

    if pages >= _MAX_PAGES and next_cursor:
        has_more = True
    return rows, {"pages_fetched": pages, "has_more": has_more, "next_after": next_cursor}, summary


def get_owned_resource(
    client: MetaAdsClient,
    resource_type: str,
    resource_id: str,
    account_id: str,
) -> dict[str, Any]:
    """Fetch a Meta object and prove it belongs to the selected ad account."""
    if resource_type not in _RESOURCE_FIELDS:
        raise ValueError("resource_type must be campaign, adset, or ad.")
    normalized_id = validate_meta_resource_id(resource_id, f"{resource_type}_id")
    payload = client.request("GET", normalized_id, params={"fields": _RESOURCE_FIELDS[resource_type]})
    returned_id = payload.get("id")
    if returned_id is None or str(returned_id) != normalized_id:
        raise ValueError(f"Meta returned an unexpected {resource_type} response.")
    raw_account_id = payload.get("account_id")
    if raw_account_id is None:
        raise ValueError(f"Meta did not return account ownership for {resource_type} {normalized_id}.")
    resource_account_id = normalize_meta_ad_account_id(str(raw_account_id))
    if resource_account_id != normalize_meta_ad_account_id(account_id):
        raise ValueError(
            f"{resource_type.capitalize()} {normalized_id} belongs to Meta ad account {resource_account_id}, "
            f"not the selected account {normalize_meta_ad_account_id(account_id)}."
        )
    return payload


def validate_insight_scope(scope: str, scope_id: str | None, level: str) -> tuple[str, str | None, str]:
    normalized_scope = scope.lower() if isinstance(scope, str) else ""
    normalized_level = level.lower() if isinstance(level, str) else ""
    if normalized_scope not in META_INSIGHT_SCOPES:
        raise ValueError("scope must be account, campaign, adset, or ad.")
    if normalized_level not in META_INSIGHT_LEVELS:
        raise ValueError("level must be account, campaign, adset, or ad.")
    if normalized_level not in _SCOPE_ALLOWED_LEVELS[normalized_scope]:
        allowed = ", ".join(sorted(_SCOPE_ALLOWED_LEVELS[normalized_scope]))
        raise ValueError(f"scope '{normalized_scope}' supports these insight levels: {allowed}.")
    if normalized_scope == "account":
        if scope_id is not None:
            raise ValueError("scope_id must be omitted when scope='account'.")
        return normalized_scope, None, normalized_level
    if scope_id is None:
        raise ValueError(f"scope_id is required when scope='{normalized_scope}'.")
    return normalized_scope, validate_meta_resource_id(scope_id, "scope_id"), normalized_level


def validate_insight_breakdowns(breakdowns: list[str] | None) -> list[str] | None:
    if breakdowns is None:
        return None
    if not isinstance(breakdowns, list) or not breakdowns:
        raise ValueError("breakdowns must contain at least one value when provided.")
    if len(breakdowns) > 3:
        raise ValueError("breakdowns may contain at most three dimensions.")
    normalized: list[str] = []
    for breakdown in breakdowns:
        value = breakdown.lower() if isinstance(breakdown, str) else ""
        if value not in META_INSIGHT_BREAKDOWNS:
            allowed = ", ".join(sorted(META_INSIGHT_BREAKDOWNS))
            raise ValueError(f"Unsupported breakdown '{breakdown}'. Choose from: {allowed}.")
        if value not in normalized:
            normalized.append(value)
    return normalized


def normalize_insight_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Retain Meta's raw fields and add keyed action maps for easier MCP analysis."""
    result = dict(row)
    for field in _ACTION_STAT_FIELDS:
        if field in row:
            result[f"{field}_by_type"] = _action_stats_by_type(row.get(field))
    return result


def dollars_to_minor_units(amount: float) -> int:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(float(amount)):
        raise ValueError("daily_budget_dollars must be a finite number.")
    return int((Decimal(str(amount)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def minor_units_to_dollars(value: Any, field: str) -> float:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Meta returned an invalid {field} value.") from None
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError(f"Meta returned an invalid {field} value.")
    return float(amount / Decimal("100"))


def _extract_data(payload: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError(f"Meta returned an unexpected {label} response.")
    if any(not isinstance(item, Mapping) for item in data):
        raise ValueError(f"Meta returned malformed rows for {label}.")
    return [dict(item) for item in data]


def _action_stats_by_type(value: Any) -> dict[str, int | float | str]:
    if not isinstance(value, list):
        return {}
    result: dict[str, int | float | str] = {}
    for item in value:
        if not isinstance(item, Mapping) or not isinstance(item.get("action_type"), str):
            continue
        raw_value = item.get("value")
        result[str(item["action_type"])] = _coerce_numeric_value(raw_value)
    return result


def _coerce_numeric_value(value: Any) -> int | float | str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value) if value is not None else ""
    if not number.is_finite():
        return str(value)
    if number == number.to_integral_value():
        return int(number)
    return float(number)
