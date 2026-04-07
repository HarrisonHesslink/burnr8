from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import dollars_to_micros, micros_to_dollars, require_customer_id, run_gaql, validate_id


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_budgets(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> list[dict] | dict:
        """List all campaign budgets with spend data."""
        customer_id, err = require_customer_id(customer_id)
        if err:
            return err
        client = get_client()
        query = """
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
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            b = row.get("campaign_budget", {})
            results.append(
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
        return results

    @mcp.tool
    @handle_google_ads_errors
    def create_budget(
        name: Annotated[str, Field(description="Budget name")],
        amount_dollars: Annotated[float, Field(description="Daily budget amount in dollars", gt=0)],
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create a new daily campaign budget."""
        customer_id, err = require_customer_id(customer_id)
        if err:
            return err
        client = get_client()
        budget_service = client.get_service("CampaignBudgetService")

        operation = client.get_type("CampaignBudgetOperation")
        budget = operation.create

        budget.name = name
        budget.amount_micros = dollars_to_micros(amount_dollars)
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget.explicitly_shared = False

        response = budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[operation])
        resource_name = response.results[0].resource_name
        new_id = resource_name.split("/")[-1]
        return {"id": new_id, "resource_name": resource_name, "name": name, "amount_dollars": amount_dollars}

    @mcp.tool
    @handle_google_ads_errors
    def update_budget(
        budget_id: Annotated[str, Field(description="Budget ID to update")],
        amount_dollars: Annotated[float, Field(description="New daily budget amount in dollars", gt=0)],
        confirm: Annotated[
            bool, Field(description="Must be true to execute. Changing budget affects ad spend.")
        ] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Update a campaign budget amount. Requires confirm=true."""
        customer_id, err = require_customer_id(customer_id)
        if err:
            return err
        if not confirm:
            return {
                "warning": True,
                "message": f"This will change budget {budget_id} to ${amount_dollars:.2f}/day. "
                "Set confirm=true to execute.",
            }
        if err := validate_id(budget_id, "budget_id"):
            return {"error": True, "message": err}
        client = get_client()
        budget_service = client.get_service("CampaignBudgetService")

        operation = client.get_type("CampaignBudgetOperation")
        budget = operation.update
        budget.resource_name = budget_service.campaign_budget_path(customer_id, budget_id)
        budget.amount_micros = dollars_to_micros(amount_dollars)
        operation.update_mask.paths.append("amount_micros")

        response = budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[operation])
        return {"resource_name": response.results[0].resource_name, "new_amount_dollars": amount_dollars}

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
        customer_id, err = require_customer_id(customer_id)
        if err:
            return err
        client = get_client()
        query = """
            SELECT
                campaign_budget.id,
                campaign_budget.name,
                campaign_budget.amount_micros,
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
                    "amount_dollars": micros_to_dollars(int(b.get("amount_micros", 0))),
                }
            )

        if not orphans:
            return {"message": "No orphan budgets found.", "removed": 0}

        if not confirm:
            return {
                "warning": True,
                "orphan_budgets": orphans,
                "message": f"Found {len(orphans)} orphan budget(s) not attached to any campaign. Set confirm=true to remove them.",
            }

        budget_service = client.get_service("CampaignBudgetService")
        operations = []
        for orphan in orphans:
            op = client.get_type("CampaignBudgetOperation")
            op.remove = budget_service.campaign_budget_path(customer_id, str(orphan["id"]))
            operations.append(op)

        response = budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=operations)
        return {
            "removed": len(response.results),
            "removed_budgets": orphans,
        }
