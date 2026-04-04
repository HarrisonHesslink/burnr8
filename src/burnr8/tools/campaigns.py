from typing import Annotated, Optional
from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id, validate_status, dollars_to_micros

VALID_BIDDING_STRATEGIES = {
    "MANUAL_CPC", "MANUAL_CPM", "MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS",
    "TARGET_IMPRESSION_SHARE", "TARGET_SPEND",
}


def _apply_bidding_strategy(client, campaign, strategy, target_cpa_dollars=None, target_roas=None,
                            max_cpc_bid_ceiling_dollars=None, target_impression_share_location="TOP_OF_PAGE",
                            target_impression_share_fraction=None):
    """Apply a bidding strategy to a campaign proto. Returns list of field mask paths."""
    paths = []
    if strategy == "MANUAL_CPC":
        campaign.manual_cpc = client.get_type("ManualCpc")
        paths.append("manual_cpc")
    elif strategy == "MANUAL_CPM":
        campaign.manual_cpm = client.get_type("ManualCpm")
        paths.append("manual_cpm")
    elif strategy == "MAXIMIZE_CLICKS":
        # In API v23+, Maximize Clicks is implemented via target_spend
        ts = client.get_type("TargetSpend")
        if max_cpc_bid_ceiling_dollars is not None:
            ts.cpc_bid_ceiling_micros = dollars_to_micros(max_cpc_bid_ceiling_dollars)
            paths.append("target_spend.cpc_bid_ceiling_micros")
        else:
            paths.append("target_spend")
        campaign.target_spend = ts
    elif strategy == "MAXIMIZE_CONVERSIONS":
        mc = client.get_type("MaximizeConversions")
        if target_cpa_dollars is not None:
            mc.target_cpa_micros = dollars_to_micros(target_cpa_dollars)
            paths.append("maximize_conversions.target_cpa_micros")
        else:
            paths.append("maximize_conversions")
        campaign.maximize_conversions = mc
    elif strategy == "MAXIMIZE_CONVERSION_VALUE":
        mcv = client.get_type("MaximizeConversionValue")
        if target_roas is not None:
            mcv.target_roas = target_roas
            paths.append("maximize_conversion_value.target_roas")
        else:
            paths.append("maximize_conversion_value")
        campaign.maximize_conversion_value = mcv
    elif strategy == "TARGET_CPA":
        tcpa = client.get_type("TargetCpa")
        if target_cpa_dollars is not None:
            tcpa.target_cpa_micros = dollars_to_micros(target_cpa_dollars)
        if max_cpc_bid_ceiling_dollars is not None:
            tcpa.cpc_bid_ceiling_micros = dollars_to_micros(max_cpc_bid_ceiling_dollars)
            paths.append("target_cpa.cpc_bid_ceiling_micros")
        # Always use subfield path
        paths.append("target_cpa.target_cpa_micros")
        campaign.target_cpa = tcpa
    elif strategy == "TARGET_ROAS":
        troas = client.get_type("TargetRoas")
        if target_roas is not None:
            troas.target_roas = target_roas
        if max_cpc_bid_ceiling_dollars is not None:
            troas.cpc_bid_ceiling_micros = dollars_to_micros(max_cpc_bid_ceiling_dollars)
            paths.append("target_roas.cpc_bid_ceiling_micros")
        # Always use subfield path
        paths.append("target_roas.target_roas")
        campaign.target_roas = troas
    elif strategy == "TARGET_IMPRESSION_SHARE":
        tis = client.get_type("TargetImpressionShare")
        location_map = {
            "ANYWHERE_ON_PAGE": client.enums.TargetImpressionShareLocationEnum.ANYWHERE_ON_PAGE,
            "TOP_OF_PAGE": client.enums.TargetImpressionShareLocationEnum.TOP_OF_PAGE,
            "ABSOLUTE_TOP_OF_PAGE": client.enums.TargetImpressionShareLocationEnum.ABSOLUTE_TOP_OF_PAGE,
        }
        tis.location = location_map.get(target_impression_share_location.upper(),
                                        client.enums.TargetImpressionShareLocationEnum.TOP_OF_PAGE)
        paths.append("target_impression_share.location")
        if target_impression_share_fraction is not None:
            tis.location_fraction_micros = int(target_impression_share_fraction * 1_000_000)
            paths.append("target_impression_share.location_fraction_micros")
        if max_cpc_bid_ceiling_dollars is not None:
            tis.cpc_bid_ceiling_micros = dollars_to_micros(max_cpc_bid_ceiling_dollars)
            paths.append("target_impression_share.cpc_bid_ceiling_micros")
        campaign.target_impression_share = tis
    elif strategy == "TARGET_SPEND":
        ts = client.get_type("TargetSpend")
        if max_cpc_bid_ceiling_dollars is not None:
            ts.cpc_bid_ceiling_micros = dollars_to_micros(max_cpc_bid_ceiling_dollars)
            paths.append("target_spend.cpc_bid_ceiling_micros")
        else:
            paths.append("target_spend")
        campaign.target_spend = ts
    return paths


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_campaigns(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        status: Annotated[Optional[str], Field(description="Filter by status: ENABLED, PAUSED, or REMOVED")] = None,
    ) -> list[dict]:
        """List all campaigns for a customer, optionally filtered by status."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.bidding_strategy_type,
                campaign.campaign_budget,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros
            FROM campaign
        """
        if status:
            if err := validate_status(status):
                return {"error": True, "message": err}
            query += f" WHERE campaign.status = '{status.upper()}'"
        query += " ORDER BY campaign.name"
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            results.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "channel_type": c.get("advertising_channel_type"),
                "bidding_strategy_type": c.get("bidding_strategy_type"),
                "budget": c.get("campaign_budget"),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
            })
        return results

    @mcp.tool
    @handle_google_ads_errors
    def get_campaign(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        campaign_id: Annotated[str, Field(description="Campaign ID")],
    ) -> dict:
        """Get full details for a specific campaign."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        client = get_client()
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.bidding_strategy_type,
                campaign.campaign_budget,
                campaign.start_date,
                campaign.end_date,
                campaign.network_settings.target_google_search,
                campaign.network_settings.target_search_network,
                campaign.network_settings.target_content_network,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """
        rows = run_gaql(client, customer_id, query)
        if rows:
            row = rows[0]
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            c["impressions"] = int(m.get("impressions", 0))
            c["clicks"] = int(m.get("clicks", 0))
            c["cost_dollars"] = int(m.get("cost_micros", 0)) / 1_000_000
            c["conversions"] = float(m.get("conversions", 0))
            c["conversions_value"] = float(m.get("conversions_value", 0))
            return c
        return {"error": True, "message": "Campaign not found"}

    @mcp.tool
    @handle_google_ads_errors
    def create_campaign(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        name: Annotated[str, Field(description="Campaign name")],
        budget_id: Annotated[str, Field(description="Campaign budget ID to use")],
        channel_type: Annotated[str, Field(description="Channel type: SEARCH, DISPLAY, SHOPPING, VIDEO")] = "SEARCH",
        bidding_strategy: Annotated[str, Field(description="Bidding strategy: MANUAL_CPC, MANUAL_CPM, MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, TARGET_ROAS, TARGET_IMPRESSION_SHARE, TARGET_SPEND")] = "MANUAL_CPC",
        target_cpa_dollars: Annotated[Optional[float], Field(description="Target CPA in dollars (for TARGET_CPA strategy)")] = None,
        target_roas: Annotated[Optional[float], Field(description="Target ROAS as a ratio, e.g. 4.0 means 400% return (for TARGET_ROAS strategy)")] = None,
        max_cpc_bid_ceiling_dollars: Annotated[Optional[float], Field(description="Max CPC bid ceiling in dollars (for MAXIMIZE_CLICKS or TARGET_IMPRESSION_SHARE)")] = None,
        target_impression_share_location: Annotated[str, Field(description="Where to target impressions: ANYWHERE_ON_PAGE, TOP_OF_PAGE, ABSOLUTE_TOP_OF_PAGE (for TARGET_IMPRESSION_SHARE)")] = "TOP_OF_PAGE",
        target_impression_share_fraction: Annotated[Optional[float], Field(description="Target impression share as decimal 0.0-1.0, e.g. 0.5 = 50% (for TARGET_IMPRESSION_SHARE)")] = None,
        eu_political_ads: Annotated[bool, Field(description="Set to true if this campaign contains EU political advertising. Required for EU/EEA compliance.")] = False,
    ) -> dict:
        """Create a new campaign. Always starts PAUSED for safety. Supports all Google Ads bidding strategies."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(budget_id, "budget_id"):
            return {"error": True, "message": err}

        valid_strategies = {
            "MANUAL_CPC", "MANUAL_CPM", "MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS",
            "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS",
            "TARGET_IMPRESSION_SHARE", "TARGET_SPEND",
        }
        strategy = bidding_strategy.upper()
        if strategy not in valid_strategies:
            return {"error": True, "message": f"Invalid bidding_strategy '{bidding_strategy}'. Must be one of: {', '.join(sorted(valid_strategies))}"}

        client = get_client()
        campaign_service = client.get_service("CampaignService")
        campaign_budget_service = client.get_service("CampaignBudgetService")

        operation = client.get_type("CampaignOperation")
        campaign = operation.create

        campaign.name = name
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
        campaign.campaign_budget = campaign_budget_service.campaign_budget_path(customer_id, budget_id)

        channel_map = {
            "SEARCH": client.enums.AdvertisingChannelTypeEnum.SEARCH,
            "DISPLAY": client.enums.AdvertisingChannelTypeEnum.DISPLAY,
            "SHOPPING": client.enums.AdvertisingChannelTypeEnum.SHOPPING,
            "VIDEO": client.enums.AdvertisingChannelTypeEnum.VIDEO,
        }
        campaign.advertising_channel_type = channel_map.get(
            channel_type.upper(), client.enums.AdvertisingChannelTypeEnum.SEARCH
        )

        _apply_bidding_strategy(client, campaign, strategy, target_cpa_dollars, target_roas,
                                max_cpc_bid_ceiling_dollars, target_impression_share_location,
                                target_impression_share_fraction)

        if channel_type.upper() == "SEARCH":
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

        response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[operation]
        )
        resource_name = response.results[0].resource_name
        new_id = resource_name.split("/")[-1]
        return {"id": new_id, "resource_name": resource_name, "status": "PAUSED", "name": name}

    @mcp.tool
    @handle_google_ads_errors
    def update_campaign(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        campaign_id: Annotated[str, Field(description="Campaign ID to update")],
        name: Annotated[Optional[str], Field(description="New campaign name")] = None,
        budget_id: Annotated[Optional[str], Field(description="New budget ID")] = None,
        bidding_strategy: Annotated[Optional[str], Field(description="New bidding strategy: MANUAL_CPC, MANUAL_CPM, MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, TARGET_ROAS, TARGET_IMPRESSION_SHARE, TARGET_SPEND")] = None,
        target_cpa_dollars: Annotated[Optional[float], Field(description="Target CPA in dollars (for TARGET_CPA or MAXIMIZE_CONVERSIONS)")] = None,
        target_roas: Annotated[Optional[float], Field(description="Target ROAS as ratio, e.g. 4.0 = 400% (for TARGET_ROAS or MAXIMIZE_CONVERSION_VALUE)")] = None,
        max_cpc_bid_ceiling_dollars: Annotated[Optional[float], Field(description="Max CPC bid ceiling in dollars")] = None,
        target_impression_share_location: Annotated[str, Field(description="ANYWHERE_ON_PAGE, TOP_OF_PAGE, or ABSOLUTE_TOP_OF_PAGE")] = "TOP_OF_PAGE",
        target_impression_share_fraction: Annotated[Optional[float], Field(description="Target impression share 0.0-1.0")] = None,
        target_search_network: Annotated[Optional[bool], Field(description="Show ads on Google search partner sites (e.g. AOL, Ask.com)")] = None,
        target_content_network: Annotated[Optional[bool], Field(description="Show ads on Google Display Network (opt-out recommended for Search campaigns)")] = None,
    ) -> dict:
        """Update a campaign's name, budget, bidding strategy, or network settings."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        client = get_client()
        campaign_service = client.get_service("CampaignService")

        operation = client.get_type("CampaignOperation")
        campaign = operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)

        field_mask = []
        if name is not None:
            campaign.name = name
            field_mask.append("name")
        if budget_id is not None:
            if err := validate_id(budget_id, "budget_id"):
                return {"error": True, "message": err}
            budget_service = client.get_service("CampaignBudgetService")
            campaign.campaign_budget = budget_service.campaign_budget_path(customer_id, budget_id)
            field_mask.append("campaign_budget")
        if bidding_strategy is not None:
            strategy = bidding_strategy.upper()
            if strategy not in VALID_BIDDING_STRATEGIES:
                return {"error": True, "message": f"Invalid bidding_strategy '{bidding_strategy}'. Must be one of: {', '.join(sorted(VALID_BIDDING_STRATEGIES))}"}
            strategy_paths = _apply_bidding_strategy(
                client, campaign, strategy, target_cpa_dollars, target_roas,
                max_cpc_bid_ceiling_dollars, target_impression_share_location,
                target_impression_share_fraction,
            )
            field_mask.extend(strategy_paths)
        if target_search_network is not None:
            campaign.network_settings.target_search_network = target_search_network
            field_mask.append("network_settings.target_search_network")
        if target_content_network is not None:
            campaign.network_settings.target_content_network = target_content_network
            field_mask.append("network_settings.target_content_network")

        if not field_mask:
            return {"error": True, "message": "No fields to update. Provide name, budget_id, bidding_strategy, or network settings."}

        operation.update_mask.paths.extend(field_mask)

        response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[operation]
        )
        return {"resource_name": response.results[0].resource_name, "updated_fields": field_mask}

    @mcp.tool
    @handle_google_ads_errors
    def set_campaign_status(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        status: Annotated[str, Field(description="New status: ENABLED, PAUSED, or REMOVED")],
        confirm: Annotated[bool, Field(description="Must be true to execute. Enabling a campaign will cause it to serve ads and spend money.")] = False,
    ) -> dict:
        """Enable, pause, or remove a campaign. Requires confirm=true for safety."""
        if err := validate_status(status):
            return {"error": True, "message": err}
        if not confirm:
            return {
                "warning": f"This will set campaign {campaign_id} to {status.upper()}. "
                "If ENABLED, the campaign will begin serving ads and spending budget. "
                "Set confirm=true to execute."
            }

        client = get_client()
        campaign_service = client.get_service("CampaignService")

        operation = client.get_type("CampaignOperation")
        campaign = operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)

        status_map = {
            "ENABLED": client.enums.CampaignStatusEnum.ENABLED,
            "PAUSED": client.enums.CampaignStatusEnum.PAUSED,
            "REMOVED": client.enums.CampaignStatusEnum.REMOVED,
        }
        campaign.status = status_map[status.upper()]
        operation.update_mask.paths.append("status")

        response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[operation]
        )
        return {"resource_name": response.results[0].resource_name, "new_status": status.upper()}
