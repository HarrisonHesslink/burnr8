from typing import Annotated

from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id
from burnr8.session import resolve_customer_id

VALID_CATEGORIES = {
    "DEFAULT", "PAGE_VIEW", "PURCHASE", "SIGNUP", "LEAD", "DOWNLOAD",
    "ADD_TO_CART", "BEGIN_CHECKOUT", "CONTACT", "BOOK_APPOINTMENT",
    "REQUEST_QUOTE", "GET_DIRECTIONS", "SUBMIT_LEAD_FORM", "SUBSCRIBE_PAID",
    "PHONE_CALL_LEAD", "IMPORTED_LEAD", "CONVERTED_LEAD", "QUALIFIED_LEAD",
    "STORE_SALE", "STORE_VISIT",
}

VALID_ORIGINS = {
    "WEBSITE", "APP", "CALL_FROM_ADS", "STORE", "GOOGLE_HOSTED", "YOUTUBE_HOSTED",
}


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_conversion_goals(
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> list[dict]:
        """List all customer conversion goals showing which are biddable (used by Smart Bidding)."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        query = """
            SELECT
                customer_conversion_goal.category,
                customer_conversion_goal.origin,
                customer_conversion_goal.biddable
            FROM customer_conversion_goal
        """
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            g = row.get("customer_conversion_goal", {})
            results.append({
                "category": g.get("category"),
                "origin": g.get("origin"),
                "biddable": g.get("biddable"),
            })
        return results

    @mcp.tool
    @handle_google_ads_errors
    def set_conversion_goal_biddable(
        category: Annotated[str, Field(description="Conversion goal category, e.g. PURCHASE, SIGNUP, LEAD, PAGE_VIEW")],
        origin: Annotated[str, Field(description="Conversion goal origin, e.g. WEBSITE, APP, STORE, CALL_FROM_ADS")],
        biddable: Annotated[bool, Field(description="Whether Smart Bidding should optimize toward this goal")],
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Toggle a customer conversion goal as biddable or non-biddable. Controls what Smart Bidding optimizes toward."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        cat = category.upper()
        if cat not in VALID_CATEGORIES:
            return {"error": True, "message": f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"}
        orig = origin.upper()
        if orig not in VALID_ORIGINS:
            return {"error": True, "message": f"Invalid origin '{origin}'. Must be one of: {', '.join(sorted(VALID_ORIGINS))}"}

        client = get_client()
        customer_conversion_goal_service = client.get_service("CustomerConversionGoalService")
        operation = client.get_type("CustomerConversionGoalOperation")
        goal = operation.update
        goal.resource_name = customer_conversion_goal_service.customer_conversion_goal_path(
            customer_id, cat, orig
        )
        goal.biddable = biddable
        operation.update_mask.paths.append("biddable")

        response = customer_conversion_goal_service.mutate_customer_conversion_goals(
            customer_id=customer_id, operations=[operation]
        )
        return {
            "resource_name": response.results[0].resource_name,
            "category": cat,
            "origin": orig,
            "biddable": biddable,
        }

    @mcp.tool
    @handle_google_ads_errors
    def get_campaign_conversion_goal_config(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Check if a campaign uses account-level or campaign-level conversion goals."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        client = get_client()
        query = f"""
            SELECT
                conversion_goal_campaign_config.campaign,
                conversion_goal_campaign_config.goal_config_level,
                conversion_goal_campaign_config.custom_conversion_goal
            FROM conversion_goal_campaign_config
            WHERE conversion_goal_campaign_config.campaign = 'customers/{customer_id}/campaigns/{campaign_id}'
        """
        rows = run_gaql(client, customer_id, query)
        if rows:
            row = rows[0]
            cfg = row.get("conversion_goal_campaign_config", {})
            return {
                "campaign": cfg.get("campaign"),
                "goal_config_level": cfg.get("goal_config_level"),
                "custom_conversion_goal": cfg.get("custom_conversion_goal"),
            }
        return {"error": True, "message": "Campaign conversion goal config not found"}

    @mcp.tool
    @handle_google_ads_errors
    def set_campaign_conversion_goal(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        conversion_action_ids: Annotated[list[str], Field(description="Conversion action IDs to optimize toward")],
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Set a campaign to use campaign-level goals with a custom conversion goal targeting specific conversion actions."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        for action_id in conversion_action_ids:
            if err := validate_id(action_id, "conversion_action_id"):
                return {"error": True, "message": err}
        if not conversion_action_ids:
            return {"error": True, "message": "conversion_action_ids must not be empty"}

        client = get_client()

        # Step 1: Create custom conversion goal
        custom_conversion_goal_service = client.get_service("CustomConversionGoalService")
        operation = client.get_type("CustomConversionGoalOperation")
        goal = operation.create
        goal.name = f"Campaign {campaign_id} Goal"
        goal.status = client.enums.CustomConversionGoalStatusEnum.ENABLED
        for action_id in conversion_action_ids:
            goal.conversion_actions.append(
                client.get_service("ConversionActionService").conversion_action_path(customer_id, action_id)
            )
        response = custom_conversion_goal_service.mutate_custom_conversion_goals(
            customer_id=customer_id, operations=[operation]
        )
        custom_goal_resource = response.results[0].resource_name

        # Step 2: Update campaign config to use campaign-level goals
        config_service = client.get_service("ConversionGoalCampaignConfigService")
        config_op = client.get_type("ConversionGoalCampaignConfigOperation")
        config = config_op.update
        config.resource_name = config_service.conversion_goal_campaign_config_path(customer_id, campaign_id)
        config.goal_config_level = client.enums.GoalConfigLevelEnum.CAMPAIGN
        config.custom_conversion_goal = custom_goal_resource
        config_op.update_mask.paths.extend(["goal_config_level", "custom_conversion_goal"])
        config_service.mutate_conversion_goal_campaign_configs(
            customer_id=customer_id, operations=[config_op]
        )

        return {
            "campaign_id": campaign_id,
            "custom_conversion_goal": custom_goal_resource,
            "goal_config_level": "CAMPAIGN",
            "conversion_action_ids": conversion_action_ids,
        }

    @mcp.tool
    @handle_google_ads_errors
    def list_custom_conversion_goals(
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> list[dict]:
        """List existing custom conversion goals."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        query = """
            SELECT
                custom_conversion_goal.id,
                custom_conversion_goal.name,
                custom_conversion_goal.status,
                custom_conversion_goal.conversion_actions
            FROM custom_conversion_goal
            ORDER BY custom_conversion_goal.name
        """
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            g = row.get("custom_conversion_goal", {})
            results.append({
                "id": g.get("id"),
                "name": g.get("name"),
                "status": g.get("status"),
                "conversion_actions": g.get("conversion_actions", []),
            })
        return results
