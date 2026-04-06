from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import dollars_to_micros, micros_to_dollars, run_gaql, validate_id, validate_status
from burnr8.session import resolve_customer_id


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_ad_groups(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        campaign_id: Annotated[str | None, Field(description="Filter by campaign ID")] = None,
    ) -> list[dict] | dict:
        """List ad groups, optionally filtered by campaign."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = """
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                ad_group.type,
                ad_group.cpc_bid_micros,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros
            FROM ad_group
        """
        if campaign_id is not None:
            query += f" WHERE campaign.id = {campaign_id}"
        query += " ORDER BY ad_group.name"
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            results.append(
                {
                    "id": ag.get("id"),
                    "name": ag.get("name"),
                    "status": ag.get("status"),
                    "type": ag.get("type"),
                    "cpc_bid_dollars": micros_to_dollars(int(ag.get("cpc_bid_micros", 0))),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost_dollars": micros_to_dollars(int(m.get("cost_micros", 0))),
                }
            )
        return results

    @mcp.tool
    @handle_google_ads_errors
    def create_ad_group(
        campaign_id: Annotated[str, Field(description="Campaign ID to add the ad group to")],
        name: Annotated[str, Field(description="Ad group name")],
        cpc_bid: Annotated[float, Field(description="CPC bid in dollars")] = 1.0,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create a new ad group in a campaign."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        client = get_client()
        ad_group_service = client.get_service("AdGroupService")
        campaign_service = client.get_service("CampaignService")

        operation = client.get_type("AdGroupOperation")
        ad_group = operation.create

        ad_group.name = name
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
        ad_group.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
        ad_group.cpc_bid_micros = dollars_to_micros(cpc_bid)

        response = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[operation])
        resource_name = response.results[0].resource_name
        new_id = resource_name.split("/")[-1]
        return {"id": new_id, "resource_name": resource_name, "name": name}

    @mcp.tool
    @handle_google_ads_errors
    def update_ad_group(
        ad_group_id: Annotated[str, Field(description="Ad group ID to update")],
        name: Annotated[str | None, Field(description="New ad group name")] = None,
        cpc_bid: Annotated[float | None, Field(description="New CPC bid in dollars")] = None,
        status: Annotated[str | None, Field(description="New status: ENABLED, PAUSED, or REMOVED")] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Update an ad group's name, bid, or status."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(ad_group_id, "ad_group_id"):
            return {"error": True, "message": err}
        client = get_client()
        ad_group_service = client.get_service("AdGroupService")

        operation = client.get_type("AdGroupOperation")
        ad_group = operation.update
        ad_group.resource_name = ad_group_service.ad_group_path(customer_id, ad_group_id)

        field_mask = []
        if name is not None:
            ad_group.name = name
            field_mask.append("name")
        if cpc_bid is not None:
            ad_group.cpc_bid_micros = dollars_to_micros(cpc_bid)
            field_mask.append("cpc_bid_micros")
        if status is not None:
            if err := validate_status(status):
                return {"error": True, "message": err}
            status_map = {
                "ENABLED": client.enums.AdGroupStatusEnum.ENABLED,
                "PAUSED": client.enums.AdGroupStatusEnum.PAUSED,
                "REMOVED": client.enums.AdGroupStatusEnum.REMOVED,
            }
            ad_group.status = status_map[status.upper()]
            field_mask.append("status")

        if not field_mask:
            return {"error": True, "message": "No fields to update"}

        operation.update_mask.paths.extend(field_mask)

        response = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[operation])
        return {"resource_name": response.results[0].resource_name, "updated_fields": field_mask}
