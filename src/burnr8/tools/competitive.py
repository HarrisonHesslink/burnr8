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
    def get_competitive_metrics(
        date_range: Annotated[
            str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, LAST_MONTH, etc.")
        ] = "LAST_30_DAYS",
        campaign_id: Annotated[str | None, Field(description="Filter to a specific campaign ID")] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get impression share and competitive positioning metrics for campaigns.

        Shows how often your ads appear vs. the total eligible impressions,
        and why you're losing impressions (budget vs. rank). Available to ALL accounts.

        Key metrics:
        - search_impression_share: % of impressions you received out of total eligible
        - search_top_impression_share: % of impressions shown above organic results
        - search_abs_top_impression_share: % of impressions shown as the very first ad
        - search_budget_lost_impression_share: % of impressions lost due to budget
        - search_rank_lost_impression_share: % of impressions lost due to ad rank (QS + bid)
        - search_exact_match_impression_share: impression share for exact match queries
        """
        customer_id, err = require_customer_id(customer_id)
        if err:
            return err
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
                metrics.cost_micros,
                metrics.conversions,
                metrics.search_impression_share,
                metrics.search_top_impression_share,
                metrics.search_absolute_top_impression_share,
                metrics.search_budget_lost_impression_share,
                metrics.search_rank_lost_impression_share,
                metrics.search_exact_match_impression_share
            FROM campaign
            WHERE campaign.status != 'REMOVED'
                AND segments.date DURING {date_range.upper()}
        """
        if campaign_id:
            query += f" AND campaign.id = {campaign_id}"
        query += " ORDER BY metrics.cost_micros DESC"

        rows = run_gaql(client, customer_id, query)
        results = []
        total_spend = 0
        for row in rows:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost = micros_to_dollars(int(m.get("cost_micros", 0)))
            total_spend += cost

            is_val = m.get("search_impression_share")
            top_is = m.get("search_top_impression_share")
            abs_top_is = m.get("search_absolute_top_impression_share")
            budget_lost = m.get("search_budget_lost_impression_share")
            rank_lost = m.get("search_rank_lost_impression_share")
            exact_is = m.get("search_exact_match_impression_share")

            results.append(
                {
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "status": c.get("status"),
                    "cost_dollars": round(cost, 2),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "conversions": round(float(m.get("conversions", 0)), 1),
                    "impression_share": _fmt_share(is_val),
                    "top_impression_share": _fmt_share(top_is),
                    "abs_top_impression_share": _fmt_share(abs_top_is),
                    "budget_lost_impression_share": _fmt_share(budget_lost),
                    "rank_lost_impression_share": _fmt_share(rank_lost),
                    "exact_match_impression_share": _fmt_share(exact_is),
                }
            )

        report = save_report(results, "competitive_metrics")
        if not results:
            return report

        # Build opportunity analysis
        opportunities = []
        for r in results:
            if r["status"] != "ENABLED":
                continue
            budget_lost_share = r["budget_lost_impression_share"]
            rank_lost_share = r["rank_lost_impression_share"]
            if budget_lost_share is not None and budget_lost_share > 0.10:
                opportunities.append(
                    {
                        "campaign": r["campaign_name"],
                        "issue": "budget_limited",
                        "lost_share": round(budget_lost_share, 3),
                        "action": "Increase daily budget or reallocate from lower-performing campaigns",
                    }
                )
            if rank_lost_share is not None and rank_lost_share > 0.20:
                opportunities.append(
                    {
                        "campaign": r["campaign_name"],
                        "issue": "rank_limited",
                        "lost_share": round(rank_lost_share, 3),
                        "action": "Improve Quality Score (ad relevance, landing page) or increase bids",
                    }
                )

        report["summary"] = {
            "date_range": date_range.upper(),
            "campaigns_analyzed": len(results),
            "total_spend": round(total_spend, 2),
            "opportunities": opportunities,
        }
        return report

    @mcp.tool
    @handle_google_ads_errors
    def get_auction_insights(
        campaign_id: Annotated[str, Field(description="Campaign ID to get auction insights for")],
        date_range: Annotated[
            str, Field(description="Date range: LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, etc.")
        ] = "LAST_30_DAYS",
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get auction insights showing competitor domains and how you compare.

        Shows which competitors appear alongside your ads, their impression share,
        overlap rate, and position metrics. Requires campaign_id.

        NOTE: Auction insight metrics require Google API allowlisting. If your account
        doesn't have access, this tool returns an error with a suggestion to use
        get_competitive_metrics instead (which works for all accounts).
        """
        customer_id, err = require_customer_id(customer_id)
        if err:
            return err
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                segments.auction_insight_domain,
                metrics.auction_insight_search_impression_share,
                metrics.auction_insight_search_overlap_rate,
                metrics.auction_insight_search_outranking_share,
                metrics.auction_insight_search_position_above_rate,
                metrics.auction_insight_search_top_impression_percentage,
                metrics.auction_insight_search_absolute_top_impression_percentage
            FROM campaign
            WHERE campaign.id = {campaign_id}
                AND segments.date DURING {date_range.upper()}
            ORDER BY metrics.auction_insight_search_impression_share DESC
        """

        try:
            rows = run_gaql(client, customer_id, query)
        except Exception as e:
            from google.ads.googleads.errors import GoogleAdsException

            if not isinstance(e, GoogleAdsException):
                raise
            error_codes = [str(err.error_code) for err in e.failure.errors]
            if any(
                "NOT_PERMITTED" in code or "AUTHORIZATION_ERROR" in code or "UNRECOGNIZED_FIELD" in code
                for code in error_codes
            ):
                return {
                    "error": True,
                    "message": "Auction insight metrics require Google API allowlisting (currently closed to new accounts). "
                    "Use get_competitive_metrics instead — it provides impression share data available to all accounts.",
                    "fallback_tool": "get_competitive_metrics",
                }
            raise

        results = []
        for row in rows:
            c = row.get("campaign", {})
            seg = row.get("segments", {})
            m = row.get("metrics", {})
            results.append(
                {
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "competitor_domain": seg.get("auction_insight_domain"),
                    "impression_share": _fmt_share(m.get("auction_insight_search_impression_share")),
                    "overlap_rate": _fmt_share(m.get("auction_insight_search_overlap_rate")),
                    "outranking_share": _fmt_share(m.get("auction_insight_search_outranking_share")),
                    "position_above_rate": _fmt_share(m.get("auction_insight_search_position_above_rate")),
                    "top_impression_pct": _fmt_share(m.get("auction_insight_search_top_impression_percentage")),
                    "abs_top_impression_pct": _fmt_share(
                        m.get("auction_insight_search_absolute_top_impression_percentage")
                    ),
                }
            )

        report = save_report(results, "auction_insights")
        if not results:
            return report
        report["summary"] = {
            "date_range": date_range.upper(),
            "campaign_id": campaign_id,
            "competitors_found": len(results),
        }
        return report


def _fmt_share(value) -> float | None:
    """Format impression share values — API returns as float (0.0-1.0) or None."""
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (ValueError, TypeError):
        return None
