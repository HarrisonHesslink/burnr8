from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import build_mutate_request, require_customer_id, run_gaql, validate_id
from burnr8.logging import get_logger

VALID_CATEGORIES = {
    "DEFAULT",
    "PAGE_VIEW",
    "PURCHASE",
    "SIGNUP",
    "LEAD",
    "DOWNLOAD",
    "ADD_TO_CART",
    "BEGIN_CHECKOUT",
    "CONTACT",
    "BOOK_APPOINTMENT",
    "REQUEST_QUOTE",
    "GET_DIRECTIONS",
    "SUBMIT_LEAD_FORM",
    "SUBSCRIBE_PAID",
    "PHONE_CALL_LEAD",
    "IMPORTED_LEAD",
    "CONVERTED_LEAD",
    "QUALIFIED_LEAD",
    "STORE_SALE",
    "STORE_VISIT",
}

VALID_ORIGINS = {
    "WEBSITE",
    "APP",
    "CALL_FROM_ADS",
    "STORE",
    "GOOGLE_HOSTED",
    "YOUTUBE_HOSTED",
}


def _resolve_action_names(client: object, customer_id: str, action_ids: list[str]) -> dict[str, str]:
    """Resolve conversion action IDs to names via a single GAQL query.

    Returns a dict mapping action ID (str) -> action name (str).
    """
    if not action_ids:
        return {}
    # Guard against non-numeric IDs that would produce invalid GAQL
    if not all(aid.isdigit() for aid in action_ids):
        get_logger().warning("_resolve_action_names: non-numeric action IDs skipped: %s", action_ids)
        return {}
    id_list = ", ".join(action_ids)
    query = f"""
        SELECT conversion_action.id, conversion_action.name
        FROM conversion_action
        WHERE conversion_action.id IN ({id_list})
    """
    rows = run_gaql(client, customer_id, query)
    result: dict[str, str] = {}
    for row in rows:
        ca = row.get("conversion_action", {})
        aid = ca.get("id")
        aname = ca.get("name")
        if aid is not None:
            result[str(aid)] = aname
    return result


def _extract_action_id(resource_name: str) -> str | None:
    """Extract the action ID from a conversion action resource name.

    E.g. 'customers/123/conversionActions/456' -> '456'
    """
    parts = resource_name.rsplit("/", 1)
    return parts[-1] if len(parts) == 2 and parts[-1] else None


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_conversion_goals(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> list[dict] | dict:
        """List all customer conversion goals showing which are biddable (used by Smart Bidding), with conversion actions grouped by category."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        client = get_client()
        query = """
            SELECT
                customer_conversion_goal.category,
                customer_conversion_goal.origin,
                customer_conversion_goal.biddable
            FROM customer_conversion_goal
        """
        rows = run_gaql(client, customer_id, query)

        try:
            action_query = """
                SELECT
                    conversion_action.id,
                    conversion_action.name,
                    conversion_action.category
                FROM conversion_action
                WHERE conversion_action.status = 'ENABLED'
            """
            action_rows = run_gaql(client, customer_id, action_query)
            actions_by_category: dict[str, list[dict]] = {}
            for arow in action_rows:
                ca = arow.get("conversion_action", {})
                cat = ca.get("category")
                if cat:
                    actions_by_category.setdefault(cat, []).append({"id": str(ca.get("id")), "name": ca.get("name")})
        except Exception:
            get_logger().warning("list_conversion_goals: action name resolution failed", exc_info=True)
            actions_by_category = {}

        results = []
        for row in rows:
            g = row.get("customer_conversion_goal", {})
            cat = g.get("category")
            results.append(
                {
                    "category": cat,
                    "origin": g.get("origin"),
                    "biddable": g.get("biddable"),
                    "conversion_actions": actions_by_category.get(cat, []),
                }
            )
        return results

    @mcp.tool
    @handle_google_ads_errors
    def set_conversion_goal_biddable(
        category: Annotated[str, Field(description="Conversion goal category, e.g. PURCHASE, SIGNUP, LEAD, PAGE_VIEW")],
        origin: Annotated[str, Field(description="Conversion goal origin, e.g. WEBSITE, APP, STORE, CALL_FROM_ADS")],
        biddable: Annotated[bool, Field(description="Whether Smart Bidding should optimize toward this goal")],
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Toggle a customer conversion goal as biddable or non-biddable. Controls what Smart Bidding optimizes toward."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        cat = category.upper()
        if cat not in VALID_CATEGORIES:
            return {
                "error": True,
                "message": f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
            }
        orig = origin.upper()
        if orig not in VALID_ORIGINS:
            return {
                "error": True,
                "message": f"Invalid origin '{origin}'. Must be one of: {', '.join(sorted(VALID_ORIGINS))}",
            }

        client = get_client()
        customer_conversion_goal_service = client.get_service("CustomerConversionGoalService")
        operation = client.get_type("CustomerConversionGoalOperation")
        goal = operation.update
        goal.resource_name = customer_conversion_goal_service.customer_conversion_goal_path(customer_id, cat, orig)
        goal.biddable = biddable
        operation.update_mask.paths.append("biddable")

        response = customer_conversion_goal_service.mutate_customer_conversion_goals(
            request=build_mutate_request(
                client, "MutateCustomerConversionGoalsRequest", customer_id, [operation], validate_only=not confirm
            )
        )
        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "message": f"Validation succeeded. This will toggle biddable={biddable} for {cat}/{orig}. Set confirm=true to execute.",
            }

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
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Check if a campaign uses account-level or campaign-level conversion goals."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
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
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Set a campaign to use campaign-level goals with a custom conversion goal targeting specific conversion actions."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
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
            request=build_mutate_request(
                client, "MutateCustomConversionGoalsRequest", customer_id, [operation], validate_only=not confirm
            )
        )
        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "message": f"Validation succeeded. This will set campaign conversion goal targeting {len(conversion_action_ids)} actions. Set confirm=true to execute.",
            }

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
            request=build_mutate_request(
                client,
                "MutateConversionGoalCampaignConfigsRequest",
                customer_id,
                [config_op],
                validate_only=not confirm,
            )
        )

        try:
            name_map = _resolve_action_names(client, customer_id, list(conversion_action_ids))
        except Exception:
            get_logger().warning("set_campaign_conversion_goal: action name resolution failed", exc_info=True)
            name_map = {}
        resolved_actions = [{"id": aid, "name": name_map.get(aid)} for aid in conversion_action_ids]

        return {
            "campaign_id": campaign_id,
            "custom_conversion_goal": custom_goal_resource,
            "goal_config_level": "CAMPAIGN",
            "conversion_actions": resolved_actions,
        }

    @mcp.tool
    @handle_google_ads_errors
    def list_custom_conversion_goals(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> list[dict] | dict:
        """List existing custom conversion goals with resolved conversion action names."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
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

        all_action_ids: list[str] = []
        for row in rows:
            g = row.get("custom_conversion_goal", {})
            for rn in g.get("conversion_actions", []):
                aid = _extract_action_id(rn)
                if aid is not None:
                    all_action_ids.append(aid)

        try:
            unique_ids = list(set(all_action_ids))
            name_map = _resolve_action_names(client, customer_id, unique_ids) if unique_ids else {}
        except Exception:
            get_logger().warning("list_custom_conversion_goals: action name resolution failed", exc_info=True)
            name_map = {}

        results = []
        for row in rows:
            g = row.get("custom_conversion_goal", {})
            resolved_actions = []
            for rn in g.get("conversion_actions", []):
                aid = _extract_action_id(rn)
                resolved_actions.append({"id": aid, "name": name_map.get(aid or "")})
            results.append(
                {
                    "id": g.get("id"),
                    "name": g.get("name"),
                    "status": g.get("status"),
                    "conversion_actions": resolved_actions,
                }
            )
        return results
