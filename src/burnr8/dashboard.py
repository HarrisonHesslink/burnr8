#!/usr/bin/env python3
"""Terminal dashboard for burnr8 — shows API usage, recent activity, and campaign spend."""

import sys
from datetime import UTC, datetime

from dotenv import load_dotenv


def bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def format_dollars(val: float) -> str:
    return f"${val:,.2f}"


def print_dashboard():
    load_dotenv()

    from burnr8 import __version__
    from burnr8.client import get_client
    from burnr8.helpers import run_gaql
    from burnr8.logging import get_usage_stats

    stats = get_usage_stats()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    print()
    print(f"  burnr8 v{__version__}")
    print(f"  {now}")
    print("  " + "-" * 50)
    print()

    # API Usage
    pct = stats["ops_pct"]
    print(f"  API Ops Today:    {stats['ops_today']:,} / {stats['ops_limit']:,}  {bar(pct)}  {pct}%")
    print(f"  Errors (24h):     {stats['errors_today']}")

    # Recent activity
    calls = stats["recent_calls"]
    if calls:
        last = calls[-1]
        print(f"  Last Tool Call:   {last['tool']} (took {last['duration']}s)")
        print()
        print("  Recent Activity:")
        for call in reversed(calls[-8:]):
            status_color = call["status"].upper()
            print(f"    {call['time']}  {call['tool']:<30} {status_color:<6} {call['duration']}s")
    else:
        print("  No tool calls recorded today.")

    # Campaign spend
    print()
    print("  " + "-" * 50)
    try:
        client = get_client()
        # Get today's spend
        rows_today = run_gaql(client, _get_customer_id(), """
            SELECT campaign.id, campaign.name, campaign.status,
                   metrics.cost_micros, metrics.clicks, metrics.conversions
            FROM campaign
            WHERE campaign.status = 'ENABLED'
              AND segments.date DURING TODAY
        """)
        rows_mtd = run_gaql(client, _get_customer_id(), """
            SELECT campaign.id, campaign.name, campaign.status,
                   metrics.cost_micros, metrics.clicks, metrics.conversions
            FROM campaign
            WHERE campaign.status = 'ENABLED'
              AND segments.date DURING THIS_MONTH
        """)
        # Get budget
        budgets = run_gaql(client, _get_customer_id(), """
            SELECT campaign_budget.amount_micros, campaign_budget.status, campaign.name, campaign.status
            FROM campaign_budget
            WHERE campaign.status = 'ENABLED'
        """)

        print()
        print("  Campaign Spend:")
        for row in rows_today:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            name = c.get("name", "Unknown")
            cost_today = int(m.get("cost_micros", 0)) / 1_000_000
            clicks = int(m.get("clicks", 0))
            conv = float(m.get("conversions", 0))

            # Find matching budget
            budget_daily = 0
            for b in budgets:
                if b.get("campaign", {}).get("name") == name:
                    budget_daily = int(b.get("campaign_budget", {}).get("amount_micros", 0)) / 1_000_000
                    break

            # Find MTD
            cost_mtd = 0
            for mr in rows_mtd:
                if mr.get("campaign", {}).get("name") == name:
                    cost_mtd = int(mr.get("metrics", {}).get("cost_micros", 0)) / 1_000_000
                    break

            budget_str = f" / {format_dollars(budget_daily)} budget" if budget_daily else ""
            print(f"    {name}:")
            print(f"      Today:  {format_dollars(cost_today)}{budget_str}  |  {clicks} clicks  |  {conv:.0f} conv")
            print(f"      MTD:    {format_dollars(cost_mtd)}")

    except Exception as e:
        print(f"  Could not load campaign data: {e}")

    print()


def _get_customer_id() -> str:
    """Get the first non-manager customer ID."""
    import os

    from burnr8.client import get_client
    client = get_client()
    svc = client.get_service("CustomerService")
    resp = svc.list_accessible_customers()
    login_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
    for r in resp.resource_names:
        cid = r.split("/")[-1]
        if cid != login_id:
            return cid
    # Fallback to first
    return resp.resource_names[0].split("/")[-1] if resp.resource_names else ""


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m burnr8.dashboard")
        print("       burnr8")
        print()
        print("Shows API usage, recent tool calls, errors, and campaign spend.")
        return

    print_dashboard()


if __name__ == "__main__":
    main()
