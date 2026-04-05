from typing import Annotated

from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id
from burnr8.logging import LOG_DIR, get_recent_errors, get_usage_stats
from burnr8.session import get_active_account, resolve_customer_id
from burnr8.session import set_active_account as _set_active


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_accessible_accounts() -> list[dict]:
        """List all Google Ads customer accounts accessible via the manager account. Shows account names and IDs for easy selection."""
        client = get_client()
        customer_service = client.get_service("CustomerService")
        response = customer_service.list_accessible_customers()
        accounts = []
        for resource_name in response.resource_names:
            cid = resource_name.split("/")[-1]
            # Fetch account name
            try:
                rows = run_gaql(
                    client,
                    cid,
                    """
                    SELECT customer.id, customer.descriptive_name, customer.manager, customer.status
                    FROM customer LIMIT 1
                """,
                )
                if rows:
                    c = rows[0].get("customer", {})
                    accounts.append(
                        {
                            "customer_id": cid,
                            "name": c.get("descriptive_name", "Unknown"),
                            "is_manager": c.get("manager", False),
                            "status": c.get("status"),
                        }
                    )
                else:
                    accounts.append({"customer_id": cid, "name": "Unknown"})
            except Exception:
                accounts.append({"customer_id": cid, "name": "Unknown"})

        active = get_active_account()
        return {
            "accounts": accounts,
            "active_account": active,
            "hint": "Call set_active_account with a customer_id to set the default for all tools."
            if not active
            else None,
        }

    @mcp.tool
    def set_active_account_tool(
        customer_id: Annotated[str, Field(description="Google Ads customer ID to set as active (no dashes)")],
    ) -> dict:
        """Set the active Google Ads account for this session. Once set, all tools use this account by default — no need to pass customer_id on every call."""
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        _set_active(customer_id)
        # Fetch account name for confirmation
        try:
            client = get_client()
            rows = run_gaql(
                client,
                customer_id,
                """
                SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1
            """,
            )
            name = rows[0].get("customer", {}).get("descriptive_name", "Unknown") if rows else "Unknown"
        except Exception:
            name = "Unknown"
        return {
            "active_account": customer_id,
            "name": name,
            "message": f"Active account set to {name} ({customer_id}). All tools will use this account by default.",
        }

    @mcp.tool
    def get_active_account_tool() -> dict:
        """Get the currently active Google Ads account for this session."""
        active = get_active_account()
        if not active:
            return {"active_account": None, "message": "No active account set. Call set_active_account to set one."}
        return {"active_account": active}

    @mcp.tool
    @handle_google_ads_errors
    def get_account_info(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get account details including name, currency, timezone, and status."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
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

    @mcp.tool
    def get_recent_errors_tool(
        limit: Annotated[int, Field(description="Max number of recent errors to return")] = 20,
    ) -> dict:
        """Get recent error log entries from burnr8. Useful for diagnosing tool failures."""
        errors = get_recent_errors(limit=limit)
        return {
            "error_count": len(errors),
            "errors": errors,
            "log_file": str(LOG_DIR / "burnr8.log"),
        }
