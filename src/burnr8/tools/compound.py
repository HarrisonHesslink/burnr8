from typing import Annotated

from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import dollars_to_micros, run_gaql, validate_date_range, validate_id

# Keywords that suggest informational/free intent (for cleanup_wasted_spend)
_INFORMATIONAL_SIGNALS = [
    "free", "what is", "how to", "tutorial", "wiki", "definition",
    "meaning", "example", "examples", "reddit", "youtube", "download",
    "pdf", "template", "diy", "course", "learn", "training",
    "certification", "salary", "job", "jobs", "career", "intern",
    "volunteer", "cheap", "vs", "versus", "review", "reviews",
]


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def quick_audit(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        date_range: Annotated[str, Field(description="Date range: TODAY, YESTERDAY, LAST_7_DAYS, LAST_14_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
    ) -> dict:
        """Pull all account data and return a formatted audit report in one call. Covers campaigns, keywords, ads, negatives, conversions, and budgets."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
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
        campaign_rows = run_gaql(client, customer_id, campaign_query)

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
            campaigns.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "channel_type": c.get("advertising_channel_type"),
                "bidding_strategy": c.get("bidding_strategy_type"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "cost_dollars": cost_micros / 1_000_000,
                "conversions": convs,
                "conversions_value": float(m.get("conversions_value", 0)),
                "ctr": float(m.get("ctr", 0)),
                "avg_cpc_dollars": int(m.get("average_cpc", 0)) / 1_000_000,
            })

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
        keyword_rows = run_gaql(client, customer_id, keyword_query)

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
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
            }
            top_keywords.append(entry)

            if qs is not None and int(qs) > 0:
                quality_scores.append(int(qs))
                if int(qs) < 5:
                    low_quality_keywords.append(entry)

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
        ad_rows = run_gaql(client, customer_id, ad_query)

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

            ads.append({
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
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
            })

        # 4. Negative keyword count
        negative_query = """
            SELECT
                campaign_criterion.criterion_id
            FROM campaign_criterion
            WHERE campaign_criterion.type = 'KEYWORD'
                AND campaign_criterion.negative = true
        """
        negative_rows = run_gaql(client, customer_id, negative_query)
        negative_keyword_count = len(negative_rows)

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
        conversion_rows = run_gaql(client, customer_id, conversion_query)

        conversion_actions = []
        for row in conversion_rows:
            ca = row.get("conversion_action", {})
            conversion_actions.append({
                "id": ca.get("id"),
                "name": ca.get("name"),
                "status": ca.get("status"),
                "type": ca.get("type"),
                "category": ca.get("category"),
                "counting_type": ca.get("counting_type"),
            })

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
        budget_rows = run_gaql(client, customer_id, budget_query)

        budgets = []
        for row in budget_rows:
            b = row.get("campaign_budget", {})
            budgets.append({
                "id": b.get("id"),
                "name": b.get("name"),
                "amount_dollars": int(b.get("amount_micros", 0)) / 1_000_000,
                "status": b.get("status"),
                "delivery_method": b.get("delivery_method"),
                "shared": b.get("explicitly_shared"),
                "campaigns_using": b.get("reference_count"),
            })

        # Build summary
        total_spend_dollars = total_spend_micros / 1_000_000
        avg_cpa = (total_spend_dollars / total_conversions) if total_conversions > 0 else None
        avg_qs = (sum(quality_scores) / len(quality_scores)) if quality_scores else None

        return {
            "campaigns": campaigns,
            "top_keywords": top_keywords,
            "low_quality_keywords": low_quality_keywords,
            "ads": ads,
            "negative_keyword_count": negative_keyword_count,
            "conversion_actions": conversion_actions,
            "budgets": budgets,
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
            },
        }

    @mcp.tool
    @handle_google_ads_errors
    def launch_campaign(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        campaign_name: Annotated[str, Field(description="Name for the new campaign")],
        daily_budget_dollars: Annotated[float, Field(description="Daily budget in dollars", gt=0)],
        keywords: Annotated[list[str], Field(description="List of keyword texts (added as Broad match)")],
        headlines: Annotated[list[str], Field(description="List of 3-15 headline texts for the RSA (max 30 chars each)")],
        descriptions: Annotated[list[str], Field(description="List of 2-4 description texts for the RSA (max 90 chars each)")],
        final_url: Annotated[str, Field(description="Landing page URL for the ad")],
        cpc_bid: Annotated[float, Field(description="Default CPC bid in dollars")] = 1.0,
        ad_group_name: Annotated[str, Field(description="Name for the ad group")] = "Ad Group 1",
        eu_political_ads: Annotated[bool, Field(description="Set to true if this campaign contains EU political advertising")] = False,
    ) -> dict:
        """Create a complete campaign setup in one call: budget, campaign (PAUSED, SEARCH, MANUAL_CPC), ad group, keywords (Broad match), and a responsive search ad."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}

        # Validate inputs
        if len(headlines) < 3 or len(headlines) > 15:
            return {"error": True, "message": f"headlines must have 3-15 items, got {len(headlines)}"}
        if len(descriptions) < 2 or len(descriptions) > 4:
            return {"error": True, "message": f"descriptions must have 2-4 items, got {len(descriptions)}"}
        if not keywords:
            return {"error": True, "message": "keywords list cannot be empty"}

        client = get_client()
        created = {"budget": None, "campaign": None, "ad_group": None, "keywords": None, "ad": None}

        try:
            return _execute_launch(client, customer_id, campaign_name, daily_budget_dollars,
                                   keywords, headlines, descriptions, final_url, cpc_bid, ad_group_name,
                                   eu_political_ads, created)
        except Exception as ex:
            return {
                "error": True,
                "partial_failure": True,
                "message": str(ex),
                "created_before_failure": {k: v for k, v in created.items() if v is not None},
            }

    @mcp.tool
    @handle_google_ads_errors
    def cleanup_wasted_spend(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        date_range: Annotated[str, Field(description="Date range: TODAY, YESTERDAY, LAST_7_DAYS, LAST_14_DAYS, LAST_30_DAYS, etc.")] = "LAST_30_DAYS",
        min_spend: Annotated[float, Field(description="Minimum spend in dollars to flag a keyword as wasted")] = 10.0,
    ) -> dict:
        """Analyze keywords with spend but zero conversions and return actionable recommendations for reducing wasted ad spend."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
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
            cost_dollars = cost_micros / 1_000_000
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
            for signal in _INFORMATIONAL_SIGNALS:
                if signal in keyword_lower:
                    suggested_negatives.append({
                        "keyword": keyword_text,
                        "reason": f"Contains '{signal}' — likely informational/non-commercial intent",
                        "spend_dollars": round(cost_dollars, 2),
                    })
                    break

        total_wasted_dollars = round(total_wasted_micros / 1_000_000, 2)

        return {
            "date_range": date_range_upper,
            "min_spend_threshold_dollars": min_spend,
            "wasted_keywords": wasted_keywords,
            "total_wasted_dollars": total_wasted_dollars,
            "wasted_keyword_count": len(wasted_keywords),
            "suggested_negatives": suggested_negatives,
            "suggested_negative_count": len(suggested_negatives),
        }


def _execute_launch(client, customer_id, campaign_name, daily_budget_dollars,
                    keywords, headlines, descriptions, final_url, cpc_bid, ad_group_name,
                    eu_political_ads, created):
    # 1. Create budget
    budget_service = client.get_service("CampaignBudgetService")
    budget_op = client.get_type("CampaignBudgetOperation")
    budget = budget_op.create
    budget.name = f"{campaign_name} Budget"
    budget.amount_micros = dollars_to_micros(daily_budget_dollars)
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared = False

    budget_response = budget_service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[budget_op]
    )
    budget_resource_name = budget_response.results[0].resource_name
    budget_id = budget_resource_name.split("/")[-1]
    created["budget"] = budget_resource_name

    # 2. Create campaign (PAUSED, SEARCH, MANUAL_CPC)
    campaign_service = client.get_service("CampaignService")
    campaign_op = client.get_type("CampaignOperation")
    campaign = campaign_op.create
    campaign.name = campaign_name
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    campaign.campaign_budget = budget_resource_name
    campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    campaign.manual_cpc = client.get_type("ManualCpc")
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

    campaign_response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[campaign_op]
    )
    campaign_resource_name = campaign_response.results[0].resource_name
    campaign_id = campaign_resource_name.split("/")[-1]
    created["campaign"] = campaign_resource_name

    # 3. Create ad group
    ad_group_service = client.get_service("AdGroupService")
    ad_group_op = client.get_type("AdGroupOperation")
    ad_group = ad_group_op.create
    ad_group.name = ad_group_name
    ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
    ad_group.campaign = campaign_resource_name
    ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    ad_group.cpc_bid_micros = dollars_to_micros(cpc_bid)

    ad_group_response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ad_group_op]
    )
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

    ad_response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[ad_op]
    )
    ad_resource_name = ad_response.results[0].resource_name
    created["ad"] = ad_resource_name

    return {
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
