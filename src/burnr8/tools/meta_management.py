"""Meta Ads discovery, reporting, preview, and guarded management tools."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.helpers import validate_daily_budget
from burnr8.meta.client import get_meta_client
from burnr8.meta.errors import handle_meta_ads_errors
from burnr8.meta.operations import (
    AD_FIELDS,
    AD_SET_FIELDS,
    CAMPAIGN_FIELDS,
    INSIGHT_FIELDS,
    META_DATE_PRESETS,
    collect_edge,
    dollars_to_minor_units,
    get_owned_resource,
    minor_units_to_dollars,
    normalize_insight_row,
    validate_effective_statuses,
    validate_insight_breakdowns,
    validate_insight_scope,
    validate_meta_resource_id,
    validate_mutable_status,
    validate_preview_format,
)
from burnr8.meta.session import require_meta_ad_account_id


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_meta_ads_errors
    def meta_list_campaigns(
        effective_statuses: Annotated[
            list[str] | None,
            Field(description="Optional effective-status filters such as ['ACTIVE', 'PAUSED']"),
        ] = None,
        max_results: Annotated[
            int, Field(description="Maximum rows to return across cursor pages", ge=1, le=2000)
        ] = 100,
        after: Annotated[str | None, Field(description="Optional Meta cursor returned as next_after")] = None,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """List campaigns for a Meta ad account with bounded cursor pagination and delivery/budget state."""
        normalized = require_meta_ad_account_id(account_id)
        statuses = validate_effective_statuses(effective_statuses, "campaign")
        params: dict[str, Any] = {"fields": CAMPAIGN_FIELDS}
        if statuses:
            params["effective_status"] = statuses
        rows, paging, _ = collect_edge(
            get_meta_client(),
            f"act_{normalized}/campaigns",
            params=params,
            label="campaigns",
            max_results=max_results,
            after=after,
        )
        return {"account_id": normalized, "campaigns": rows, "count": len(rows), "paging": paging}

    @mcp.tool
    @handle_meta_ads_errors
    def meta_list_ad_sets(
        campaign_id: Annotated[
            str | None,
            Field(description="Optional campaign ID to restrict results; ownership is verified first"),
        ] = None,
        effective_statuses: Annotated[
            list[str] | None,
            Field(description="Optional effective-status filters such as ['ACTIVE', 'PAUSED']"),
        ] = None,
        max_results: Annotated[
            int, Field(description="Maximum rows to return across cursor pages", ge=1, le=2000)
        ] = 100,
        after: Annotated[str | None, Field(description="Optional Meta cursor returned as next_after")] = None,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """List Meta ad sets for an account or one verified campaign, including targeting and budget configuration."""
        normalized = require_meta_ad_account_id(account_id)
        client = get_meta_client()
        path = f"act_{normalized}/adsets"
        if campaign_id is not None:
            campaign = get_owned_resource(client, "campaign", campaign_id, normalized)
            path = f"{campaign['id']}/adsets"
        params: dict[str, Any] = {"fields": AD_SET_FIELDS}
        if statuses := validate_effective_statuses(effective_statuses, "adset"):
            params["effective_status"] = statuses
        rows, paging, _ = collect_edge(
            client, path, params=params, label="ad sets", max_results=max_results, after=after
        )
        return {
            "account_id": normalized,
            "campaign_id": campaign_id,
            "ad_sets": rows,
            "count": len(rows),
            "paging": paging,
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_list_ads(
        campaign_id: Annotated[
            str | None,
            Field(description="Optional campaign ID to restrict results; cannot be combined with ad_set_id"),
        ] = None,
        ad_set_id: Annotated[
            str | None,
            Field(description="Optional ad-set ID to restrict results; cannot be combined with campaign_id"),
        ] = None,
        effective_statuses: Annotated[
            list[str] | None,
            Field(description="Optional effective-status filters such as ['ACTIVE', 'PAUSED']"),
        ] = None,
        max_results: Annotated[
            int, Field(description="Maximum rows to return across cursor pages", ge=1, le=2000)
        ] = 100,
        after: Annotated[str | None, Field(description="Optional Meta cursor returned as next_after")] = None,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """List Meta ads for an account, campaign, or ad set, including configured/effective status and creative metadata."""
        if campaign_id is not None and ad_set_id is not None:
            raise ValueError("Pass campaign_id or ad_set_id, not both.")
        normalized = require_meta_ad_account_id(account_id)
        client = get_meta_client()
        path = f"act_{normalized}/ads"
        if campaign_id is not None:
            campaign = get_owned_resource(client, "campaign", campaign_id, normalized)
            path = f"{campaign['id']}/ads"
        elif ad_set_id is not None:
            ad_set = get_owned_resource(client, "adset", ad_set_id, normalized)
            path = f"{ad_set['id']}/ads"
        params: dict[str, Any] = {"fields": AD_FIELDS}
        if statuses := validate_effective_statuses(effective_statuses, "ad"):
            params["effective_status"] = statuses
        rows, paging, _ = collect_edge(client, path, params=params, label="ads", max_results=max_results, after=after)
        return {
            "account_id": normalized,
            "campaign_id": campaign_id,
            "ad_set_id": ad_set_id,
            "ads": rows,
            "count": len(rows),
            "paging": paging,
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_get_insights(
        level: Annotated[str, Field(description="Aggregation level: account, campaign, adset, or ad")] = "campaign",
        scope: Annotated[
            str,
            Field(description="Reporting scope: account, campaign, adset, or ad; object scopes require scope_id"),
        ] = "account",
        scope_id: Annotated[str | None, Field(description="Campaign, ad-set, or ad ID for a non-account scope")] = None,
        date_preset: Annotated[
            str | None,
            Field(description="Meta date preset such as last_7d or last_30d; ignored when since/until are supplied"),
        ] = "last_30d",
        since: Annotated[str | None, Field(description="Optional custom start date in YYYY-MM-DD format")] = None,
        until: Annotated[str | None, Field(description="Optional custom end date in YYYY-MM-DD format")] = None,
        time_increment: Annotated[
            int | str,
            Field(description="all_days, monthly, or a day interval from 1 to 90"),
        ] = "all_days",
        breakdowns: Annotated[
            list[str] | None,
            Field(description="Up to three dimensions such as publisher_platform, platform_position, or age"),
        ] = None,
        max_results: Annotated[
            int, Field(description="Maximum rows to return across cursor pages", ge=1, le=2000)
        ] = 500,
        after: Annotated[str | None, Field(description="Optional Meta cursor returned as next_after")] = None,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """Return Meta Ads Insights with spend, reach, click, cost, and action metrics at a chosen reporting level."""
        normalized = require_meta_ad_account_id(account_id)
        normalized_scope, normalized_scope_id, normalized_level = validate_insight_scope(scope, scope_id, level)
        client = get_meta_client()
        if normalized_scope == "account":
            path = f"act_{normalized}/insights"
        else:
            assert normalized_scope_id is not None
            get_owned_resource(client, normalized_scope, normalized_scope_id, normalized)
            path = f"{normalized_scope_id}/insights"

        params: dict[str, Any] = {"fields": INSIGHT_FIELDS, "level": normalized_level, "default_summary": True}
        date_window = _insight_date_params(date_preset=date_preset, since=since, until=until)
        params.update(date_window)
        params["time_increment"] = _validate_time_increment(time_increment)
        if normalized_breakdowns := validate_insight_breakdowns(breakdowns):
            params["breakdowns"] = normalized_breakdowns

        rows, paging, summary = collect_edge(
            client, path, params=params, label="ad insights", max_results=max_results, after=after
        )
        return {
            "account_id": normalized,
            "scope": normalized_scope,
            "scope_id": normalized_scope_id,
            "level": normalized_level,
            "date_window": date_window,
            "breakdowns": normalized_breakdowns if breakdowns is not None else [],
            "insights": [normalize_insight_row(row) for row in rows],
            "count": len(rows),
            "summary": summary,
            "paging": paging,
            "attribution_note": "Meta-reported actions use the ad account's attribution settings; compare them with first-party analytics.",
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_get_ad_preview(
        ad_id: Annotated[str, Field(description="Meta ad ID to preview")],
        ad_format: Annotated[
            str,
            Field(description="Preview format such as INSTAGRAM_REELS or FACEBOOK_REELS_MOBILE"),
        ] = "INSTAGRAM_REELS",
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """Render Meta's preview markup for an owned ad in a supported Feed, Stories, or Reels format."""
        normalized = require_meta_ad_account_id(account_id)
        client = get_meta_client()
        ad = get_owned_resource(client, "ad", ad_id, normalized)
        normalized_format = validate_preview_format(ad_format)
        rows, _, _ = collect_edge(
            client,
            f"{ad['id']}/previews",
            params={"ad_format": normalized_format},
            label="ad previews",
            max_results=10,
        )
        return {
            "account_id": normalized,
            "ad": {key: ad.get(key) for key in ("id", "name", "status", "effective_status")},
            "ad_format": normalized_format,
            "previews": rows,
            "count": len(rows),
            "rendering_note": "Preview bodies are Meta-provided HTML and may load Meta-hosted resources.",
        }

    @mcp.tool
    @handle_meta_ads_errors
    def meta_set_campaign_status(
        campaign_id: Annotated[str, Field(description="Meta campaign ID to pause or activate")],
        status: Annotated[str, Field(description="New configured status: ACTIVE or PAUSED")],
        confirm: Annotated[bool, Field(description="Must be true to change campaign delivery")] = False,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """Pause or activate an owned Meta campaign after an explicit confirmation and verify the resulting state."""
        return _set_resource_status("campaign", campaign_id, status, confirm=confirm, account_id=account_id)

    @mcp.tool
    @handle_meta_ads_errors
    def meta_set_ad_set_status(
        ad_set_id: Annotated[str, Field(description="Meta ad-set ID to pause or activate")],
        status: Annotated[str, Field(description="New configured status: ACTIVE or PAUSED")],
        confirm: Annotated[bool, Field(description="Must be true to change ad-set delivery")] = False,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """Pause or activate an owned Meta ad set after an explicit confirmation and verify the resulting state."""
        return _set_resource_status("adset", ad_set_id, status, confirm=confirm, account_id=account_id)

    @mcp.tool
    @handle_meta_ads_errors
    def meta_set_ad_status(
        ad_id: Annotated[str, Field(description="Meta ad ID to pause or activate")],
        status: Annotated[str, Field(description="New configured status: ACTIVE or PAUSED")],
        confirm: Annotated[bool, Field(description="Must be true to change ad delivery")] = False,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """Pause or activate an owned Meta ad after an explicit confirmation and verify the resulting state."""
        return _set_resource_status("ad", ad_id, status, confirm=confirm, account_id=account_id)

    @mcp.tool
    @handle_meta_ads_errors
    def meta_update_ad_set_budget(
        ad_set_id: Annotated[str, Field(description="Meta ad-set ID whose daily budget should change")],
        daily_budget_dollars: Annotated[
            float,
            Field(description="New ad-set daily budget in USD; bounded by BURNR8_MAX_DAILY_BUDGET_DOLLARS", gt=0),
        ],
        confirm: Annotated[bool, Field(description="Must be true to change spend settings")] = False,
        account_id: Annotated[
            str | None,
            Field(description="Meta ad account ID. Uses the active account or META_AD_ACCOUNT_ID when omitted."),
        ] = None,
    ) -> dict[str, Any]:
        """Change an owned Meta ad set's existing USD daily budget with a hard cap, confirmation, and read-back verification."""
        normalized = require_meta_ad_account_id(account_id)
        normalized_ad_set_id = validate_meta_resource_id(ad_set_id, "ad_set_id")
        if err := validate_daily_budget(daily_budget_dollars):
            raise ValueError(err)
        new_minor_units = dollars_to_minor_units(daily_budget_dollars)
        if new_minor_units < 1:
            raise ValueError("daily_budget_dollars must round to at least $0.01.")
        new_dollars = minor_units_to_dollars(new_minor_units, "daily_budget_dollars")
        client = get_meta_client()
        current = get_owned_resource(client, "adset", normalized_ad_set_id, normalized)
        raw_current_budget = current.get("daily_budget")
        if raw_current_budget in (None, ""):
            raise ValueError(
                "This ad set has no ad-set daily budget. It may use a campaign-level or lifetime budget, which this tool will not change."
            )
        current_dollars = minor_units_to_dollars(raw_current_budget, "daily_budget")
        account = client.request(
            "GET", f"act_{normalized}", params={"fields": "id,account_id,name,account_status,currency,timezone_name"}
        )
        if account.get("currency") != "USD":
            raise ValueError(
                f"meta_update_ad_set_budget accepts USD amounts, but the selected account uses {account.get('currency') or 'an unknown currency'}."
            )
        if account.get("account_status") is not None and str(account["account_status"]) != "1":
            raise ValueError(f"Meta ad account is not active (account_status={account['account_status']}).")

        percent_change = _percent_change(current_dollars, new_dollars)
        plan = {
            "resource_type": "adset",
            "ad_set_id": normalized_ad_set_id,
            "ad_set_name": current.get("name"),
            "currency": "USD",
            "current_daily_budget_dollars": current_dollars,
            "new_daily_budget_dollars": new_dollars,
            "percent_change": percent_change,
            "large_change_warning": abs(percent_change) > 30 if percent_change is not None else None,
        }
        if new_minor_units == int(str(raw_current_budget)):
            return {"updated": False, "no_change": True, "account_id": normalized, "plan": plan}
        if not confirm:
            return {
                "warning": True,
                "validated": "client_and_account_read",
                "message": "No budget was changed. Review the plan, then repeat with confirm=true.",
                "account_id": normalized,
                "plan": plan,
            }

        response = client.request("POST", normalized_ad_set_id, params={"daily_budget": new_minor_units})
        if response.get("success") is False:
            raise ValueError("Meta did not acknowledge the ad-set budget update.")
        updated = get_owned_resource(client, "adset", normalized_ad_set_id, normalized)
        verified_minor_units = updated.get("daily_budget")
        if verified_minor_units is None or int(str(verified_minor_units)) != new_minor_units:
            raise ValueError("Meta acknowledged the update, but the new daily budget could not be verified.")
        return {
            "updated": True,
            "verified": True,
            "account_id": normalized,
            "plan": plan,
            "effective_daily_budget_dollars": minor_units_to_dollars(verified_minor_units, "daily_budget"),
            "learning_note": (
                "This changes the budget by more than 30%; monitor delivery and learning stability."
                if plan["large_change_warning"]
                else None
            ),
        }


def _set_resource_status(
    resource_type: str,
    resource_id: str,
    status: str,
    *,
    confirm: bool,
    account_id: str | None,
) -> dict[str, Any]:
    normalized = require_meta_ad_account_id(account_id)
    normalized_id = validate_meta_resource_id(resource_id, f"{resource_type}_id")
    target_status = validate_mutable_status(status)
    client = get_meta_client()
    current = get_owned_resource(client, resource_type, normalized_id, normalized)
    plan = {
        "resource_type": resource_type,
        "resource_id": normalized_id,
        "resource_name": current.get("name"),
        "current_status": current.get("status"),
        "current_effective_status": current.get("effective_status"),
        "new_status": target_status,
    }
    if current.get("status") == target_status:
        return {"updated": False, "no_change": True, "account_id": normalized, "plan": plan}
    if not confirm:
        return {
            "warning": True,
            "validated": "client_and_account_read",
            "message": "No delivery status was changed. Review the plan, then repeat with confirm=true.",
            "account_id": normalized,
            "plan": plan,
        }

    response = client.request("POST", normalized_id, params={"status": target_status})
    if response.get("success") is False:
        raise ValueError(f"Meta did not acknowledge the {resource_type} status update.")
    updated = get_owned_resource(client, resource_type, normalized_id, normalized)
    if updated.get("status") != target_status:
        raise ValueError(f"Meta acknowledged the update, but the {resource_type} status could not be verified.")
    return {
        "updated": True,
        "verified": True,
        "account_id": normalized,
        "plan": plan,
        "resource": updated,
    }


def _insight_date_params(*, date_preset: str | None, since: str | None, until: str | None) -> dict[str, Any]:
    if (since is None) != (until is None):
        raise ValueError("since and until must be supplied together.")
    if since is not None and until is not None:
        try:
            start = date.fromisoformat(since)
            end = date.fromisoformat(until)
        except ValueError:
            raise ValueError("since and until must use YYYY-MM-DD format.") from None
        if start > end:
            raise ValueError("since cannot be later than until.")
        if (end - start).days > 366:
            raise ValueError("Custom Insights ranges may span at most 367 days.")
        return {"time_range": {"since": since, "until": until}}
    normalized_preset = date_preset.lower() if isinstance(date_preset, str) else ""
    if normalized_preset not in META_DATE_PRESETS:
        allowed = ", ".join(sorted(META_DATE_PRESETS))
        raise ValueError(f"Unsupported date_preset '{date_preset}'. Choose from: {allowed}.")
    return {"date_preset": normalized_preset}


def _validate_time_increment(value: int | str) -> int | str:
    if isinstance(value, bool):
        raise ValueError("time_increment must be all_days, monthly, or an integer from 1 to 90.")
    if isinstance(value, int):
        if 1 <= value <= 90:
            return value
        raise ValueError("Numeric time_increment must be between 1 and 90 days.")
    if isinstance(value, str) and value.lower() in {"all_days", "monthly"}:
        return value.lower()
    raise ValueError("time_increment must be all_days, monthly, or an integer from 1 to 90.")


def _percent_change(current: float, new: float) -> float | None:
    if current == 0:
        return None
    return round(((new - current) / current) * 100, 2)
