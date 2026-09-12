"""Reddit Ads v3 inventory, reports, paused campaigns and delivery controls."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from burnr8.reddit.client import get_reddit_client
from burnr8.reddit.errors import handle_reddit_errors
from burnr8.reddit.helpers import (
    RESOURCE_PATHS,
    ResourceType,
    get_account,
    money_micros,
    owned_resource,
    pagination,
    require_usd,
    resource_id,
    write_and_verify,
)
from burnr8.reddit.helpers import (
    account_id as resolve_account_id,
)
from burnr8.reports import save_report

Account = Annotated[
    str | None, Field(description="Reddit ad account ID (a2_... or t2_...). Defaults to REDDIT_AD_ACCOUNT_ID.")
]
PageSize = Annotated[int, Field(ge=1, le=1000, description="Maximum rows on this page (1-1000).")]
NextURL = Annotated[
    str | None,
    Field(description="Exact next_url from the previous call. Keep the account, filters and report inputs unchanged."),
]
Confirm = Annotated[bool, Field(description="False previews the change; true sends the reviewed write to Reddit.")]
Breakdown = Literal["AD_ACCOUNT_ID", "CAMPAIGN_ID", "AD_GROUP_ID", "AD_ID", "DATE", "COMMUNITY", "COUNTRY", "PLACEMENT"]
_DEFAULT_FIELDS = [
    "IMPRESSIONS",
    "CLICKS",
    "SPEND",
    "CPC",
    "CTR",
    "CONVERSION_SIGN_UP_CLICKS",
    "CONVERSION_SIGN_UP_VIEWS",
    "CONVERSION_PURCHASE_CLICKS",
    "CONVERSION_PURCHASE_VIEWS",
]


def _list_page(
    path: str, *, page_size: int, next_url: str | None, filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000.")
    payload = get_reddit_client().request(
        "GET",
        path,
        params={"page.size": page_size, **(filters or {})},
        next_url=next_url,
    )
    rows = payload.get("data")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Reddit returned an invalid inventory page.")
    return {"data": rows, "rows": len(rows), **pagination(payload, path)}


def _preview(selected: str, plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "warning": True,
        "account_id": selected,
        "plan": plan,
        "validated": "local_and_account_read",
        "message": "No write sent to Reddit. Review the plan, then repeat with confirm=true.",
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_reddit_errors
    def reddit_list_businesses(page_size: PageSize = 100, next_url: NextURL = None) -> dict[str, Any]:
        """List businesses authorized through this Reddit OAuth identity, one bounded page at a time."""
        # The business discovery endpoint has a smaller documented maximum.
        return _list_page("me/businesses", page_size=min(page_size, 700), next_url=next_url)

    @mcp.tool
    @handle_reddit_errors
    def reddit_list_ad_accounts(
        business_id: str, page_size: PageSize = 100, next_url: NextURL = None
    ) -> dict[str, Any]:
        """List accessible Reddit ad accounts for a business returned by reddit_list_businesses."""
        return _list_page(f"businesses/{resource_id(business_id)}/ad_accounts", page_size=page_size, next_url=next_url)

    @mcp.tool
    @handle_reddit_errors
    def reddit_get_ad_account(account_id: Account = None) -> dict[str, Any]:
        """Read a Reddit ad account's currency, timezone, approval and attribution settings."""
        return get_account(get_reddit_client(), resolve_account_id(account_id))

    @mcp.tool
    @handle_reddit_errors
    def reddit_list_campaigns(
        account_id: Account = None, page_size: PageSize = 100, next_url: NextURL = None
    ) -> dict[str, Any]:
        """List Reddit campaigns with configured/effective status, objectives and budget settings."""
        return _list_page(
            f"ad_accounts/{resolve_account_id(account_id)}/campaigns", page_size=page_size, next_url=next_url
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_list_ad_groups(
        account_id: Account = None,
        campaign_id: str | None = None,
        page_size: PageSize = 100,
        next_url: NextURL = None,
    ) -> dict[str, Any]:
        """List Reddit ad groups, including targeting, schedule, bid and daily/lifetime budget configuration."""
        filters = {"campaign_id": resource_id(campaign_id)} if campaign_id is not None else {}
        return _list_page(
            f"ad_accounts/{resolve_account_id(account_id)}/ad_groups",
            page_size=page_size,
            next_url=next_url,
            filters=filters,
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_list_ads(
        account_id: Account = None, page_size: PageSize = 100, next_url: NextURL = None
    ) -> dict[str, Any]:
        """List Reddit ad creatives and configured/effective delivery states for the selected account."""
        return _list_page(f"ad_accounts/{resolve_account_id(account_id)}/ads", page_size=page_size, next_url=next_url)

    @mcp.tool
    @handle_reddit_errors
    def reddit_search_communities(query: str, page_size: PageSize = 100, next_url: NextURL = None) -> dict[str, Any]:
        """Find Reddit Ads community targeting options by topic/name; does not scrape posts or users."""
        if not query.strip() or len(query) > 200:
            raise ValueError("query must contain 1-200 characters.")
        return _list_page(
            "targeting/communities/search", page_size=page_size, next_url=next_url, filters={"query": query.strip()}
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_get_report(
        starts_at: Annotated[str, Field(description="Report start in UTC, YYYY-MM-DDTHH:00:00Z.")],
        ends_at: Annotated[
            str, Field(description="Report end in UTC, YYYY-MM-DDTHH:00:00Z; at most 31 days after start.")
        ],
        account_id: Account = None,
        breakdowns: list[Breakdown] | None = None,
        fields: list[str] | None = None,
        page_size: PageSize = 1000,
        next_url: NextURL = None,
    ) -> dict[str, Any]:
        """Export one Reddit performance page to CSV. Follow next_url until has_more=false for a complete report.

        Defaults to campaign/day delivery plus separate click- and view-attributed signup/purchase counts.
        Spend is retained in microcurrency and also exposed as spend_currency_units. CPC/CTR are unchanged.
        Reddit-attributed conversions do not establish Lily's confirmed first payments.
        """
        for timestamp in (starts_at, ends_at):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:00:00Z", timestamp):
                raise ValueError("Report timestamps must use YYYY-MM-DDTHH:00:00Z (UTC).")
        start, end = (datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ") for value in (starts_at, ends_at))
        if not 0 < (end - start).total_seconds() <= 31 * 86400:
            raise ValueError("Report end must be after start and within 31 days.")
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000.")
        selected_fields = _DEFAULT_FIELDS if fields is None else fields
        if (
            not selected_fields
            or len(selected_fields) > 50
            or any(not re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", f) for f in selected_fields)
        ):
            raise ValueError("Supply 1-50 uppercase Reddit reporting field names.")
        selected_breakdowns = ["CAMPAIGN_ID", "DATE"] if breakdowns is None else breakdowns
        allowed = {"AD_ACCOUNT_ID", "CAMPAIGN_ID", "AD_GROUP_ID", "AD_ID", "DATE", "COMMUNITY", "COUNTRY", "PLACEMENT"}
        if len(selected_breakdowns) > 3 or set(selected_breakdowns) - allowed:
            raise ValueError("Choose up to three supported report breakdowns.")
        if {"COMMUNITY", "COUNTRY"}.issubset(selected_breakdowns):
            raise ValueError("Request COMMUNITY and COUNTRY breakdowns in separate reports.")
        selected = resolve_account_id(account_id)
        client = get_reddit_client()
        info = get_account(client, selected)
        path = f"ad_accounts/{selected}/reports"
        payload = client.request(
            "POST",
            path,
            params={"page.size": page_size},
            next_url=next_url,
            body={
                "data": {
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "fields": selected_fields,
                    "breakdowns": selected_breakdowns,
                }
            },
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("metrics"), list):
            raise ValueError("Reddit returned an invalid report response.")
        rows = []
        for raw in data["metrics"]:
            if not isinstance(raw, dict):
                raise ValueError("Reddit returned an invalid report row.")
            row = dict(raw)
            if row.get("spend") is not None:
                row["spend_currency_units"] = int(row["spend"]) / 1_000_000
            rows.append(row)
        # Missing metric keys can differ by row; keep every column in the CSV.
        columns = list(dict.fromkeys(key for row in rows for key in row))
        result = save_report([{key: row.get(key) for key in columns} for row in rows], "reddit_performance")
        return {
            **result,
            **pagination(payload, path),
            "account_id": selected,
            "currency": info.get("currency"),
            "starts_at": starts_at,
            "ends_at": ends_at,
            "time_zone": "UTC",
            "metrics_updated_at": data.get("metrics_updated_at"),
            "click_attribution_window": info.get("click_attribution_window"),
            "view_attribution_window": info.get("view_attribution_window"),
        }

    @mcp.tool
    @handle_reddit_errors
    def reddit_create_campaign(
        name: str,
        objective: Literal["CLICKS", "CONVERSIONS", "IMPRESSIONS"],
        spend_cap_dollars: Annotated[
            float, Field(gt=0, description="USD campaign lifetime cap; default local ceiling $1000.")
        ],
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Create a PAUSED standard Reddit campaign with a required lifetime spend cap and ad-group budgets.

        Continue with reddit_create_ad_group, reddit_upload_media, reddit_create_ad_post and reddit_create_ad.
        Campaign, ad group and ad activation remain separate status changes after review.
        Uses the current objective names, which Reddit says remain supported after the September 2026 migration.
        """
        if not name.strip() or len(name) > 200:
            raise ValueError("Campaign name must contain 1-200 characters.")
        if objective not in {"CLICKS", "CONVERSIONS", "IMPRESSIONS"}:
            raise ValueError("Supported standard campaign objectives: CLICKS, CONVERSIONS, IMPRESSIONS.")
        selected = resolve_account_id(account_id)
        cap = money_micros(spend_cap_dollars)
        client = get_reddit_client()
        require_usd(client, selected)
        changes = {
            "name": name.strip(),
            "objective": objective,
            "configured_status": "PAUSED",
            "is_campaign_budget_optimization": False,
            "spend_cap": cap,
        }
        if not confirm:
            return _preview(
                selected,
                {
                    "resource_type": "campaign",
                    "currency": "USD",
                    "spend_cap_dollars": cap / 1_000_000,
                    "request": {"data": changes},
                },
            )
        return write_and_verify(
            client,
            method="POST",
            path=f"ad_accounts/{selected}/campaigns",
            kind="campaign",
            selected=selected,
            changes=changes,
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_set_status(
        resource_type: ResourceType,
        ident: str,
        status: Literal["ACTIVE", "PAUSED"],
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Preview/apply ACTIVE or PAUSED to an owned Reddit campaign, ad group or ad; verify configured state.

        Effective delivery can still be blocked by parent state, review, billing or schedule. No delete/archive.
        """
        if status not in {"ACTIVE", "PAUSED"}:
            raise ValueError("status must be ACTIVE or PAUSED.")
        selected = resolve_account_id(account_id)
        client = get_reddit_client()
        current = owned_resource(client, resource_type, ident, selected)
        plan = {
            "resource_type": resource_type,
            "resource_id": ident,
            "name": current.get("name"),
            "current_status": current.get("configured_status"),
            "effective_status": current.get("effective_status"),
            "new_status": status,
        }
        if current.get("configured_status") == status:
            return {"updated": False, "no_change": True, "account_id": selected, "plan": plan}
        if not confirm:
            return _preview(selected, plan)
        return write_and_verify(
            client,
            method="PATCH",
            path=f"{RESOURCE_PATHS[resource_type]}/{ident}",
            kind=resource_type,
            ident=ident,
            selected=selected,
            changes={"configured_status": status},
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_update_ad_group_budget(
        ad_group_id: str,
        daily_budget_dollars: float,
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Change an existing USD ad-group daily budget; never convert lifetime or campaign-controlled budgets.

        Enforces BURNR8_MAX_DAILY_BUDGET_DOLLARS, verifies ownership and reads the saved amount back.
        """
        selected = resolve_account_id(account_id)
        micros = money_micros(daily_budget_dollars, daily=True)
        client = get_reddit_client()
        current = owned_resource(client, "ad_group", ad_group_id, selected)
        parent = owned_resource(client, "campaign", str(current.get("campaign_id", "")), selected)
        if current.get("goal_type") != "DAILY_SPEND" or parent.get("is_campaign_budget_optimization") is not False:
            raise ValueError("Only existing daily budgets in campaigns with ad-group budgeting can be changed.")
        require_usd(client, selected)
        plan = {
            "ad_group_id": ad_group_id,
            "currency": "USD",
            "current_goal_value_micros": current.get("goal_value"),
            "new_goal_value_micros": micros,
            "new_daily_budget_dollars": micros / 1_000_000,
        }
        if current.get("goal_value") == micros:
            return {"updated": False, "no_change": True, "account_id": selected, "plan": plan}
        if not confirm:
            return _preview(selected, plan)
        return write_and_verify(
            client,
            method="PATCH",
            path=f"ad_groups/{ad_group_id}",
            kind="ad_group",
            ident=ad_group_id,
            selected=selected,
            changes={"goal_value": micros},
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_update_campaign_spend_cap(
        campaign_id: str,
        spend_cap_dollars: float,
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Change a USD campaign lifetime cap for a standard campaign using ad-group budgets, with read-back verification."""
        selected = resolve_account_id(account_id)
        micros = money_micros(spend_cap_dollars)
        client = get_reddit_client()
        current = owned_resource(client, "campaign", campaign_id, selected)
        if current.get("is_campaign_budget_optimization") is not False:
            raise ValueError("This tool only changes lifetime spend caps on campaigns using ad-group budgets.")
        require_usd(client, selected)
        plan = {
            "campaign_id": campaign_id,
            "currency": "USD",
            "current_spend_cap_micros": current.get("spend_cap"),
            "new_spend_cap_micros": micros,
            "new_spend_cap_dollars": micros / 1_000_000,
        }
        if current.get("spend_cap") == micros:
            return {"updated": False, "no_change": True, "account_id": selected, "plan": plan}
        if not confirm:
            return _preview(selected, plan)
        return write_and_verify(
            client,
            method="PATCH",
            path=f"campaigns/{campaign_id}",
            kind="campaign",
            ident=campaign_id,
            selected=selected,
            changes={"spend_cap": micros},
        )
