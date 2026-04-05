from typing import Annotated

from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id, validate_status
from burnr8.reports import save_report
from burnr8.session import resolve_customer_id


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_ads(
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
        ad_group_id: Annotated[str | None, Field(description="Filter by ad group ID")] = None,
    ) -> dict:
        """List ads with approval status and performance metrics. Saves full results to CSV, returns summary + top rows."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if ad_group_id and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = """
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.ad.final_urls,
                ad_group_ad.ad.responsive_search_ad.headlines,
                ad_group_ad.ad.responsive_search_ad.descriptions,
                ad_group_ad.ad_strength,
                ad_group_ad.status,
                ad_group_ad.policy_summary.approval_status,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM ad_group_ad
        """
        conditions = ["ad_group_ad.status != 'REMOVED'"]
        if ad_group_id:
            conditions.append(f"ad_group.id = {ad_group_id}")
        query += " WHERE " + " AND ".join(conditions)

        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            ad = row.get("ad_group_ad", {}).get("ad", {})
            aga = row.get("ad_group_ad", {})
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})

            rsa = ad.get("responsive_search_ad", {})
            headlines = [h.get("text", "") for h in rsa.get("headlines", [])] if rsa else []
            descriptions = [d.get("text", "") for d in rsa.get("descriptions", [])] if rsa else []

            results.append({
                "ad_id": ad.get("id"),
                "type": ad.get("type"),
                "final_urls": "|".join(ad.get("final_urls", [])),
                "headlines": "|".join(headlines),
                "descriptions": "|".join(descriptions),
                "ad_strength": aga.get("ad_strength"),
                "status": aga.get("status"),
                "approval_status": aga.get("policy_summary", {}).get("approval_status"),
                "ad_group_id": ag.get("id"),
                "ad_group_name": ag.get("name"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
            })

        # Build summary: ad strength distribution and approval status counts
        strength_counts: dict[str, int] = {}
        approval_counts: dict[str, int] = {}
        for r in results:
            strength = r.get("ad_strength") or "UNKNOWN"
            strength_counts[strength] = strength_counts.get(strength, 0) + 1
            approval = r.get("approval_status") or "UNKNOWN"
            approval_counts[approval] = approval_counts.get(approval, 0) + 1

        report = save_report(results, "ads")
        if report.get("error"):
            return report
        report["summary"] = {
            "total_ads": len(results),
            "ad_strength_distribution": strength_counts,
            "approval_status_counts": approval_counts,
        }
        return report

    @mcp.tool
    @handle_google_ads_errors
    def create_responsive_search_ad(
        ad_group_id: Annotated[str, Field(description="Ad group ID to add the ad to")],
        headlines: Annotated[list[str], Field(description="List of 3-15 headline texts (max 30 chars each)")],
        descriptions: Annotated[list[str], Field(description="List of 2-4 description texts (max 90 chars each)")],
        final_url: Annotated[str, Field(description="Landing page URL")],
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Create a responsive search ad in an ad group."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(ad_group_id, "ad_group_id"):
            return {"error": True, "message": err}
        client = get_client()
        ad_group_ad_service = client.get_service("AdGroupAdService")
        ad_group_service = client.get_service("AdGroupService")

        operation = client.get_type("AdGroupAdOperation")
        ad_group_ad = operation.create

        ad_group_ad.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
        ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

        ad = ad_group_ad.ad
        ad.final_urls.append(final_url)

        for headline_text in headlines:
            headline = client.get_type("AdTextAsset")
            headline.text = headline_text
            ad.responsive_search_ad.headlines.append(headline)

        for desc_text in descriptions:
            desc = client.get_type("AdTextAsset")
            desc.text = desc_text
            ad.responsive_search_ad.descriptions.append(desc)

        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=[operation]
        )
        resource_name = response.results[0].resource_name
        return {"resource_name": resource_name, "headlines_count": len(headlines), "descriptions_count": len(descriptions)}

    @mcp.tool
    @handle_google_ads_errors
    def set_ad_status(
        ad_group_id: Annotated[str, Field(description="Ad group ID containing the ad")],
        ad_id: Annotated[str, Field(description="Ad ID")],
        status: Annotated[str, Field(description="New status: ENABLED, PAUSED, or REMOVED")],
        confirm: Annotated[bool, Field(description="Must be true to execute. Enabling an ad means it can serve and spend budget.")] = False,
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Enable, pause, or remove an ad. Requires confirm=true for safety."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_status(status):
            return {"error": True, "message": err}
        if not confirm:
            return {
                "warning": f"This will set ad {ad_id} to {status.upper()}. "
                "Set confirm=true to execute."
            }

        client = get_client()
        ad_group_ad_service = client.get_service("AdGroupAdService")

        operation = client.get_type("AdGroupAdOperation")
        ad_group_ad = operation.update
        ad_group_ad.resource_name = ad_group_ad_service.ad_group_ad_path(
            customer_id, ad_group_id, ad_id
        )

        status_map = {
            "ENABLED": client.enums.AdGroupAdStatusEnum.ENABLED,
            "PAUSED": client.enums.AdGroupAdStatusEnum.PAUSED,
            "REMOVED": client.enums.AdGroupAdStatusEnum.REMOVED,
        }
        ad_group_ad.status = status_map[status.upper()]
        operation.update_mask.paths.append("status")

        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=[operation]
        )
        return {"resource_name": response.results[0].resource_name, "new_status": status.upper()}
