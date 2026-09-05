from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import (
    build_mutate_request,
    dollars_to_micros,
    micros_to_dollars,
    require_customer_id,
    run_gaql,
    validate_daily_budget,
    validate_id,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_budgets(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> list[dict] | dict:
        """List all campaign budgets with spend data."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        client = get_client()
        query = """
            SELECT
                campaign_budget.id,
                campaign_budget.name,
                campaign_budget.amount_micros,
                campaign_budget.total_amount_micros,
                campaign_budget.period,
                campaign_budget.status,
                campaign_budget.delivery_method,
                campaign_budget.explicitly_shared,
                campaign_budget.reference_count
            FROM campaign_budget
            ORDER BY campaign_budget.name
        """
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            b = row.get("campaign_budget", {})
            results.append(
                {
                    "id": b.get("id"),
                    "name": b.get("name"),
                    "amount_dollars": micros_to_dollars(
                        int(b.get("total_amount_micros" if b.get("period") == "CUSTOM_PERIOD" else "amount_micros", 0))
                    ),
                    "period": b.get("period", "DAILY"),
                    "status": b.get("status"),
                    "delivery_method": b.get("delivery_method"),
                    "shared": b.get("explicitly_shared"),
                    "campaigns_using": b.get("reference_count"),
                }
            )
        return results

    @mcp.tool
    @handle_google_ads_errors
    def create_budget(
        name: Annotated[str, Field(description="Budget name")],
        amount_dollars: Annotated[float, Field(description="Budget amount in dollars for the selected period", gt=0)],
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        period: Annotated[
            Literal["DAILY", "CUSTOM_PERIOD"],
            Field(
                description="DAILY is an average daily budget; CUSTOM_PERIOD is a total campaign budget. Budget type cannot change after creation."
            ),
        ] = "DAILY",
    ) -> dict:
        """Create a daily or total budget. Total-budget campaigns require start/end dates."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if period not in ("DAILY", "CUSTOM_PERIOD"):
            return {"error": True, "message": "period must be DAILY or CUSTOM_PERIOD."}
        # Retain the configured mutation cap for total budgets too.
        if err := validate_daily_budget(amount_dollars):
            return {"error": True, "message": err}
        client = get_client()
        budget_service = client.get_service("CampaignBudgetService")

        operation = client.get_type("CampaignBudgetOperation")
        budget = operation.create

        budget.name = name
        budget.period = getattr(client.enums.BudgetPeriodEnum, period)
        amount_field = "total_amount_micros" if period == "CUSTOM_PERIOD" else "amount_micros"
        setattr(budget, amount_field, dollars_to_micros(amount_dollars))
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget.explicitly_shared = False

        response = budget_service.mutate_campaign_budgets(
            request=build_mutate_request(
                client, "MutateCampaignBudgetsRequest", customer_id, [operation], validate_only=not confirm
            )
        )
        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "amount_dollars": amount_dollars,
                "period": period,
                "message": f"Validation succeeded. This will create budget '{name}'. Set confirm=true to execute.",
            }

        resource_name = response.results[0].resource_name
        new_id = resource_name.split("/")[-1]
        return {
            "id": new_id,
            "resource_name": resource_name,
            "name": name,
            "amount_dollars": amount_dollars,
            "period": period,
        }

    @mcp.tool
    @handle_google_ads_errors
    def update_budget(
        budget_id: Annotated[str, Field(description="Budget ID to update")],
        amount_dollars: Annotated[
            float, Field(description="New budget amount in dollars for the existing budget period", gt=0)
        ],
        confirm: Annotated[
            bool, Field(description="Must be true to execute. Changing budget affects ad spend.")
        ] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        period: Annotated[
            Literal["DAILY", "CUSTOM_PERIOD"],
            Field(
                description="DAILY is an average daily budget; CUSTOM_PERIOD is a total campaign budget. Budget type cannot change after creation."
            ),
        ] = "DAILY",
    ) -> dict:
        """Update a budget amount using its existing period. Does not change budget type."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(budget_id, "budget_id"):
            return {"error": True, "message": err}
        if period not in ("DAILY", "CUSTOM_PERIOD"):
            return {"error": True, "message": "period must be DAILY or CUSTOM_PERIOD."}
        if err := validate_daily_budget(amount_dollars):
            return {"error": True, "message": err}
        client = get_client()
        budget_service = client.get_service("CampaignBudgetService")

        operation = client.get_type("CampaignBudgetOperation")
        budget = operation.update
        budget.resource_name = budget_service.campaign_budget_path(customer_id, budget_id)
        amount_field = "total_amount_micros" if period == "CUSTOM_PERIOD" else "amount_micros"
        setattr(budget, amount_field, dollars_to_micros(amount_dollars))
        operation.update_mask.paths.append(amount_field)

        response = budget_service.mutate_campaign_budgets(
            request=build_mutate_request(
                client, "MutateCampaignBudgetsRequest", customer_id, [operation], validate_only=not confirm
            )
        )
        period_label = "/day" if period == "DAILY" else " total"
        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "amount_dollars": amount_dollars,
                "period": period,
                "message": f"Validation succeeded. This will change budget {budget_id} to ${amount_dollars:.2f}{period_label}. "
                "Set confirm=true to execute.",
            }

        return {
            "resource_name": response.results[0].resource_name,
            "new_amount_dollars": amount_dollars,
            "period": period,
        }

    @mcp.tool
    @handle_google_ads_errors
    def remove_orphan_budgets(
        confirm: Annotated[
            bool, Field(description="Must be true to execute. Removes budgets not attached to any campaign.")
        ] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Find and remove orphan budgets (reference_count = 0). Requires confirm=true."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        client = get_client()
        query = """
            SELECT
                campaign_budget.id,
                campaign_budget.name,
                campaign_budget.amount_micros,
                campaign_budget.total_amount_micros,
                campaign_budget.period,
                campaign_budget.reference_count,
                campaign_budget.status
            FROM campaign_budget
            WHERE campaign_budget.reference_count = 0
                AND campaign_budget.status = 'ENABLED'
            ORDER BY campaign_budget.name
        """
        rows = run_gaql(client, customer_id, query)
        orphans = []
        for row in rows:
            b = row.get("campaign_budget", {})
            orphans.append(
                {
                    "id": b.get("id"),
                    "name": b.get("name"),
                    "amount_dollars": micros_to_dollars(
                        int(b.get("total_amount_micros" if b.get("period") == "CUSTOM_PERIOD" else "amount_micros", 0))
                    ),
                    "period": b.get("period", "DAILY"),
                }
            )

        if not orphans:
            return {"message": "No orphan budgets found.", "removed": 0}

        budget_service = client.get_service("CampaignBudgetService")
        operations = []
        for orphan in orphans:
            op = client.get_type("CampaignBudgetOperation")
            op.remove = budget_service.campaign_budget_path(customer_id, str(orphan["id"]))
            operations.append(op)

        response = budget_service.mutate_campaign_budgets(
            request=build_mutate_request(
                client, "MutateCampaignBudgetsRequest", customer_id, operations, validate_only=not confirm
            )
        )
        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "orphan_budgets": orphans,
                "message": f"Validation succeeded. Found {len(orphans)} orphan budget(s) not attached to any campaign. Set confirm=true to remove them.",
            }

        return {
            "removed": len(response.results),
            "removed_budgets": orphans,
        }
