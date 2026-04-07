from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import micros_to_dollars, require_customer_id, run_gaql, validate_date_range, validate_id
from burnr8.reports import save_report


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
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
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
        segment_by_device: Annotated[
            bool, Field(description="Break down metrics by device (MOBILE, DESKTOP, TABLET)")
        ] = False,
        segment_by_day_of_week: Annotated[
            bool, Field(description="Break down metrics by day of week for dayparting analysis")
        ] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get campaign performance metrics. Saves full report to CSV, returns summary + top rows."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if segment_by_device and segment_by_day_of_week:
            return {"error": True, "message": "Only one segment at a time is supported. Choose either segment_by_device or segment_by_day_of_week."}
        client = get_client()

        segment_field = ""
        if segment_by_device:
            segment_field = "segments.device,"
        elif segment_by_day_of_week:
            segment_field = "segments.day_of_week,"

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                {segment_field}
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
            s = row.get("segments", {})
            cost = micros_to_dollars(int(m.get("cost_micros", 0)))
            conv = float(m.get("conversions", 0))
            clicks = int(m.get("clicks", 0))
            total_spend += cost
            total_conversions += conv
            entry = {
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "status": c.get("status"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": clicks,
                "ctr": round(float(m.get("ctr", 0)), 4),
                "avg_cpc_dollars": round(micros_to_dollars(int(m.get("average_cpc", 0))), 2),
                "cost_dollars": round(cost, 2),
                "conversions": round(conv, 1),
                "conversions_value": round(float(m.get("conversions_value", 0)), 2),
                "cost_per_conversion": round(micros_to_dollars(int(m.get("cost_per_conversion", 0))), 2),
                "cost_per_conversion_computed": round(cost / conv, 2) if conv > 0 else None,
                "conversion_rate": round(conv / clicks * 100, 2) if clicks > 0 else None,
                "roas": round(float(m.get("conversions_value", 0)) / cost, 2) if cost > 0 else None,
            }
            if segment_by_device:
                entry["device"] = s.get("device")
            if segment_by_day_of_week:
                entry["day_of_week"] = s.get("day_of_week")
            results.append(entry)

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
        segment_by_device: Annotated[
            bool, Field(description="Break down metrics by device (MOBILE, DESKTOP, TABLET)")
        ] = False,
        segment_by_day_of_week: Annotated[
            bool, Field(description="Break down metrics by day of week for dayparting analysis")
        ] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get ad group level performance metrics. Saves full report to CSV, returns summary + top rows."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if segment_by_device and segment_by_day_of_week:
            return {"error": True, "message": "Only one segment at a time is supported. Choose either segment_by_device or segment_by_day_of_week."}
        client = get_client()

        segment_field = ""
        if segment_by_device:
            segment_field = "segments.device,"
        elif segment_by_day_of_week:
            segment_field = "segments.day_of_week,"

        query = f"""
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                campaign.id,
                campaign.name,
                {segment_field}
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
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
            s = row.get("segments", {})
            cost = round(micros_to_dollars(int(m.get("cost_micros", 0))), 2)
            conv = round(float(m.get("conversions", 0)), 1)
            clicks = int(m.get("clicks", 0))
            conv_value = round(float(m.get("conversions_value", 0)), 2)
            total_spend += cost
            entry = {
                "ad_group_id": ag.get("id"),
                "ad_group_name": ag.get("name"),
                "status": ag.get("status"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": clicks,
                "ctr": round(float(m.get("ctr", 0)), 4),
                "avg_cpc_dollars": round(micros_to_dollars(int(m.get("average_cpc", 0))), 2),
                "cost_dollars": cost,
                "conversions": conv,
                "conversions_value": conv_value,
                "cost_per_conversion": round(cost / conv, 2) if conv > 0 else None,
                "conversion_rate": round(conv / clicks * 100, 2) if clicks > 0 else None,
                "roas": round(conv_value / cost, 2) if cost > 0 else None,
            }
            if segment_by_device:
                entry["device"] = s.get("device")
            if segment_by_day_of_week:
                entry["day_of_week"] = s.get("day_of_week")
            results.append(entry)

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
        segment_by_device: Annotated[
            bool, Field(description="Break down metrics by device (MOBILE, DESKTOP, TABLET)")
        ] = False,
        segment_by_day_of_week: Annotated[
            bool, Field(description="Break down metrics by day of week for dayparting analysis")
        ] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get keyword spending performance — cost, clicks, CTR, CPC, conversions over a date range. Filter by campaign."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if segment_by_device and segment_by_day_of_week:
            return {"error": True, "message": "Only one segment at a time is supported. Choose either segment_by_device or segment_by_day_of_week."}
        client = get_client()

        segment_field = ""
        if segment_by_device:
            segment_field = "segments.device,"
        elif segment_by_day_of_week:
            segment_field = "segments.day_of_week,"

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
                {segment_field}
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
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
            s = row.get("segments", {})
            qs = qi.get("quality_score")
            if qs is not None and int(qs) > 0:
                quality_scores.append(int(qs))
            cost = round(micros_to_dollars(int(m.get("cost_micros", 0))), 2)
            conv = round(float(m.get("conversions", 0)), 1)
            clicks = int(m.get("clicks", 0))
            conv_value = round(float(m.get("conversions_value", 0)), 2)
            entry = {
                "keyword": kw.get("text"),
                "match_type": kw.get("match_type"),
                "quality_score": qs,
                "ad_group_id": ag.get("id"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": clicks,
                "ctr": round(float(m.get("ctr", 0)), 4),
                "avg_cpc_dollars": round(micros_to_dollars(int(m.get("average_cpc", 0))), 2),
                "cost_dollars": cost,
                "conversions": conv,
                "conversions_value": conv_value,
                "cost_per_conversion": round(cost / conv, 2) if conv > 0 else None,
                "conversion_rate": round(conv / clicks * 100, 2) if clicks > 0 else None,
                "roas": round(conv_value / cost, 2) if cost > 0 else None,
            }
            if segment_by_device:
                entry["device"] = s.get("device")
            if segment_by_day_of_week:
                entry["day_of_week"] = s.get("day_of_week")
            results.append(entry)

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
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
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
                metrics.ctr,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
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
            cost = micros_to_dollars(int(m.get("cost_micros", 0)))
            conv = float(m.get("conversions", 0))
            clicks = int(m.get("clicks", 0))
            conv_value = round(float(m.get("conversions_value", 0)), 2)
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
                    "clicks": clicks,
                    "ctr": round(float(m.get("ctr", 0)), 4),
                    "cost_dollars": round(cost, 2),
                    "conversions": round(conv, 1),
                    "conversions_value": conv_value,
                    "cost_per_conversion": round(cost / conv, 2) if conv > 0 else None,
                    "conversion_rate": round(conv / clicks * 100, 2) if clicks > 0 else None,
                    "roas": round(conv_value / cost, 2) if cost > 0 else None,
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
