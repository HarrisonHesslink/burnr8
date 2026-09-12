"""Reddit account ownership, currency, and mutation result checks."""

from __future__ import annotations

import os
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

import requests

from burnr8.helpers import validate_daily_budget
from burnr8.reddit.client import RedditAdsApiError, RedditAdsClient, validate_page_url

ResourceType = Literal["campaign", "ad_group", "ad"]
RESOURCE_PATHS = {"campaign": "campaigns", "ad_group": "ad_groups", "ad": "ads"}


def resource_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Reddit resource IDs must contain only letters, numbers, underscores or hyphens.")
    return value


def account_id(value: str | None) -> str:
    value = value if value is not None else os.environ.get("REDDIT_AD_ACCOUNT_ID", "")
    if not re.fullmatch(r"(?:t2|a2)_[A-Za-z0-9]+", value):
        raise ValueError("Supply a Reddit account_id such as a2_abc123, or set REDDIT_AD_ACCOUNT_ID.")
    return value


def object_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RedditAdsApiError("Reddit returned an invalid resource response.")
    return data


def get_account(client: RedditAdsClient, selected: str) -> dict[str, Any]:
    data = object_data(client.request("GET", f"ad_accounts/{selected}"))
    if data.get("id") != selected:
        raise ValueError("Reddit returned an account different from the selected account.")
    return data


def require_usd(client: RedditAdsClient, selected: str) -> dict[str, Any]:
    data = get_account(client, selected)
    if data.get("currency") != "USD":
        raise ValueError("Reddit budget tools accept USD amounts and require a USD ad account.")
    return data


def owned_resource(client: RedditAdsClient, kind: ResourceType, ident: str, selected: str) -> dict[str, Any]:
    if kind not in RESOURCE_PATHS:
        raise ValueError("resource_type must be campaign, ad_group or ad.")
    data = object_data(client.request("GET", f"{RESOURCE_PATHS[kind]}/{resource_id(ident)}"))
    if data.get("id") != ident or data.get("ad_account_id") != selected:
        raise ValueError("The Reddit resource does not belong to the selected account.")
    return data


def money_micros(value: float, *, daily: bool = False) -> int:
    try:
        amount = Decimal(str(value))
        limit = Decimal(os.environ.get("BURNR8_REDDIT_MAX_SPEND_CAP_DOLLARS", "1000")) if not daily else Decimal(0)
    except InvalidOperation:
        raise ValueError("Reddit budget and spend-cap settings must be finite positive numbers.") from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Reddit budget amounts must be finite and greater than zero.")
    if daily:
        if error := validate_daily_budget(float(amount)):
            raise ValueError(error)
    elif not limit.is_finite() or limit <= 0 or amount > limit:
        raise ValueError("Campaign spend cap exceeds BURNR8_REDDIT_MAX_SPEND_CAP_DOLLARS (default $1000).")
    micros = int((amount * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if micros < 10_000:
        raise ValueError("Reddit budget amounts must be at least $0.01.")
    return micros


def pagination(payload: dict[str, Any], path: str) -> dict[str, Any]:
    raw = payload.get("pagination") or {}
    if not isinstance(raw, dict):
        raise RedditAdsApiError("Reddit returned invalid pagination.")
    next_url = raw.get("next_url")
    if next_url is not None:
        if not isinstance(next_url, str):
            raise RedditAdsApiError("Reddit returned an invalid next-page URL.")
        validate_page_url(next_url, path)
    return {"next_url": next_url, "has_more": bool(next_url)}


def requested_fields_match(saved: Any, requested: Any, key: str = "") -> bool:
    """Ignore provider-added defaults, while checking every requested field."""
    if isinstance(requested, bool):
        return isinstance(saved, bool) and saved is requested
    if isinstance(requested, dict):
        return isinstance(saved, dict) and all(
            name in saved and requested_fields_match(saved[name], value, name) for name, value in requested.items()
        )
    if key in {"start_time", "end_time", "preview_expiry"} and isinstance(saved, str) and isinstance(requested, str):
        try:
            return datetime.fromisoformat(saved.replace("Z", "+00:00")) == datetime.fromisoformat(
                requested.replace("Z", "+00:00")
            )
        except ValueError:
            return False
    if key in {"communities", "excluded_communities", "geolocations", "locations"} and isinstance(requested, list):
        if not isinstance(saved, list) or any(not isinstance(value, str) for value in [*saved, *requested]):
            return False
        return {value.lower() for value in saved} == {value.lower() for value in requested}
    return bool(saved == requested)


def write_and_verify(
    client: RedditAdsClient,
    *,
    method: str,
    path: str,
    kind: ResourceType,
    selected: str,
    changes: dict[str, Any],
    ident: str | None = None,
) -> dict[str, Any]:
    """Never turn a write/read-back failure into an invitation to retry a write."""
    try:
        response = client.request(method, path, body={"data": changes})
    except (requests.RequestException, RedditAdsApiError) as ex:
        rejected = isinstance(ex, RedditAdsApiError) and ex.status_code in {400, 401, 403, 404, 429}
        return {
            "error": True,
            "mutation_outcome": "rejected" if rejected else "unknown",
            "resource_id": ident,
            "message": "Reddit did not confirm the write. Read the resource or campaign inventory before repeating it.",
        }
    data = response.get("data")
    data = data if isinstance(data, dict) else {}
    saved_id = ident or data.get("id")
    result: dict[str, Any] = {
        "created" if method == "POST" else "updated": True,
        "verified": False,
        "resource_id": saved_id,
        "account_id": selected,
        "requested_changes": changes,
    }
    if not isinstance(saved_id, str) or not saved_id:
        return {
            **result,
            "warning": True,
            "message": "Write acknowledged without a resource ID. Inspect inventory before retrying.",
        }
    try:
        saved = owned_resource(client, kind, saved_id, selected)
    except (requests.RequestException, RedditAdsApiError, ValueError):
        return {
            **result,
            "warning": True,
            "message": "Write acknowledged; read-back failed. Inspect this resource before retrying.",
        }
    matches = requested_fields_match(saved, changes)
    result.update(verified=matches, resource=saved)
    if not matches:
        result.update(
            warning=True, message="Write acknowledged; saved fields differ from the request. Inspect before proceeding."
        )
    return result
