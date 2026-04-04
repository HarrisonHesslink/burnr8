from typing import Annotated

from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql
from burnr8.logging import get_usage_stats


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_accessible_accounts() -> list[dict]:
        """List all Google Ads customer accounts accessible via the manager account."""
        client = get_client()
        customer_service = client.get_service("CustomerService")
        response = customer_service.list_accessible_customers()
        accounts = []
        for resource_name in response.resource_names:
            customer_id = resource_name.split("/")[-1]
            accounts.append({"customer_id": customer_id, "resource_name": resource_name})
        return accounts

    @mcp.tool
    @handle_google_ads_errors
    def get_account_info(
        customer_id: Annotated[str, Field(description="Google Ads customer ID (no dashes)")],
    ) -> dict:
        """Get account details including name, currency, timezone, and status."""
        client = get_client()
        query = """
            SELECT
                customer.id,
                customer.descriptive_name,
                customer.currency_code,
                customer.time_zone,
                customer.status,
                customer.manager,
                customer.test_account
            FROM customer
            LIMIT 1
        """
        rows = run_gaql(client, customer_id, query)
        if rows:
            return rows[0].get("customer", {})
        return {"error": True, "message": "Account not found"}

    @mcp.tool
    def get_api_usage() -> dict:
        """Get today's API usage stats: operations count, errors, rate limit status, recent tool calls, storage stats, and burnr8 version."""
        from burnr8 import __version__
        from burnr8.reports import get_storage_stats
        stats = get_usage_stats()
        stats["burnr8_version"] = __version__
        stats["storage"] = get_storage_stats()
        return stats
