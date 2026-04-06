from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_date_range, validate_id
from burnr8.reports import save_report
from burnr8.session import resolve_customer_id


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def run_gaql_query(
        query: Annotated[str, Field(description="GAQL query to execute")],
        limit: Annotated[int, Field(description="Max rows to return (0 = no limit)")] = 100,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Execute a raw GAQL query. Saves full results to CSV. WARNING: limit=0 fetches all rows — use with caution on large accounts."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        rows = run_gaql(client, customer_id, query, limit=limit)
        return save_report(rows, "gaql_query")

    @mcp.tool
    @handle_google_ads_errors
    def get_campaign_performance(
        date_range: Annotated[
            str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, LAST_MONTH, etc.")
        ] = "LAST_30_DAYS",
        campaign_id: Annotated[str | None, Field(description="Filter to a specific campaign ID")] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get campaign performance metrics. Saves full report to CSV, returns summary + top rows."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.cost_per_conversion
            FROM campaign
            WHERE segments.date DURING {date_range.upper()}
        """
        if campaign_id:
            query += f" AND campaign.id = {campaign_id}"
        query += " ORDER BY metrics.cost_micros DESC"

        rows = run_gaql(client, customer_id, query)
        results = []
        total_spend = 0
        total_conversions = 0
        for row in rows:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost = int(m.get("cost_micros", 0)) / 1_000_000
            conv = float(m.get("conversions", 0))
            total_spend += cost
            total_conversions += conv
            results.append(
                {
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "status": c.get("status"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "ctr": round(float(m.get("ctr", 0)), 4),
                    "avg_cpc_dollars": round(int(m.get("average_cpc", 0)) / 1_000_000, 2),
                    "cost_dollars": round(cost, 2),
                    "conversions": round(conv, 1),
                    "conversions_value": round(float(m.get("conversions_value", 0)), 2),
                    "cost_per_conversion": round(int(m.get("cost_per_conversion", 0)) / 1_000_000, 2),
                }
            )

        report = save_report(results, "campaign_performance")
        report["summary"] = {
            "date_range": date_range.upper(),
            "total_spend": round(total_spend, 2),
            "total_conversions": round(total_conversions, 1),
            "avg_cpa": round(total_spend / total_conversions, 2) if total_conversions > 0 else None,
        }
        return report

    @mcp.tool
    @handle_google_ads_errors
    def get_ad_group_performance(
        campaign_id: Annotated[str | None, Field(description="Filter to a specific campaign ID")] = None,
        date_range: Annotated[str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get ad group level performance metrics. Saves full report to CSV, returns summary + top rows."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = f"""
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_micros,
                metrics.conversions
            FROM ad_group
            WHERE segments.date DURING {date_range.upper()}
        """
        if campaign_id:
            query += f" AND campaign.id = {campaign_id}"
        query += " ORDER BY metrics.cost_micros DESC"

        rows = run_gaql(client, customer_id, query)
        results = []
        total_spend = 0
        for row in rows:
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost = round(int(m.get("cost_micros", 0)) / 1_000_000, 2)
            total_spend += cost
            results.append(
                {
                    "ad_group_id": ag.get("id"),
                    "ad_group_name": ag.get("name"),
                    "status": ag.get("status"),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "ctr": round(float(m.get("ctr", 0)), 4),
                    "avg_cpc_dollars": round(int(m.get("average_cpc", 0)) / 1_000_000, 2),
                    "cost_dollars": cost,
                    "conversions": round(float(m.get("conversions", 0)), 1),
                }
            )

        report = save_report(results, "ad_group_performance")
        report["summary"] = {
            "date_range": date_range.upper(),
            "total_spend": round(total_spend, 2),
            "ad_groups_count": len(results),
        }
        return report

    @mcp.tool
    @handle_google_ads_errors
    def get_keyword_performance(
        campaign_id: Annotated[str | None, Field(description="Filter to a specific campaign ID")] = None,
        date_range: Annotated[str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get keyword spending performance — cost, clicks, CTR, CPC, conversions over a date range. Filter by campaign."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.quality_info.quality_score,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_micros,
                metrics.conversions
            FROM keyword_view
            WHERE segments.date DURING {date_range.upper()}
        """
        if campaign_id:
            query += f" AND campaign.id = {campaign_id}"
        query += " ORDER BY metrics.cost_micros DESC"

        rows = run_gaql(client, customer_id, query)
        results = []
        quality_scores = []
        for row in rows:
            cr = row.get("ad_group_criterion", {})
            kw = cr.get("keyword", {})
            qi = cr.get("quality_info", {})
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            qs = qi.get("quality_score")
            if qs is not None and int(qs) > 0:
                quality_scores.append(int(qs))
            results.append(
                {
                    "keyword": kw.get("text"),
                    "match_type": kw.get("match_type"),
                    "quality_score": qs,
                    "ad_group_id": ag.get("id"),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "ctr": round(float(m.get("ctr", 0)), 4),
                    "avg_cpc_dollars": round(int(m.get("average_cpc", 0)) / 1_000_000, 2),
                    "cost_dollars": round(int(m.get("cost_micros", 0)) / 1_000_000, 2),
                    "conversions": round(float(m.get("conversions", 0)), 1),
                }
            )

        report = save_report(results, "keyword_performance")
        report["summary"] = {
            "avg_quality_score": round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else None,
            "low_qs_count": sum(1 for qs in quality_scores if qs < 5),
            "keywords_with_qs": len(quality_scores),
        }
        return report

    @mcp.tool
    @handle_google_ads_errors
    def get_search_terms_report(
        campaign_id: Annotated[str | None, Field(description="Filter to a specific campaign ID")] = None,
        date_range: Annotated[str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get search terms that triggered your ads, sorted by spend (highest first). Saves full report to CSV, returns summary + top spenders.

        Note: Top rows returned inline may contain actual user search queries,
        which can include personally identifiable information (PII). Handle with care."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = f"""
            SELECT
                search_term_view.search_term,
                search_term_view.status,
                campaign.id,
                campaign.name,
                ad_group.id,
                ad_group.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM search_term_view
            WHERE segments.date DURING {date_range.upper()}
        """
        if campaign_id:
            query += f" AND campaign.id = {campaign_id}"
        query += " ORDER BY metrics.cost_micros DESC"

        rows = run_gaql(client, customer_id, query)
        results = []
        total_spend = 0
        zero_conv_spend = 0
        for row in rows:
            st = row.get("search_term_view", {})
            c = row.get("campaign", {})
            ag = row.get("ad_group", {})
            m = row.get("metrics", {})
            cost = int(m.get("cost_micros", 0)) / 1_000_000
            conv = float(m.get("conversions", 0))
            total_spend += cost
            if conv == 0 and cost > 0:
                zero_conv_spend += cost
            results.append(
                {
                    "search_term": st.get("search_term"),
                    "status": st.get("status"),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "ad_group_id": ag.get("id"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost_dollars": round(cost, 2),
                    "conversions": round(conv, 1),
                }
            )

        report = save_report(results, "search_terms")
        report["summary"] = {
            "date_range": date_range.upper(),
            "unique_terms": len(results),
            "total_spend": round(total_spend, 2),
            "zero_conversion_spend": round(zero_conv_spend, 2),
            "wasted_pct": round(zero_conv_spend / total_spend * 100, 1) if total_spend > 0 else 0,
        }
        return report
