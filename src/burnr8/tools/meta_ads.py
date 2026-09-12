"""Meta Ads tools for image-based Facebook and Instagram Reels campaigns."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import urlsplit

import requests
from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.helpers import validate_daily_budget
from burnr8.meta.client import MetaAdsApiError, MetaAdsClient, get_meta_client
from burnr8.meta.errors import handle_meta_ads_errors
from burnr8.meta.media import ValidatedImage, get_media_root, validate_local_image
from burnr8.meta.session import require_meta_ad_account_id, set_active_meta_ad_account

_CTA_TYPES = {
    "APPLY_NOW",
    "BOOK_NOW",
    "CONTACT_US",
    "DOWNLOAD",
    "GET_STARTED",
    "LEARN_MORE",
    "SHOP_NOW",
    "SIGN_UP",
    "SUBSCRIBE",
}
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_meta_ads_errors
    def meta_list_ad_accounts() -> dict:
        """List Meta ad accounts available to the configured access token, including status, currency, and timezone."""
        client = get_meta_client()
        payload = client.request(
            "GET",
            "me/adaccounts",
            params={"fields": "id,account_id,name,account_status,currency,timezone_name", "limit": 100},
        )
        return {
            "accounts": _extract_data(payload, "Meta ad accounts"),
            "hint": "Call meta_set_active_ad_account once to use an account by default.",
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_set_active_ad_account(
        account_id: Annotated[str, Field(description="Meta ad account ID, with or without the act_ prefix")],
    ) -> dict:
        """Verify and select a Meta ad account for this request context and subsequent Meta tools."""
        normalized = require_meta_ad_account_id(account_id)
        client = get_meta_client()
        account = client.request(
            "GET",
            f"act_{normalized}",
            params={"fields": "id,account_id,name,account_status,currency,timezone_name"},
        )
        set_active_meta_ad_account(normalized)
        return {
            "active_account_id": normalized,
            "account": account,
            "message": f"Active Meta ad account set to {account.get('name', normalized)} ({normalized}).",
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_get_account_assets(
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict:
        """Get a Meta ad account plus its promotable Facebook Pages and connected Instagram accounts for campaign setup."""
        normalized = require_meta_ad_account_id(account_id)
        client = get_meta_client()
        account = client.request(
            "GET",
            f"act_{normalized}",
            params={"fields": "id,account_id,name,account_status,currency,timezone_name"},
        )
        pages_payload = client.request(
            "GET", f"act_{normalized}/promote_pages", params={"fields": "id,name", "limit": 100}
        )
        instagram_payload = client.request(
            "GET",
            f"act_{normalized}/connected_instagram_accounts",
            params={"fields": "id,username,name", "limit": 100},
        )
        return {
            "account": account,
            "facebook_pages": _extract_data(pages_payload, "Facebook Pages"),
            "instagram_accounts": _extract_data(instagram_payload, "Instagram accounts"),
            "next_step": "Use a Page id and Instagram account id with meta_create_reels_campaign.",
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_upload_image(
        image_path: Annotated[
            str,
            Field(
                description="Local JPEG or PNG path beneath BURNR8_MEDIA_ROOT (defaults to the server working directory)"
            ),
        ],
        confirm: Annotated[bool, Field(description="Must be true to upload the image to Meta.")] = False,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict:
        """Validate and upload one local JPEG/PNG to a Meta ad account, returning the reusable image hash. No upload occurs until confirm=true."""
        normalized = require_meta_ad_account_id(account_id)
        image = validate_local_image(image_path)
        if not confirm:
            return {
                "warning": True,
                "validated": "client_side",
                "message": "Image validation passed but nothing was uploaded. Set confirm=true to upload it to Meta.",
                "account_id": normalized,
                "media_root": str(get_media_root()),
                "image": image.as_dict(),
            }
        client = get_meta_client()
        result = _upload_image(client, normalized, image)
        return {
            "account_id": normalized,
            "uploaded": True,
            "image": {**image.as_dict(), **result},
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_create_reels_campaign(
        campaign_name: Annotated[str, Field(description="Name for the new Meta traffic campaign")],
        image_paths: Annotated[
            list[str],
            Field(description="One to ten local JPEG/PNG paths; one paused ad is created per photo"),
        ],
        page_id: Annotated[str, Field(description="Facebook Page ID used as the ad identity")],
        instagram_user_id: Annotated[str, Field(description="Connected Instagram account ID used as the ad identity")],
        landing_url: Annotated[str, Field(description="HTTPS destination URL for every ad")],
        primary_text: Annotated[str, Field(description="Primary text shown with each Reels image ad")],
        headline: Annotated[str, Field(description="Headline shown with each Reels image ad")],
        daily_budget_dollars: Annotated[float, Field(description="Ad-set daily budget in USD", gt=0)],
        countries: Annotated[
            list[str] | None,
            Field(description="Two-letter country codes to target, such as ['US']; defaults to ['US']"),
        ] = None,
        age_min: Annotated[int, Field(description="Minimum target age (18-65)", ge=18, le=65)] = 18,
        age_max: Annotated[int, Field(description="Maximum target age (18-65; 65 means 65+)", ge=18, le=65)] = 65,
        call_to_action: Annotated[
            str,
            Field(
                description="CTA: LEARN_MORE, SIGN_UP, GET_STARTED, APPLY_NOW, BOOK_NOW, CONTACT_US, DOWNLOAD, SHOP_NOW, or SUBSCRIBE"
            ),
        ] = "LEARN_MORE",
        description: Annotated[str | None, Field(description="Optional link description")] = None,
        url_tags: Annotated[
            str | None,
            Field(description="Optional query tags without '?', e.g. utm_source=meta&utm_medium=paid_social"),
        ] = None,
        enable_standard_enhancements: Annotated[
            bool,
            Field(description="Opt into Meta standard creative enhancements; false explicitly opts out"),
        ] = False,
        confirm: Annotated[
            bool,
            Field(description="Must be true to upload photos and create the paused campaign objects."),
        ] = False,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict:
        """Upload photos and create a USD traffic campaign limited to Facebook and Instagram Reels. Creates one ad per photo; campaign, ad set, and ads always start PAUSED."""
        normalized = require_meta_ad_account_id(account_id)
        target_countries = ["US"] if countries is None else countries
        images = _validate_reels_campaign(
            campaign_name=campaign_name,
            image_paths=image_paths,
            page_id=page_id,
            instagram_user_id=instagram_user_id,
            landing_url=landing_url,
            primary_text=primary_text,
            headline=headline,
            daily_budget_dollars=daily_budget_dollars,
            countries=target_countries,
            age_min=age_min,
            age_max=age_max,
            call_to_action=call_to_action,
            description=description,
            url_tags=url_tags,
        )
        warnings = [image.reels_warning for image in images if image.reels_warning]
        plan = _campaign_plan(
            normalized,
            campaign_name.strip(),
            images,
            daily_budget_dollars,
            target_countries,
            age_min,
            age_max,
            enable_standard_enhancements,
        )
        if not confirm:
            return {
                "warning": True,
                "validated": "client_side",
                "message": "Client-side validation passed; no API calls or uploads were made. Set confirm=true to create everything paused.",
                "plan": plan,
                "image_warnings": warnings or None,
            }

        client = get_meta_client()
        created: dict[str, Any] = {
            "uploaded_images": [],
            "campaign_id": None,
            "ad_set_id": None,
            "creative_ids": [],
            "ad_ids": [],
        }
        account = client.request(
            "GET",
            f"act_{normalized}",
            params={"fields": "id,account_id,name,account_status,currency,timezone_name"},
        )
        _require_usable_usd_account(account)
        try:
            for image in images:
                uploaded = _upload_image(client, normalized, image)
                created["uploaded_images"].append({"filename": image.filename, **uploaded})

            campaign_response = client.request(
                "POST",
                f"act_{normalized}/campaigns",
                params={
                    "name": campaign_name.strip(),
                    "objective": "OUTCOME_TRAFFIC",
                    "buying_type": "AUCTION",
                    "special_ad_categories": [],
                    "status": "PAUSED",
                },
            )
            campaign_id = _require_created_id(campaign_response, "campaign")
            created["campaign_id"] = campaign_id

            budget_minor_units = int(
                (Decimal(str(daily_budget_dollars)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            ad_set_response = client.request(
                "POST",
                f"act_{normalized}/adsets",
                params={
                    "name": f"{campaign_name.strip()} - Reels",
                    "campaign_id": campaign_id,
                    "daily_budget": budget_minor_units,
                    "billing_event": "IMPRESSIONS",
                    "optimization_goal": "LANDING_PAGE_VIEWS",
                    "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                    "destination_type": "WEBSITE",
                    "targeting": {
                        "geo_locations": {"countries": target_countries},
                        "age_min": age_min,
                        "age_max": age_max,
                        "publisher_platforms": ["facebook", "instagram"],
                        "facebook_positions": ["facebook_reels"],
                        "instagram_positions": ["reels"],
                        "device_platforms": ["mobile"],
                    },
                    "status": "PAUSED",
                },
            )
            ad_set_id = _require_created_id(ad_set_response, "ad set")
            created["ad_set_id"] = ad_set_id

            for index, uploaded in enumerate(created["uploaded_images"], start=1):
                image_hash = uploaded["image_hash"]
                link_data: dict[str, Any] = {
                    "image_hash": image_hash,
                    "link": landing_url,
                    "message": primary_text.strip(),
                    "name": headline.strip(),
                    "call_to_action": {"type": call_to_action.upper(), "value": {"link": landing_url}},
                }
                if description and description.strip():
                    link_data["description"] = description.strip()
                creative_params: dict[str, Any] = {
                    "name": f"{campaign_name.strip()} - Photo {index}",
                    "object_story_spec": {
                        "page_id": page_id,
                        "instagram_user_id": instagram_user_id,
                        "link_data": link_data,
                    },
                    "degrees_of_freedom_spec": {
                        "creative_features_spec": {
                            "standard_enhancements": {
                                "enroll_status": "OPT_IN" if enable_standard_enhancements else "OPT_OUT"
                            }
                        }
                    },
                }
                if url_tags:
                    creative_params["url_tags"] = url_tags
                creative_response = client.request("POST", f"act_{normalized}/adcreatives", params=creative_params)
                creative_id = _require_created_id(creative_response, "ad creative")
                created["creative_ids"].append(creative_id)

                ad_response = client.request(
                    "POST",
                    f"act_{normalized}/ads",
                    params={
                        "name": f"{campaign_name.strip()} - Photo {index}",
                        "adset_id": ad_set_id,
                        "creative": {"creative_id": creative_id},
                        "status": "PAUSED",
                    },
                )
                created["ad_ids"].append(_require_created_id(ad_response, "ad"))
        except (MetaAdsApiError, requests.RequestException, OSError, ValueError) as ex:
            return _partial_failure(ex, normalized, created)

        return {
            "created": True,
            "account_id": normalized,
            "account_name": account.get("name"),
            "status": "PAUSED",
            "review_required": True,
            "campaign": created,
            "placements": ["facebook_reels", "instagram_reels"],
            "image_warnings": warnings or None,
            "message": "Campaign, ad set, creatives, and ads were created PAUSED. Review them in Meta Ads Manager before enabling delivery.",
        }


def _extract_data(payload: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError(f"Meta returned an unexpected {label} response.")
    return [dict(item) for item in data if isinstance(item, Mapping)]


def _upload_image(client: MetaAdsClient, account_id: str, image: ValidatedImage) -> dict[str, Any]:
    with image.path.open("rb") as handle:
        response = client.request(
            "POST",
            f"act_{account_id}/adimages",
            files={"filename": (image.filename, handle, image.content_type)},
        )
    images = response.get("images")
    if not isinstance(images, Mapping) or not images:
        raise ValueError("Meta image upload succeeded but returned no image metadata.")
    raw = next(iter(images.values()))
    if not isinstance(raw, Mapping) or not raw.get("hash"):
        raise ValueError("Meta image upload response did not include an image hash.")
    return {
        "image_hash": str(raw["hash"]),
        "meta_name": raw.get("name"),
        "meta_url": raw.get("url"),
        "meta_width": raw.get("width"),
        "meta_height": raw.get("height"),
    }


def _validate_reels_campaign(
    *,
    campaign_name: str,
    image_paths: list[str],
    page_id: str,
    instagram_user_id: str,
    landing_url: str,
    primary_text: str,
    headline: str,
    daily_budget_dollars: float,
    countries: list[str],
    age_min: int,
    age_max: int,
    call_to_action: str,
    description: str | None,
    url_tags: str | None,
) -> list[ValidatedImage]:
    _validate_text(campaign_name, "campaign_name", 255)
    _validate_text(primary_text, "primary_text", 2200)
    _validate_text(headline, "headline", 255)
    if description is not None and description.strip():
        _validate_text(description, "description", 255)
    _validate_numeric_id(page_id, "page_id")
    _validate_numeric_id(instagram_user_id, "instagram_user_id")
    _validate_https_url(landing_url)
    if err := validate_daily_budget(daily_budget_dollars):
        raise ValueError(err)
    if not math.isfinite(float(daily_budget_dollars)):
        raise ValueError("daily_budget_dollars must be finite.")
    if not isinstance(image_paths, list) or not 1 <= len(image_paths) <= 10:
        raise ValueError("image_paths must contain between 1 and 10 photos.")
    if len(set(image_paths)) != len(image_paths):
        raise ValueError("image_paths cannot contain duplicate photos.")
    images = [validate_local_image(path) for path in image_paths]
    if not isinstance(countries, list) or not countries:
        raise ValueError("countries must contain at least one two-letter country code.")
    if len(countries) > 25:
        raise ValueError("countries may contain at most 25 country codes.")
    for country in countries:
        if not isinstance(country, str) or not _COUNTRY_RE.fullmatch(country):
            raise ValueError("countries must use uppercase two-letter codes such as 'US'.")
    if age_min > age_max:
        raise ValueError("age_min cannot be greater than age_max.")
    if not 18 <= age_min <= 65 or not 18 <= age_max <= 65:
        raise ValueError("age_min and age_max must be between 18 and 65.")
    if call_to_action.upper() not in _CTA_TYPES:
        raise ValueError(f"call_to_action must be one of: {', '.join(sorted(_CTA_TYPES))}.")
    if url_tags is not None:
        if url_tags.startswith("?"):
            raise ValueError("url_tags must not start with '?'.")
        if len(url_tags) > 2000 or any(ord(char) < 32 for char in url_tags):
            raise ValueError("url_tags must be at most 2000 characters and contain no control characters.")
    return images


def _validate_text(value: str, field: str, max_length: int) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty.")
    if len(value.strip()) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters.")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise ValueError(f"{field} contains unsupported control characters.")


def _validate_numeric_id(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip().isdigit():
        raise ValueError(f"{field} must contain digits only.")


def _validate_https_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("landing_url must be a valid HTTPS URL without embedded credentials.")
    if any(ord(char) < 33 for char in value):
        raise ValueError("landing_url contains whitespace or control characters.")


def _require_usable_usd_account(account: Mapping[str, Any]) -> None:
    currency = account.get("currency")
    if currency != "USD":
        raise ValueError(
            f"This first Reels workflow supports USD ad accounts only; the selected account uses {currency or 'an unknown currency'}."
        )
    status = account.get("account_status")
    if status is not None:
        try:
            status_value = int(status)
        except (TypeError, ValueError):
            raise ValueError("Meta returned an invalid ad account status.") from None
        if status_value != 1:
            raise ValueError(f"Meta ad account is not active (account_status={status_value}).")


def _require_created_id(response: Mapping[str, Any], label: str) -> str:
    resource_id = response.get("id")
    if resource_id is None or not str(resource_id).isdigit():
        raise ValueError(f"Meta did not return an ID for the created {label}.")
    return str(resource_id)


def _campaign_plan(
    account_id: str,
    campaign_name: str,
    images: list[ValidatedImage],
    daily_budget_dollars: float,
    countries: list[str],
    age_min: int,
    age_max: int,
    enable_standard_enhancements: bool,
) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "campaign_name": campaign_name,
        "objective": "OUTCOME_TRAFFIC",
        "optimization_goal": "LANDING_PAGE_VIEWS",
        "daily_budget_usd": round(float(daily_budget_dollars), 2),
        "targeting": {"countries": countries, "age_min": age_min, "age_max": age_max},
        "placements": ["facebook_reels", "instagram_reels"],
        "device_platforms": ["mobile"],
        "images": [image.as_dict() for image in images],
        "objects_to_create": {
            "campaigns": 1,
            "ad_sets": 1,
            "creatives": len(images),
            "ads": len(images),
        },
        "initial_status": "PAUSED",
        "standard_enhancements": "OPT_IN" if enable_standard_enhancements else "OPT_OUT",
    }


def _partial_failure(
    ex: MetaAdsApiError | requests.RequestException | OSError | ValueError,
    account_id: str,
    created: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(ex, MetaAdsApiError):
        result = ex.as_dict()
    elif isinstance(ex, requests.RequestException):
        result = {
            "error": True,
            "message": "Could not reach the Meta Marketing API. Check the network connection and try again.",
        }
    else:
        result = {"error": True, "message": str(ex)[:500]}
    result.update(
        {
            "partial_failure": True,
            "account_id": account_id,
            "created_before_failure": created,
            "safety_note": "Any campaign, ad set, or ad listed above was created PAUSED.",
        }
    )
    return result
