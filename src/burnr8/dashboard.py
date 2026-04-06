#!/usr/bin/env python3
"""Terminal dashboard for burnr8 — shows API usage, recent activity, and campaign spend."""

import sys
from concurrent.futures import ThreadPoolExecutor
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

    # Storage stats
    from burnr8.logging import LOG_DIR
    from burnr8.reports import get_storage_stats

    storage = get_storage_stats()
    log_size = 0
    log_file = LOG_DIR / "burnr8.log"
    if log_file.exists():
        log_size = log_file.stat().st_size / 1_048_576
    print(f"  Reports:          {storage.get('report_files', 0)} files ({storage.get('total_size_mb', 0.0)} MB)")
    print(f"  Logs:             {log_size:.1f} MB")
    print()

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
        cid = _get_customer_id()

        today_query = """
            SELECT campaign.id, campaign.name, campaign.status,
                   metrics.cost_micros, metrics.clicks, metrics.conversions
            FROM campaign
            WHERE campaign.status = 'ENABLED'
              AND segments.date DURING TODAY
        """
        mtd_query = """
            SELECT campaign.id, campaign.name, campaign.status,
                   metrics.cost_micros, metrics.clicks, metrics.conversions
            FROM campaign
            WHERE campaign.status = 'ENABLED'
              AND segments.date DURING THIS_MONTH
        """
        budget_query = """
            SELECT campaign_budget.amount_micros, campaign_budget.status, campaign.name, campaign.status
            FROM campaign_budget
            WHERE campaign.status = 'ENABLED'
        """

        # Run all 3 queries in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_today = executor.submit(run_gaql, client, cid, today_query)
            future_mtd = executor.submit(run_gaql, client, cid, mtd_query)
            future_budgets = executor.submit(run_gaql, client, cid, budget_query)

        rows_today = future_today.result()
        rows_mtd = future_mtd.result()
        budgets = future_budgets.result()

        print()
        print("  Campaign Spend:")
        budget_map = {b.get("campaign", {}).get("name"): b for b in budgets}
        mtd_map = {mr.get("campaign", {}).get("name"): mr for mr in rows_mtd}
        for row in rows_today:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            name = c.get("name", "Unknown")
            cost_today = int(m.get("cost_micros", 0)) / 1_000_000
            clicks = int(m.get("clicks", 0))
            conv = float(m.get("conversions", 0))

            # Find matching budget
            budget_daily = 0
            b = budget_map.get(name)
            if b:
                budget_daily = int(b.get("campaign_budget", {}).get("amount_micros", 0)) / 1_000_000

            # Find MTD
            cost_mtd = 0
            mr = mtd_map.get(name)
            if mr:
                cost_mtd = int(mr.get("metrics", {}).get("cost_micros", 0)) / 1_000_000

            budget_str = f" / {format_dollars(budget_daily)} budget" if budget_daily else ""
            print(f"    {name}:")
            print(f"      Today:  {format_dollars(cost_today)}{budget_str}  |  {clicks} clicks  |  {conv:.0f} conv")
            print(f"      MTD:    {format_dollars(cost_mtd)}")

    except OSError as e:
        print(f"  Could not load campaign data: {e}")
    except Exception as e:
        from burnr8.logging import get_logger

        get_logger().exception("Dashboard campaign data error: %s", e)
        print(f"  Could not load campaign data: {e} (see ~/.burnr8/logs/burnr8.log)")

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
