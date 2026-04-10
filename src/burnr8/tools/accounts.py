from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import require_customer_id, run_gaql, validate_id, validate_recent_errors_limit
from burnr8.logging import LOG_DIR, get_recent_errors, get_usage_stats
from burnr8.session import get_active_account
from burnr8.session import set_active_account as _set_active


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_accessible_accounts() -> list[dict] | dict:
        """List all Google Ads customer accounts accessible via the manager account. Shows account names and IDs for easy selection."""
        client = get_client()
        customer_service = client.get_service("CustomerService")
        response = customer_service.list_accessible_customers()
        customer_ids = [rn.split("/")[-1] for rn in response.resource_names]
        query = """
            SELECT customer.id, customer.descriptive_name, customer.manager, customer.status
            FROM customer LIMIT 1
        """

        def _fetch_account(cid: str) -> dict[str, object]:
            try:
                rows = run_gaql(client, cid, query)
                if rows:
                    c = rows[0].get("customer", {})
                    return {
                        "customer_id": cid,
                        "name": c.get("descriptive_name", "Unknown"),
                        "is_manager": c.get("manager", False),
                        "status": c.get("status"),
                    }
                return {"customer_id": cid, "name": "Unknown"}
            except Exception:  # Enrichment step — run_gaql may raise GoogleAdsException or RPC errors
                return {"customer_id": cid, "name": "Unknown"}

        accounts = []
        if customer_ids:
            with ThreadPoolExecutor(max_workers=min(len(customer_ids), 10)) as executor:
                accounts = list(executor.map(_fetch_account, customer_ids))

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

        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err

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
        except Exception:  # Enrichment step — run_gaql may raise GoogleAdsException or RPC errors
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
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        client = get_client()
        query = """
            SELECT
                customer.id,
                customer.descriptive_name,
                customer.currency_code,
                customer.time_zone,
                customer.status,
                customer.manager,
                customer.test_account,
                customer.tracking_url_template,
                customer.final_url_suffix
            FROM customer
            LIMIT 1
        """
        rows = run_gaql(client, customer_id, query)
        if rows:
            return dict(rows[0].get("customer", {}))
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

        if err := validate_recent_errors_limit(limit):
            return {"error": True, "message": err}
        
        errors = get_recent_errors(limit=limit)
        return {
            "error_count": len(errors),
            "errors": errors,
            "log_file": str(LOG_DIR / "burnr8.log"),
        }
