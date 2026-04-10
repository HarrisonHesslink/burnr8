from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import micros_to_dollars, require_customer_id, run_gaql, validate_id, validate_status
from burnr8.reports import save_report

# Maps pin position integers to ServedAssetFieldTypeEnum names
_HEADLINE_PIN_MAP = {1: "HEADLINE_1", 2: "HEADLINE_2", 3: "HEADLINE_3"}
_DESCRIPTION_PIN_MAP = {1: "DESCRIPTION_1", 2: "DESCRIPTION_2"}


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_ads(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        ad_group_id: Annotated[str | None, Field(description="Filter by ad group ID")] = None,
    ) -> dict:
        """List ads with approval status, pinning, display paths, policy topics, and performance metrics. Saves full results to CSV, returns summary + top rows."""
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
                ad_group_ad.ad.responsive_search_ad.path1,
                ad_group_ad.ad.responsive_search_ad.path2,
                ad_group_ad.ad_strength,
                ad_group_ad.status,
                ad_group_ad.policy_summary.approval_status,
                ad_group_ad.policy_summary.policy_topic_entries,
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
            structured_headlines = (
                [{"text": h.get("text", ""), "pinned": h.get("pinned_field")} for h in rsa.get("headlines", [])]
                if rsa
                else []
            )
            structured_descriptions = (
                [{"text": d.get("text", ""), "pinned": d.get("pinned_field")} for d in rsa.get("descriptions", [])]
                if rsa
                else []
            )

            # Policy topic entries
            policy_topics = [
                {"topic": e.get("topic"), "type": e.get("type")}
                for e in aga.get("policy_summary", {}).get("policy_topic_entries", [])
            ]

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
                    "headlines": structured_headlines,
                    "descriptions": structured_descriptions,
                    "path1": rsa.get("path1") if rsa else None,
                    "path2": rsa.get("path2") if rsa else None,
                    "ad_strength": aga.get("ad_strength"),
                    "status": aga.get("status"),
                    "approval_status": aga.get("policy_summary", {}).get("approval_status"),
                    "policy_topics": policy_topics,
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

        # Flatten structured fields for CSV export (pipe-joined text for backwards compat)
        csv_rows = []
        for r in results:
            csv_row = dict(r)
            csv_row["headlines"] = "|".join(h["text"] for h in r["headlines"])
            csv_row["descriptions"] = "|".join(d["text"] for d in r["descriptions"])
            csv_row["policy_topics"] = "|".join(
                f"{pt['topic']}:{pt['type']}" for pt in r.get("policy_topics", []) if pt.get("topic")
            )
            csv_rows.append(csv_row)

        report = save_report(csv_rows, "ads")
        if report.get("error"):
            return report
        # Replace flattened CSV top rows with structured data for API response
        report["top"] = results[: len(report.get("top", []))]
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
        pinned_headlines: Annotated[
            list[int | None] | None,
            Field(description="Pin positions for headlines (1-3), parallel to headlines list. None means unpinned."),
        ] = None,
        pinned_descriptions: Annotated[
            list[int | None] | None,
            Field(description="Pin positions for descriptions (1-2), parallel to descriptions list. None means unpinned."),
        ] = None,
        path1: Annotated[str | None, Field(description="First display path segment (max 15 chars)")] = None,
        path2: Annotated[str | None, Field(description="Second display path segment (max 15 chars)")] = None,
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
    ) -> dict:
        """Create a responsive search ad in an ad group. Supports optional headline/description pinning and display paths."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(ad_group_id, "ad_group_id"):
            return {"error": True, "message": err}

        # Validate pinned_headlines length and values
        if pinned_headlines is not None:
            if len(pinned_headlines) != len(headlines):
                return {
                    "error": True,
                    "message": f"pinned_headlines length ({len(pinned_headlines)}) must match headlines length ({len(headlines)}).",
                }
            for i, pin in enumerate(pinned_headlines):
                if pin is not None and pin not in _HEADLINE_PIN_MAP:
                    return {
                        "error": True,
                        "message": f"pinned_headlines[{i}] = {pin} is invalid. Must be 1, 2, 3, or null.",
                    }

        # Validate pinned_descriptions length and values
        if pinned_descriptions is not None:
            if len(pinned_descriptions) != len(descriptions):
                return {
                    "error": True,
                    "message": f"pinned_descriptions length ({len(pinned_descriptions)}) must match descriptions length ({len(descriptions)}).",
                }
            for i, pin in enumerate(pinned_descriptions):
                if pin is not None and pin not in _DESCRIPTION_PIN_MAP:
                    return {
                        "error": True,
                        "message": f"pinned_descriptions[{i}] = {pin} is invalid. Must be 1, 2, or null.",
                    }

        # Validate display paths
        if path2 is not None and path1 is None:
            return {"error": True, "message": "path2 requires path1 to also be set."}
        if path1 is not None and len(path1) > 15:
            return {"error": True, "message": f"path1 exceeds 15 characters ({len(path1)})."}
        if path2 is not None and len(path2) > 15:
            return {"error": True, "message": f"path2 exceeds 15 characters ({len(path2)})."}

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

        for i, headline_text in enumerate(headlines):
            headline = client.get_type("AdTextAsset")
            headline.text = headline_text
            if pinned_headlines is not None and (pin_pos := pinned_headlines[i]) is not None:
                enum_name = _HEADLINE_PIN_MAP[pin_pos]
                headline.pinned_field = getattr(client.enums.ServedAssetFieldTypeEnum, enum_name)
            ad.responsive_search_ad.headlines.append(headline)

        for i, desc_text in enumerate(descriptions):
            desc = client.get_type("AdTextAsset")
            desc.text = desc_text
            if pinned_descriptions is not None and (pin_pos := pinned_descriptions[i]) is not None:
                enum_name = _DESCRIPTION_PIN_MAP[pin_pos]
                desc.pinned_field = getattr(client.enums.ServedAssetFieldTypeEnum, enum_name)
            ad.responsive_search_ad.descriptions.append(desc)

        # Set display paths
        if path1 is not None:
            ad.responsive_search_ad.path1 = path1
        if path2 is not None:
            ad.responsive_search_ad.path2 = path2

        response = ad_group_ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation], validate_only=not confirm)
        if not confirm:
            return {"warning": True, "validated": True, "message": "Validation succeeded. This will create a responsive search ad. Set confirm=true to execute."}

        resource_name = response.results[0].resource_name
        new_id = resource_name.split("/")[-1]
        result = {
            "id": new_id,
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
        if pinned_headlines is not None:
            result["pinned_headlines"] = pinned_headlines
        if pinned_descriptions is not None:
            result["pinned_descriptions"] = pinned_descriptions
        if path1 is not None:
            result["path1"] = path1
        if path2 is not None:
            result["path2"] = path2
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

        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=[operation], validate_only=not confirm
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": f"Validation succeeded. This will set ad {ad_id} to {status.upper()}. Set confirm=true to execute."}

        return {"resource_name": response.results[0].resource_name, "new_status": status.upper()}
