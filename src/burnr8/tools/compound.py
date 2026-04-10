from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from google.ads.googleads.client import GoogleAdsClient

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import (
    dollars_to_micros,
    micros_to_dollars,
    require_customer_id,
    run_gaql,
    validate_cpc_bid,
    validate_daily_budget,
    validate_date_range,
    validate_target_cpa,
    validate_target_roas,
)
from burnr8.reports import save_report
from burnr8.tools.campaigns import VALID_BIDDING_STRATEGIES, _apply_bidding_strategy

# Keywords that suggest informational/free intent (for cleanup_wasted_spend)
_INFORMATIONAL_SIGNALS = [
    "free",
    "what is",
    "how to",
    "tutorial",
    "wiki",
    "definition",
    "meaning",
    "example",
    "examples",
    "reddit",
    "youtube",
    "download",
    "pdf",
    "template",
    "diy",
    "course",
    "learn",
    "training",
    "certification",
    "salary",
    "job",
    "jobs",
    "career",
    "intern",
    "volunteer",
    "cheap",
    "vs",
    "versus",
    "review",
    "reviews",
]
_SIGNAL_RE = re.compile(r'\b(?:' + '|'.join(re.escape(s) for s in _INFORMATIONAL_SIGNALS) + r')\b')


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def quick_audit(
        date_range: Annotated[
            str, Field(description="Date range: TODAY, YESTERDAY, LAST_7_DAYS, LAST_14_DAYS, LAST_30_DAYS, etc.")
        ] = "LAST_30_DAYS",
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Pull all account data and return a formatted audit report in one call. Covers campaigns, keywords, ads, negatives, conversions, and budgets."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}

        client = get_client()
        date_range_upper = date_range.upper()

        # 1. Campaign performance
        campaign_query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.bidding_strategy_type,
                campaign.tracking_url_template,
                campaign.final_url_suffix,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.ctr,
                metrics.average_cpc
            FROM campaign
            WHERE segments.date DURING {date_range_upper}
            ORDER BY metrics.cost_micros DESC
        """
        # 2. Keyword performance with quality scores
        keyword_query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group_criterion.quality_info.quality_score,
                ad_group.name,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM keyword_view
            WHERE segments.date DURING {date_range_upper}
            ORDER BY metrics.cost_micros DESC
        """

        # 3. Ad data with ad_strength
        ad_query = f"""
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.ad.final_urls,
                ad_group_ad.ad.responsive_search_ad.headlines,
                ad_group_ad.ad.responsive_search_ad.descriptions,
                ad_group_ad.ad_strength,
                ad_group_ad.status,
                ad_group_ad.policy_summary.approval_status,
                ad_group.name,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM ad_group_ad
            WHERE ad_group_ad.status != 'REMOVED'
                AND segments.date DURING {date_range_upper}
        """

        # 4. Negative keyword count
        negative_query = """
            SELECT
                campaign_criterion.criterion_id
            FROM campaign_criterion
            WHERE campaign_criterion.type = 'KEYWORD'
                AND campaign_criterion.negative = true
        """

        # 5. Conversion actions (no tag_snippets — not selectable)
        conversion_query = """
            SELECT
                conversion_action.id,
                conversion_action.name,
                conversion_action.status,
                conversion_action.type,
                conversion_action.category,
                conversion_action.counting_type
            FROM conversion_action
            ORDER BY conversion_action.name
        """

        # 6. Budget data
        budget_query = """
            SELECT
                campaign_budget.id,
                campaign_budget.name,
                campaign_budget.amount_micros,
                campaign_budget.status,
                campaign_budget.delivery_method,
                campaign_budget.explicitly_shared,
                campaign_budget.reference_count
            FROM campaign_budget
            ORDER BY campaign_budget.name
        """

        # Run all 6 queries in parallel
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_campaigns = executor.submit(run_gaql, client, customer_id, campaign_query)
            future_keywords = executor.submit(run_gaql, client, customer_id, keyword_query)
            future_ads = executor.submit(run_gaql, client, customer_id, ad_query)
            future_negatives = executor.submit(run_gaql, client, customer_id, negative_query)
            future_conversions = executor.submit(run_gaql, client, customer_id, conversion_query)
            future_budgets = executor.submit(run_gaql, client, customer_id, budget_query)

        campaign_rows = future_campaigns.result()
        keyword_rows = future_keywords.result()
        ad_rows = future_ads.result()
        negative_rows = future_negatives.result()
        conversion_rows = future_conversions.result()
        budget_rows = future_budgets.result()

        # Process campaign rows
        campaigns = []
        total_spend_micros = 0
        total_conversions = 0.0
        for row in campaign_rows:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("cost_micros", 0))
            convs = float(m.get("conversions", 0))
            total_spend_micros += cost_micros
            total_conversions += convs
            campaigns.append(
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "channel_type": c.get("advertising_channel_type"),
                    "bidding_strategy": c.get("bidding_strategy_type"),
                    "tracking_url_template": c.get("tracking_url_template"),
                    "final_url_suffix": c.get("final_url_suffix"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost_dollars": micros_to_dollars(cost_micros),
                    "conversions": convs,
                    "conversions_value": float(m.get("conversions_value", 0)),
                    "ctr": float(m.get("ctr", 0)),
                    "avg_cpc_dollars": micros_to_dollars(int(m.get("average_cpc", 0))),
                }
            )

        # Process keyword rows
        top_keywords = []
        low_quality_keywords = []
        quality_scores = []
        for row in keyword_rows:
            cr = row.get("ad_group_criterion", {})
            kw = cr.get("keyword", {})
            qi = cr.get("quality_info", {})
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            qs = qi.get("quality_score")

            entry = {
                "keyword": kw.get("text"),
                "match_type": kw.get("match_type"),
                "status": cr.get("status"),
                "quality_score": qs,
                "ad_group": ag.get("name"),
                "campaign": c.get("name"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "cost_dollars": micros_to_dollars(int(m.get("cost_micros", 0))),
                "conversions": float(m.get("conversions", 0)),
            }
            top_keywords.append(entry)

            if qs is not None and int(qs) > 0:
                quality_scores.append(int(qs))
                if int(qs) < 5:
                    low_quality_keywords.append(entry)

        # Process ad rows
        ads = []
        for row in ad_rows:
            ad = row.get("ad_group_ad", {}).get("ad", {})
            aga = row.get("ad_group_ad", {})
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})

            rsa = ad.get("responsive_search_ad", {})
            headlines = [h.get("text", "") for h in rsa.get("headlines", [])] if rsa else []
            descriptions = [d.get("text", "") for d in rsa.get("descriptions", [])] if rsa else []

            ads.append(
                {
                    "ad_id": ad.get("id"),
                    "type": ad.get("type"),
                    "final_urls": ad.get("final_urls", []),
                    "headlines": headlines,
                    "descriptions": descriptions,
                    "ad_strength": aga.get("ad_strength"),
                    "status": aga.get("status"),
                    "approval_status": aga.get("policy_summary", {}).get("approval_status"),
                    "ad_group": ag.get("name"),
                    "campaign": c.get("name"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost_dollars": micros_to_dollars(int(m.get("cost_micros", 0))),
                    "conversions": float(m.get("conversions", 0)),
                }
            )

        # Process negative keyword rows
        negative_keyword_count = len(negative_rows)

        # Process conversion rows
        conversion_actions = []
        for row in conversion_rows:
            ca = row.get("conversion_action", {})
            conversion_actions.append(
                {
                    "id": ca.get("id"),
                    "name": ca.get("name"),
                    "status": ca.get("status"),
                    "type": ca.get("type"),
                    "category": ca.get("category"),
                    "counting_type": ca.get("counting_type"),
                }
            )

        # Process budget rows
        budgets = []
        for row in budget_rows:
            b = row.get("campaign_budget", {})
            budgets.append(
                {
                    "id": b.get("id"),
                    "name": b.get("name"),
                    "amount_dollars": micros_to_dollars(int(b.get("amount_micros", 0))),
                    "status": b.get("status"),
                    "delivery_method": b.get("delivery_method"),
                    "shared": b.get("explicitly_shared"),
                    "campaigns_using": b.get("reference_count"),
                }
            )

        # Build summary
        total_spend_dollars = micros_to_dollars(total_spend_micros)
        avg_cpa = (total_spend_dollars / total_conversions) if total_conversions > 0 else None
        avg_qs = (sum(quality_scores) / len(quality_scores)) if quality_scores else None

        # Tracking URL stats
        enabled_campaigns = [c for c in campaigns if c.get("status") == "ENABLED"]
        campaigns_without_tracking = [
            c["name"] for c in enabled_campaigns if not c.get("tracking_url_template")
        ]

        # Save each section to CSV
        files = {}
        campaigns_report = save_report(campaigns, "audit-campaigns", top_n=5)
        if campaigns_report.get("error"):
            return campaigns_report
        files["campaigns"] = campaigns_report.get("file") or campaigns_report.get("url")

        keywords_report = save_report(top_keywords, "audit-keywords", top_n=5)
        if keywords_report.get("error"):
            return keywords_report
        files["keywords"] = keywords_report.get("file") or keywords_report.get("url")

        low_qs_report = save_report(low_quality_keywords, "audit-low-qs-keywords", top_n=5)
        if low_qs_report.get("error"):
            return low_qs_report
        files["low_quality_keywords"] = low_qs_report.get("file") or low_qs_report.get("url")

        # Flatten list fields in ads for CSV compatibility
        ads_csv = []
        for ad in ads:
            flat = {k: v for k, v in ad.items() if k not in ("final_urls", "headlines", "descriptions")}
            flat["final_urls"] = "|".join(ad.get("final_urls") or [])
            flat["headlines"] = "|".join(ad.get("headlines") or [])
            flat["descriptions"] = "|".join(ad.get("descriptions") or [])
            ads_csv.append(flat)
        ads_report = save_report(ads_csv, "audit-ads", top_n=5)
        if ads_report.get("error"):
            return ads_report
        files["ads"] = ads_report.get("file") or ads_report.get("url")

        conversions_report = save_report(conversion_actions, "audit-conversions", top_n=5)
        if conversions_report.get("error"):
            return conversions_report
        files["conversion_actions"] = conversions_report.get("file") or conversions_report.get("url")

        budgets_report = save_report(budgets, "audit-budgets", top_n=5)
        if budgets_report.get("error"):
            return budgets_report
        files["budgets"] = budgets_report.get("file") or budgets_report.get("url")

        return {
            "files": files,
            "summary": {
                "date_range": date_range_upper,
                "total_campaigns": len(campaigns),
                "total_keywords": len(top_keywords),
                "total_ads": len(ads),
                "total_spend_dollars": round(total_spend_dollars, 2),
                "total_conversions": round(total_conversions, 2),
                "avg_cpa_dollars": round(avg_cpa, 2) if avg_cpa is not None else None,
                "avg_quality_score": round(avg_qs, 1) if avg_qs is not None else None,
                "low_quality_keyword_count": len(low_quality_keywords),
                "negative_keyword_count": negative_keyword_count,
                "conversion_action_count": len(conversion_actions),
                "budget_count": len(budgets),
                "campaigns_without_tracking": campaigns_without_tracking or None,
            },
            "top_campaigns": campaigns_report.get("top", []),
            "top_keywords": keywords_report.get("top", []),
            "top_ads": ads_report.get("top", []),
            "top_low_quality_keywords": low_qs_report.get("top", []),
            "top_conversion_actions": conversions_report.get("top", []),
            "top_budgets": budgets_report.get("top", []),
        }

    @mcp.tool
    @handle_google_ads_errors
    def launch_campaign(
        campaign_name: Annotated[str, Field(description="Name for the new campaign")],
        daily_budget_dollars: Annotated[float, Field(description="Daily budget in dollars", gt=0)],
        keywords: Annotated[list[str], Field(description="List of keyword texts (added as Broad match)")],
        headlines: Annotated[
            list[str], Field(description="List of 3-15 headline texts for the RSA (max 30 chars each)")
        ],
        descriptions: Annotated[
            list[str], Field(description="List of 2-4 description texts for the RSA (max 90 chars each)")
        ],
        final_url: Annotated[str, Field(description="Landing page URL for the ad")],
        cpc_bid: Annotated[float, Field(description="Default CPC bid in dollars")] = 1.0,
        ad_group_name: Annotated[str, Field(description="Name for the ad group")] = "Ad Group 1",
        bidding_strategy: Annotated[
            str,
            Field(
                description="Bidding strategy: MANUAL_CPC, MANUAL_CPM, MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, TARGET_ROAS, TARGET_IMPRESSION_SHARE, TARGET_SPEND"
            ),
        ] = "MANUAL_CPC",
        target_cpa_dollars: Annotated[
            float | None, Field(description="Target CPA in dollars (for TARGET_CPA or MAXIMIZE_CONVERSIONS)")
        ] = None,
        target_roas: Annotated[
            float | None,
            Field(description="Target ROAS as a ratio, e.g. 4.0 means 400% return (for TARGET_ROAS or MAXIMIZE_CONVERSION_VALUE)"),
        ] = None,
        max_cpc_bid_ceiling_dollars: Annotated[
            float | None,
            Field(description="Max CPC bid ceiling in dollars (for MAXIMIZE_CLICKS or TARGET_IMPRESSION_SHARE)"),
        ] = None,
        negative_keywords: Annotated[
            list[str] | None,
            Field(description="Optional list of negative keyword texts to add as PHRASE match campaign-level negatives"),
        ] = None,
        location_ids: Annotated[
            list[str] | None,
            Field(description="Geo target constant IDs, e.g. ['2840'] for US"),
        ] = None,
        eu_political_ads: Annotated[
            bool, Field(description="Set to true if this campaign contains EU political advertising")
        ] = False,
        tracking_url_template: Annotated[
            str | None,
            Field(description="URL template for tracking applied at campaign level, e.g. '{lpurl}?utm_source=google'"),
        ] = None,
        final_url_suffix: Annotated[
            str | None,
            Field(description="Suffix appended to final URLs at campaign level"),
        ] = None,
        url_custom_parameters: Annotated[
            dict[str, str] | None,
            Field(description="Custom parameters for tracking URL substitution at campaign level"),
        ] = None,
        confirm: Annotated[bool, Field(description="Must be true to execute the creation.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create a complete campaign setup in one call: budget, campaign (PAUSED, SEARCH), ad group, keywords (Broad match), and a responsive search ad. Supports all bidding strategies, optional negative keywords, and location targeting."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err

        # Validate inputs
        if len(headlines) < 3 or len(headlines) > 15:
            return {"error": True, "message": f"headlines must have 3-15 items, got {len(headlines)}"}
        if len(descriptions) < 2 or len(descriptions) > 4:
            return {"error": True, "message": f"descriptions must have 2-4 items, got {len(descriptions)}"}
        if not keywords:
            return {"error": True, "message": "keywords list cannot be empty"}
        if err := validate_daily_budget(daily_budget_dollars):
            return {"error": True, "message": err}
        if err := validate_cpc_bid(cpc_bid):
            return {"error": True, "message": err}
        if target_cpa_dollars is not None and (err := validate_target_cpa(target_cpa_dollars)):
            return {"error": True, "message": err}
        if target_roas is not None and (err := validate_target_roas(target_roas)):
            return {"error": True, "message": err}

        strategy = bidding_strategy.upper()
        if strategy not in VALID_BIDDING_STRATEGIES:
            return {
                "error": True,
                "message": f"Invalid bidding_strategy '{bidding_strategy}'. Must be one of: {', '.join(sorted(VALID_BIDDING_STRATEGIES))}",
            }

        client = get_client()
        created = {"budget": None, "campaign": None, "negative_keywords": None, "locations": None, "ad_group": None, "keywords": None, "ad": None}

        if not confirm:
            return {"warning": True, "validated": False, "message": f"Client-side validation passed (no API call). This will launch a full campaign '{campaign_name}'. Set confirm=true to execute."}

        try:
            return _execute_launch(
                client,
                customer_id,
                campaign_name,
                daily_budget_dollars,
                keywords,
                headlines,
                descriptions,
                final_url,
                cpc_bid,
                ad_group_name,
                strategy,
                target_cpa_dollars,
                target_roas,
                max_cpc_bid_ceiling_dollars,
                negative_keywords,
                location_ids,
                eu_political_ads,
                tracking_url_template,
                final_url_suffix,
                url_custom_parameters,
                created,
            )
        except Exception as ex:
            # Lazy imports to avoid loading SDK at module level
            import grpc
            from google.ads.googleads.errors import GoogleAdsException

            created_before = {k: v for k, v in created.items() if v is not None}
            if isinstance(ex, GoogleAdsException):
                errors = []
                for error in ex.failure.errors:
                    err = {"message": error.message[:200], "code": str(error.error_code)}
                    if error.location and error.location.field_path_elements:
                        err["field_path"] = [el.field_name for el in error.location.field_path_elements]
                    errors.append(err)
                return {
                    "error": True,
                    "partial_failure": True,
                    "message": errors[0]["message"] if errors else "Unknown Google Ads API error",
                    "request_id": ex.request_id,
                    "status": ex.error.code().name,
                    "errors": errors,
                    "created_before_failure": created_before,
                }
            if isinstance(ex, grpc.RpcError):
                return {
                    "error": True,
                    "partial_failure": True,
                    "message": f"RPC error: {ex.code().name}"[:200],
                    "created_before_failure": created_before,
                }
            # Programming errors should crash, not be silenced as "partial failures"
            raise

    @mcp.tool
    @handle_google_ads_errors
    def cleanup_wasted_spend(
        date_range: Annotated[
            str, Field(description="Date range: TODAY, YESTERDAY, LAST_7_DAYS, LAST_14_DAYS, LAST_30_DAYS, etc.")
        ] = "LAST_30_DAYS",
        min_spend: Annotated[float, Field(description="Minimum spend in dollars to flag a keyword as wasted")] = 10.0,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Analyze keywords with spend but zero conversions and return actionable recommendations for reducing wasted ad spend."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_date_range(date_range):
            return {"error": True, "message": err}

        client = get_client()
        date_range_upper = date_range.upper()
        min_spend_micros = dollars_to_micros(min_spend)

        query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.impressions
            FROM keyword_view
            WHERE segments.date DURING {date_range_upper}
            ORDER BY metrics.cost_micros DESC
        """
        rows = run_gaql(client, customer_id, query)

        wasted_keywords = []
        total_wasted_micros = 0
        suggested_negatives = []

        for row in rows:
            cr = row.get("ad_group_criterion", {})
            kw = cr.get("keyword", {})
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})

            cost_micros = int(m.get("cost_micros", 0))
            conversions = float(m.get("conversions", 0))

            if cost_micros == 0:
                continue
            if conversions > 0:
                continue
            if cost_micros < min_spend_micros:
                continue

            keyword_text = kw.get("text", "")
            cost_dollars = micros_to_dollars(cost_micros)
            total_wasted_micros += cost_micros

            entry = {
                "criterion_id": cr.get("criterion_id"),
                "keyword": keyword_text,
                "match_type": kw.get("match_type"),
                "status": cr.get("status"),
                "spend_dollars": round(cost_dollars, 2),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "ad_group_id": ag.get("id"),
                "ad_group_name": ag.get("name"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
            }
            wasted_keywords.append(entry)

            keyword_lower = keyword_text.lower()
            match = _SIGNAL_RE.search(keyword_lower)
            if match:
                suggested_negatives.append(
                    {
                        "keyword": keyword_text,
                        "reason": f"Contains '{match.group()}' — likely informational/non-commercial intent",
                        "spend_dollars": round(cost_dollars, 2),
                    }
                )

        total_wasted_dollars = round(micros_to_dollars(total_wasted_micros), 2)

        # Save full wasted keywords list to CSV
        wasted_report = save_report(wasted_keywords, "wasted-keywords", top_n=10)
        if wasted_report.get("error"):
            return wasted_report

        return {
            "date_range": date_range_upper,
            "min_spend_threshold_dollars": min_spend,
            "total_wasted_dollars": total_wasted_dollars,
            "wasted_keyword_count": len(wasted_keywords),
            "top_wasted_keywords": wasted_report.get("top", []),
            "file": wasted_report.get("file"),
            "suggested_negatives": suggested_negatives,
            "suggested_negative_count": len(suggested_negatives),
        }


def _execute_launch(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_name: str,
    daily_budget_dollars: float,
    keywords: list[str],
    headlines: list[str],
    descriptions: list[str],
    final_url: str,
    cpc_bid: float,
    ad_group_name: str,
    bidding_strategy: str,
    target_cpa_dollars: float | None,
    target_roas: float | None,
    max_cpc_bid_ceiling_dollars: float | None,
    negative_keywords: list[str] | None,
    location_ids: list[str] | None,
    eu_political_ads: bool,
    tracking_url_template: str | None,
    final_url_suffix: str | None,
    url_custom_parameters: dict[str, str] | None,
    created: dict,
) -> dict:
    # 1. Create budget
    budget_service = client.get_service("CampaignBudgetService")
    budget_op = client.get_type("CampaignBudgetOperation")
    budget = budget_op.create
    budget.name = f"{campaign_name} Budget"
    budget.amount_micros = dollars_to_micros(daily_budget_dollars)
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared = False

    budget_response = budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[budget_op])
    budget_resource_name = budget_response.results[0].resource_name
    budget_id = budget_resource_name.split("/")[-1]
    created["budget"] = budget_resource_name

    # 2. Create campaign (PAUSED, SEARCH)
    campaign_service = client.get_service("CampaignService")
    campaign_op = client.get_type("CampaignOperation")
    campaign = campaign_op.create
    campaign.name = campaign_name
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    campaign.campaign_budget = budget_resource_name
    campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    _apply_bidding_strategy(
        client, campaign, bidding_strategy,
        target_cpa_dollars=target_cpa_dollars,
        target_roas=target_roas,
        max_cpc_bid_ceiling_dollars=max_cpc_bid_ceiling_dollars,
    )
    campaign.network_settings.target_google_search = True
    campaign.network_settings.target_search_network = True
    campaign.network_settings.target_content_network = False

    if eu_political_ads:
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.CONTAINS_EU_POLITICAL_ADVERTISING
        )
    else:
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )

    if tracking_url_template is not None:
        campaign.tracking_url_template = tracking_url_template
    if final_url_suffix is not None:
        campaign.final_url_suffix = final_url_suffix
    if url_custom_parameters is not None:
        for key, value in url_custom_parameters.items():
            param = client.get_type("CustomParameter")
            param.key = key
            param.value = value
            campaign.url_custom_parameters.append(param)

    campaign_response = campaign_service.mutate_campaigns(customer_id=customer_id, operations=[campaign_op])
    campaign_resource_name = campaign_response.results[0].resource_name
    campaign_id = campaign_resource_name.split("/")[-1]
    created["campaign"] = campaign_resource_name

    # 2b. Add negative keywords (PHRASE match, campaign-level)
    neg_response = None
    if negative_keywords:
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        neg_ops = []
        for neg_text in negative_keywords:
            neg_op = client.get_type("CampaignCriterionOperation")
            criterion = neg_op.create
            criterion.campaign = campaign_resource_name
            criterion.negative = True
            criterion.keyword.text = neg_text
            criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
            neg_ops.append(neg_op)
        neg_response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id, operations=neg_ops
        )
        created["negative_keywords"] = [r.resource_name for r in neg_response.results]

    # 2c. Add location targets
    loc_response = None
    if location_ids:
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        loc_ops = []
        for loc_id in location_ids:
            loc_op = client.get_type("CampaignCriterionOperation")
            criterion = loc_op.create
            criterion.campaign = campaign_resource_name
            criterion.location.geo_target_constant = f"geoTargetConstants/{loc_id}"
            loc_ops.append(loc_op)
        loc_response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id, operations=loc_ops
        )
        created["locations"] = [r.resource_name for r in loc_response.results]

    # 3. Create ad group
    ad_group_service = client.get_service("AdGroupService")
    ad_group_op = client.get_type("AdGroupOperation")
    ad_group = ad_group_op.create
    ad_group.name = ad_group_name
    ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
    ad_group.campaign = campaign_resource_name
    ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    ad_group.cpc_bid_micros = dollars_to_micros(cpc_bid)

    ad_group_response = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[ad_group_op])
    ad_group_resource_name = ad_group_response.results[0].resource_name
    ad_group_id = ad_group_resource_name.split("/")[-1]
    created["ad_group"] = ad_group_resource_name

    # 4. Add keywords (Broad match)
    ad_group_criterion_service = client.get_service("AdGroupCriterionService")
    keyword_ops = []
    for kw_text in keywords:
        kw_op = client.get_type("AdGroupCriterionOperation")
        criterion = kw_op.create
        criterion.ad_group = ad_group_resource_name
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = kw_text
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.BROAD
        keyword_ops.append(kw_op)

    keyword_response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=keyword_ops
    )
    created["keywords"] = [r.resource_name for r in keyword_response.results]

    # 5. Create responsive search ad
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_op = client.get_type("AdGroupAdOperation")
    ad_group_ad = ad_op.create
    ad_group_ad.ad_group = ad_group_resource_name
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

    ad_response = ad_group_ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[ad_op])
    ad_resource_name = ad_response.results[0].resource_name
    created["ad"] = ad_resource_name

    result = {
        "status": "PAUSED",
        "budget": {
            "id": budget_id,
            "resource_name": budget_resource_name,
            "daily_dollars": daily_budget_dollars,
        },
        "campaign": {
            "id": campaign_id,
            "resource_name": campaign_resource_name,
            "name": campaign_name,
            "bidding_strategy": bidding_strategy,
            **({"tracking_url_template": tracking_url_template} if tracking_url_template is not None else {}),
            **({"final_url_suffix": final_url_suffix} if final_url_suffix is not None else {}),
            **({"url_custom_parameters": url_custom_parameters} if url_custom_parameters is not None else {}),
        },
        "ad_group": {
            "id": ad_group_id,
            "resource_name": ad_group_resource_name,
            "name": ad_group_name,
            "cpc_bid_dollars": cpc_bid,
        },
        "keywords": {
            "added": len(keyword_response.results),
            "resource_names": [r.resource_name for r in keyword_response.results],
            "match_type": "BROAD",
        },
        "ad": {
            "resource_name": ad_resource_name,
            "headlines_count": len(headlines),
            "descriptions_count": len(descriptions),
            "final_url": final_url,
        },
    }

    if neg_response is not None:
        result["negative_keywords"] = {
            "added": len(neg_response.results),
            "match_type": "PHRASE",
        }

    if loc_response is not None:
        result["locations"] = {
            "added": len(loc_response.results),
            "location_ids": location_ids,
        }

    return result
