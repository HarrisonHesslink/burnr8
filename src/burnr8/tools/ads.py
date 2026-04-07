from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import micros_to_dollars, require_customer_id, run_gaql, validate_id, validate_status
from burnr8.reports import save_report


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_ads(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        ad_group_id: Annotated[str | None, Field(description="Filter by ad group ID")] = None,
    ) -> dict:
        """List ads with approval status and performance metrics. Saves full results to CSV, returns summary + top rows."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if ad_group_id is not None and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = """
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.ad.final_urls,
                ad_group_ad.ad.tracking_url_template,
                ad_group_ad.ad.final_url_suffix,
                ad_group_ad.ad.url_custom_parameters,
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

            results.append(
                {
                    "ad_id": ad.get("id"),
                    "type": ad.get("type"),
                    "final_urls": "|".join(ad.get("final_urls", [])),
                    "tracking_url_template": ad.get("tracking_url_template"),
                    "final_url_suffix": ad.get("final_url_suffix"),
                    "url_custom_parameters": {
                        p["key"]: p["value"] for p in ad.get("url_custom_parameters", []) if "key" in p
                    } or None,
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
                    "cost_dollars": micros_to_dollars(int(m.get("cost_micros", 0))),
                    "conversions": float(m.get("conversions", 0)),
                }
            )

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
        tracking_url_template: Annotated[
            str | None,
            Field(description="URL template for tracking, e.g. '{lpurl}?utm_source=google&utm_campaign={campaignid}'"),
        ] = None,
        final_url_suffix: Annotated[
            str | None,
            Field(description="Suffix appended to final URLs, e.g. 'utm_source=google&utm_medium=cpc'"),
        ] = None,
        url_custom_parameters: Annotated[
            dict[str, str] | None,
            Field(description="Custom parameters for tracking URL substitution, e.g. {'season': 'winter'} for {_season} tag"),
        ] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create a responsive search ad in an ad group."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
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

        if tracking_url_template is not None:
            ad.tracking_url_template = tracking_url_template
        if final_url_suffix is not None:
            ad.final_url_suffix = final_url_suffix
        if url_custom_parameters is not None:
            for key, value in url_custom_parameters.items():
                param = client.get_type("CustomParameter")
                param.key = key
                param.value = value
                ad.url_custom_parameters.append(param)

        for headline_text in headlines:
            headline = client.get_type("AdTextAsset")
            headline.text = headline_text
            ad.responsive_search_ad.headlines.append(headline)

        for desc_text in descriptions:
            desc = client.get_type("AdTextAsset")
            desc.text = desc_text
            ad.responsive_search_ad.descriptions.append(desc)

        response = ad_group_ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation])
        resource_name = response.results[0].resource_name
        result = {
            "resource_name": resource_name,
            "headlines_count": len(headlines),
            "descriptions_count": len(descriptions),
        }
        if tracking_url_template is not None:
            result["tracking_url_template"] = tracking_url_template
        if final_url_suffix is not None:
            result["final_url_suffix"] = final_url_suffix
        if url_custom_parameters is not None:
            result["url_custom_parameters"] = url_custom_parameters
        return result

    @mcp.tool
    @handle_google_ads_errors
    def set_ad_status(
        ad_group_id: Annotated[str, Field(description="Ad group ID containing the ad")],
        ad_id: Annotated[str, Field(description="Ad ID")],
        status: Annotated[str, Field(description="New status: ENABLED, PAUSED, or REMOVED")],
        confirm: Annotated[
            bool, Field(description="Must be true to execute. Enabling an ad means it can serve and spend budget.")
        ] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Enable, pause, or remove an ad. Requires confirm=true for safety."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_status(status):
            return {"error": True, "message": err}
        if not confirm:
            return {"warning": True, "message": f"This will set ad {ad_id} to {status.upper()}. Set confirm=true to execute."}

        client = get_client()
        ad_group_ad_service = client.get_service("AdGroupAdService")

        operation = client.get_type("AdGroupAdOperation")
        ad_group_ad = operation.update
        ad_group_ad.resource_name = ad_group_ad_service.ad_group_ad_path(customer_id, ad_group_id, ad_id)

        status_map = {
            "ENABLED": client.enums.AdGroupAdStatusEnum.ENABLED,
            "PAUSED": client.enums.AdGroupAdStatusEnum.PAUSED,
            "REMOVED": client.enums.AdGroupAdStatusEnum.REMOVED,
        }
        ad_group_ad.status = status_map[status.upper()]
        operation.update_mask.paths.append("status")

        response = ad_group_ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation])
        return {"resource_name": response.results[0].resource_name, "new_status": status.upper()}
