from typing import Annotated

from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id

_CONVERSION_ACTION_QUERY = """
    SELECT
        conversion_action.id,
        conversion_action.name,
        conversion_action.type,
        conversion_action.category,
        conversion_action.status,
        conversion_action.counting_type,
        conversion_action.value_settings.default_value,
        conversion_action.value_settings.always_use_default_value,
        conversion_action.attribution_model_settings.attribution_model
    FROM conversion_action
"""

VALID_CONVERSION_TYPES = {
    "WEBPAGE", "UPLOAD_CLICKS", "UPLOAD_CALLS", "CLICK_TO_CALL", "STORE_VISIT",
}
VALID_CONVERSION_CATEGORIES = {
    "DEFAULT", "PAGE_VIEW", "PURCHASE", "SIGNUP", "LEAD", "DOWNLOAD",
    "ADD_TO_CART", "BEGIN_CHECKOUT",
}
VALID_COUNTING_TYPES = {"ONE_PER_CLICK", "MANY_PER_CLICK"}
VALID_CONVERSION_STATUSES = {"ENABLED", "REMOVED", "HIDDEN"}


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_conversion_actions(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
    ) -> list[dict]:
        """List all conversion actions with their settings (name, type, category, status, counting type, value settings, attribution model)."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        query = _CONVERSION_ACTION_QUERY + " ORDER BY conversion_action.name"
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            ca = row.get("conversion_action", {})
            vs = ca.get("value_settings", {})
            am = ca.get("attribution_model_settings", {})
            results.append({
                "id": ca.get("id"),
                "name": ca.get("name"),
                "type": ca.get("type"),
                "category": ca.get("category"),
                "status": ca.get("status"),
                "counting_type": ca.get("counting_type"),
                "default_value": vs.get("default_value"),
                "always_use_default_value": vs.get("always_use_default_value"),
                "attribution_model": am.get("attribution_model"),
            })
        return results

    @mcp.tool
    @handle_google_ads_errors
    def get_conversion_action(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        conversion_action_id: Annotated[str, Field(description="Conversion action ID")],
    ) -> dict:
        """Get detailed info for a specific conversion action by ID."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(conversion_action_id, "conversion_action_id"):
            return {"error": True, "message": err}
        client = get_client()
        query = _CONVERSION_ACTION_QUERY + f" WHERE conversion_action.id = {conversion_action_id}"
        rows = run_gaql(client, customer_id, query)
        if rows:
            row = rows[0]
            ca = row.get("conversion_action", {})
            vs = ca.get("value_settings", {})
            am = ca.get("attribution_model_settings", {})
            return {
                "id": ca.get("id"),
                "name": ca.get("name"),
                "type": ca.get("type"),
                "category": ca.get("category"),
                "status": ca.get("status"),
                "counting_type": ca.get("counting_type"),
                "default_value": vs.get("default_value"),
                "always_use_default_value": vs.get("always_use_default_value"),
                "attribution_model": am.get("attribution_model"),
            }
        return {"error": True, "message": "Conversion action not found"}

    @mcp.tool
    @handle_google_ads_errors
    def create_conversion_action(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        name: Annotated[str, Field(description="Name for the conversion action (e.g. 'Purchase', 'Sign Up')")],
        type: Annotated[str, Field(description="Conversion type: WEBPAGE, UPLOAD_CLICKS, UPLOAD_CALLS, CLICK_TO_CALL, STORE_VISIT")] = "WEBPAGE",
        category: Annotated[str, Field(description="Conversion category: DEFAULT, PAGE_VIEW, PURCHASE, SIGNUP, LEAD, DOWNLOAD, ADD_TO_CART, BEGIN_CHECKOUT")] = "DEFAULT",
        counting_type: Annotated[str, Field(description="Counting type: ONE_PER_CLICK or MANY_PER_CLICK")] = "ONE_PER_CLICK",
        default_value: Annotated[float, Field(description="Default conversion value in dollars")] = 0.0,
        always_use_default_value: Annotated[bool, Field(description="If true, always use the default value instead of transaction-specific values")] = False,
    ) -> dict:
        """Create a new conversion action for tracking sign-ups, purchases, etc. Starts ENABLED by default."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}

        type_upper = type.upper()
        if type_upper not in VALID_CONVERSION_TYPES:
            return {"error": True, "message": f"Invalid type '{type}'. Must be one of: {', '.join(sorted(VALID_CONVERSION_TYPES))}"}

        category_upper = category.upper()
        if category_upper not in VALID_CONVERSION_CATEGORIES:
            return {"error": True, "message": f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CONVERSION_CATEGORIES))}"}

        counting_upper = counting_type.upper()
        if counting_upper not in VALID_COUNTING_TYPES:
            return {"error": True, "message": f"Invalid counting_type '{counting_type}'. Must be one of: {', '.join(sorted(VALID_COUNTING_TYPES))}"}

        client = get_client()
        conversion_action_service = client.get_service("ConversionActionService")

        operation = client.get_type("ConversionActionOperation")
        action = operation.create

        action.name = name
        action.status = client.enums.ConversionActionStatusEnum.ENABLED

        type_map = {
            "WEBPAGE": client.enums.ConversionActionTypeEnum.WEBPAGE,
            "UPLOAD_CLICKS": client.enums.ConversionActionTypeEnum.UPLOAD_CLICKS,
            "UPLOAD_CALLS": client.enums.ConversionActionTypeEnum.UPLOAD_CALLS,
            "CLICK_TO_CALL": client.enums.ConversionActionTypeEnum.CLICK_TO_CALL,
            "STORE_VISIT": client.enums.ConversionActionTypeEnum.STORE_VISIT,
        }
        action.type_ = type_map[type_upper]

        category_map = {
            "DEFAULT": client.enums.ConversionActionCategoryEnum.DEFAULT,
            "PAGE_VIEW": client.enums.ConversionActionCategoryEnum.PAGE_VIEW,
            "PURCHASE": client.enums.ConversionActionCategoryEnum.PURCHASE,
            "SIGNUP": client.enums.ConversionActionCategoryEnum.SIGNUP,
            "LEAD": client.enums.ConversionActionCategoryEnum.LEAD,
            "DOWNLOAD": client.enums.ConversionActionCategoryEnum.DOWNLOAD,
            "ADD_TO_CART": client.enums.ConversionActionCategoryEnum.ADD_TO_CART,
            "BEGIN_CHECKOUT": client.enums.ConversionActionCategoryEnum.BEGIN_CHECKOUT,
        }
        action.category = category_map[category_upper]

        counting_map = {
            "ONE_PER_CLICK": client.enums.ConversionActionCountingTypeEnum.ONE_PER_CLICK,
            "MANY_PER_CLICK": client.enums.ConversionActionCountingTypeEnum.MANY_PER_CLICK,
        }
        action.counting_type = counting_map[counting_upper]

        action.value_settings.default_value = default_value
        action.value_settings.always_use_default_value = always_use_default_value

        response = conversion_action_service.mutate_conversion_actions(
            customer_id=customer_id, operations=[operation]
        )
        resource_name = response.results[0].resource_name
        new_id = resource_name.split("/")[-1]
        return {
            "id": new_id,
            "resource_name": resource_name,
            "name": name,
            "type": type_upper,
            "category": category_upper,
            "status": "ENABLED",
            "counting_type": counting_upper,
            "default_value": default_value,
            "always_use_default_value": always_use_default_value,
        }

    @mcp.tool
    @handle_google_ads_errors
    def update_conversion_action(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
        conversion_action_id: Annotated[str, Field(description="Conversion action ID to update")],
        name: Annotated[str | None, Field(description="New name for the conversion action")] = None,
        status: Annotated[str | None, Field(description="New status: ENABLED, REMOVED, or HIDDEN")] = None,
        counting_type: Annotated[str | None, Field(description="New counting type: ONE_PER_CLICK or MANY_PER_CLICK")] = None,
        default_value: Annotated[float | None, Field(description="New default conversion value in dollars")] = None,
        always_use_default_value: Annotated[bool | None, Field(description="If true, always use the default value instead of transaction-specific values")] = None,
    ) -> dict:
        """Update a conversion action's name, value, status, or counting type."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(conversion_action_id, "conversion_action_id"):
            return {"error": True, "message": err}

        client = get_client()
        conversion_action_service = client.get_service("ConversionActionService")

        operation = client.get_type("ConversionActionOperation")
        action = operation.update
        action.resource_name = conversion_action_service.conversion_action_path(
            customer_id, conversion_action_id
        )

        field_mask = []

        if name is not None:
            action.name = name
            field_mask.append("name")

        if status is not None:
            status_upper = status.upper()
            if status_upper not in VALID_CONVERSION_STATUSES:
                return {"error": True, "message": f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_CONVERSION_STATUSES))}"}
            status_map = {
                "ENABLED": client.enums.ConversionActionStatusEnum.ENABLED,
                "REMOVED": client.enums.ConversionActionStatusEnum.REMOVED,
                "HIDDEN": client.enums.ConversionActionStatusEnum.HIDDEN,
            }
            action.status = status_map[status_upper]
            field_mask.append("status")

        if counting_type is not None:
            counting_upper = counting_type.upper()
            if counting_upper not in VALID_COUNTING_TYPES:
                return {"error": True, "message": f"Invalid counting_type '{counting_type}'. Must be one of: {', '.join(sorted(VALID_COUNTING_TYPES))}"}
            counting_map = {
                "ONE_PER_CLICK": client.enums.ConversionActionCountingTypeEnum.ONE_PER_CLICK,
                "MANY_PER_CLICK": client.enums.ConversionActionCountingTypeEnum.MANY_PER_CLICK,
            }
            action.counting_type = counting_map[counting_upper]
            field_mask.append("counting_type")

        if default_value is not None:
            action.value_settings.default_value = default_value
            field_mask.append("value_settings.default_value")

        if always_use_default_value is not None:
            action.value_settings.always_use_default_value = always_use_default_value
            field_mask.append("value_settings.always_use_default_value")

        if not field_mask:
            return {"error": True, "message": "No fields to update"}

        operation.update_mask.paths.extend(field_mask)

        response = conversion_action_service.mutate_conversion_actions(
            customer_id=customer_id, operations=[operation]
        )
        return {"resource_name": response.results[0].resource_name, "updated_fields": field_mask}
