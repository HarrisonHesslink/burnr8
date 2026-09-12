"""Validation and account/profile checks for Reddit ad creation."""

from __future__ import annotations

import ipaddress
import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from urllib.parse import urlsplit

import requests

from burnr8.helpers import validate_cpc_bid
from burnr8.reddit.client import RedditAdsApiError, RedditAdsClient
from burnr8.reddit.helpers import object_data, pagination, resource_id


def text_field(value: str, label: str, maximum: int = 200) -> str:
    if not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must contain 1-{maximum} characters on one line.")
    return value.strip()


def public_url(value: str) -> str:
    """Validate a hosted URL; BurnR8 never downloads it or attaches OAuth to it."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        invalid = (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.fragment
            or len(value) > 5000
            or any(c.isspace() or ord(c) < 32 for c in value)
            or "\\" in value
        )
        try:
            invalid = invalid or not ipaddress.ip_address(host).is_global
        except ValueError:
            invalid = invalid or (
                "." not in host.rstrip(".")
                or host.lower().rstrip(".") == "localhost"
                or re.fullmatch(r"[0-9.]+", host) is not None
                or host.lower().rstrip(".").endswith((".localhost", ".local", ".internal"))
                or re.fullmatch(r"[A-Za-z0-9.-]+", host) is None
            )
        if invalid:
            raise ValueError
    except ValueError:
        raise ValueError(
            "Use a public HTTPS URL without embedded credentials, fragments or a nonstandard port."
        ) from None
    return value


def utc_time(value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("Schedule times must use UTC YYYY-MM-DDTHH:MM:SSZ.")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def targeting_values(values: list[str], label: str, pattern: str, maximum: int) -> list[str]:
    if not values or len(values) > maximum or any(not re.fullmatch(pattern, value) for value in values):
        raise ValueError(f"{label} must contain 1-{maximum} valid targeting values.")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicate values.")
    return values


def bid_micros(value: float, bid_type: str) -> int:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < Decimal("0.01"):
        raise ValueError("Bid must be finite and at least $0.01.")
    if bid_type == "CPM":
        if not Decimal("3.50") <= amount <= 100:
            raise ValueError("Reddit CPM bids must be between $3.50 and $100.")
    elif error := validate_cpc_bid(value):
        raise ValueError(error)
    return int((amount * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def list_data(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("data")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RedditAdsApiError("Reddit returned an invalid list response.")
    return rows


def linked_resource(
    client: RedditAdsClient, selected: str, collection: Literal["profiles", "pixels"], ident: str
) -> dict[str, Any]:
    """Prove the resource is linked to this account, not merely OAuth-accessible."""
    resource_id(ident)
    path = f"ad_accounts/{selected}/{collection}"
    next_url = None
    for _ in range(10):
        payload = client.request("GET", path, params={"page.size": 100}, next_url=next_url)
        for row in list_data(payload):
            if row.get("id") == ident:
                return row
        next_url = pagination(payload, path)["next_url"]
        if not next_url:
            raise ValueError(f"The requested resource is not linked to this ad account's {collection}.")
    raise ValueError(f"Could not verify the account's {collection} within 10 pages. No write was sent.")


def profile_asset(client: RedditAdsClient, profile_id: str, asset_id: str) -> dict[str, Any]:
    rows = list_data(
        client.request(
            "GET",
            f"profiles/{resource_id(profile_id)}/creative_assets",
            params={"creative_asset_ids": [resource_id(asset_id)], "page.size": 100},
        )
    )
    for row in rows:
        asset = row.get("result")
        if isinstance(asset, dict) and asset.get("id") == asset_id:
            if asset.get("status") != "ACTIVE" or asset.get("type") not in {"IMAGE", "VIDEO"}:
                raise ValueError("The creative asset must be an ACTIVE image or video before creating an ad post.")
            return asset
    raise ValueError("The creative asset does not belong to the selected profile.")


def media_url(asset: dict[str, Any], field: str = "media") -> dict[str, str]:
    media = asset.get(field)
    url = (media.get("permanent_url") or media.get("url")) if isinstance(media, dict) else None
    if not isinstance(url, str):
        raise ValueError("Reddit has not returned a usable hosted media URL.")
    return {"type": "URL", "url": public_url(url)}


def profile_post(client: RedditAdsClient, profile_id: str, post_id: str) -> dict[str, Any]:
    if not resource_id(post_id).startswith("t3_"):
        raise ValueError("post_id must be a Reddit t3_ post ID.")
    post = object_data(client.request("GET", f"structured_posts/{post_id}"))
    if post.get("id") != post_id or post.get("profile_id") != profile_id:
        raise ValueError("The ad post does not belong to the selected profile.")
    return post


def submit_job(client: RedditAdsClient, path: str, data: Any) -> dict[str, Any]:
    """One creation request, preserving uncertainty so clients do not duplicate it."""
    try:
        return client.request("POST", path, body={"data": data})
    except (requests.RequestException, RedditAdsApiError) as ex:
        rejected = isinstance(ex, RedditAdsApiError) and ex.status_code in {400, 401, 403, 404, 429}
        return {
            "error": True,
            "mutation_outcome": "rejected" if rejected else "unknown",
            "message": "Reddit did not confirm creation. Inspect the profile's creative inventory before retrying.",
        }
