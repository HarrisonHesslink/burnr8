from typing import Annotated, Optional
from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id, validate_date_range


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def run_gaql_query(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        query: Annotated[str, Field(description="GAQL query to execute")],
        limit: Annotated[int, Field(description="Max rows to return (0 = no limit)")] = 100,
    ) -> list[dict]:
        """Execute a raw GAQL query. Use this for any data not covered by other tools."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        return run_gaql(client, customer_id, query, limit=limit)

    @mcp.tool
    @handle_google_ads_errors
    def get_campaign_performance(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        date_range: Annotated[str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, LAST_MONTH, etc.")] = "LAST_30_DAYS",
        campaign_id: Annotated[Optional[str], Field(description="Filter to a specific campaign ID")] = None,
    ) -> list[dict]:
        """Get campaign performance metrics: impressions, clicks, cost, conversions, CTR, CPC."""
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
        for row in rows:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            results.append({
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "status": c.get("status"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "ctr": float(m.get("ctr", 0)),
                "avg_cpc_dollars": int(m.get("average_cpc", 0)) / 1_000_000,
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
                "conversions_value": float(m.get("conversions_value", 0)),
                "cost_per_conversion": int(m.get("cost_per_conversion", 0)) / 1_000_000,
            })
        return results

    @mcp.tool
    @handle_google_ads_errors
    def get_ad_group_performance(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        campaign_id: Annotated[Optional[str], Field(description="Filter to a specific campaign ID")] = None,
        date_range: Annotated[str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
    ) -> list[dict]:
        """Get ad group level performance metrics."""
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
        for row in rows:
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            results.append({
                "ad_group_id": ag.get("id"),
                "ad_group_name": ag.get("name"),
                "status": ag.get("status"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "ctr": float(m.get("ctr", 0)),
                "avg_cpc_dollars": int(m.get("average_cpc", 0)) / 1_000_000,
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
            })
        return results

    @mcp.tool
    @handle_google_ads_errors
    def get_keyword_performance(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        campaign_id: Annotated[Optional[str], Field(description="Filter to a specific campaign ID")] = None,
        date_range: Annotated[str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
    ) -> list[dict]:
        """Get keyword level performance with quality scores."""
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
        for row in rows:
            cr = row.get("ad_group_criterion", {})
            kw = cr.get("keyword", {})
            qi = cr.get("quality_info", {})
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            results.append({
                "keyword": kw.get("text"),
                "match_type": kw.get("match_type"),
                "quality_score": qi.get("quality_score"),
                "ad_group_id": ag.get("id"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "ctr": float(m.get("ctr", 0)),
                "avg_cpc_dollars": int(m.get("average_cpc", 0)) / 1_000_000,
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
            })
        return results

    @mcp.tool
    @handle_google_ads_errors
    def get_search_terms_report(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        campaign_id: Annotated[Optional[str], Field(description="Filter to a specific campaign ID")] = None,
        date_range: Annotated[str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
    ) -> list[dict]:
        """Get search terms that triggered your ads with performance data."""
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
        query += " ORDER BY metrics.impressions DESC"

        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            st = row.get("search_term_view", {})
            c = row.get("campaign", {})
            ag = row.get("ad_group", {})
            m = row.get("metrics", {})
            results.append({
                "search_term": st.get("search_term"),
                "status": st.get("status"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "ad_group_id": ag.get("id"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
            })
        return results
