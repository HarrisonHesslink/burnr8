Analyze budget allocation for account $ARGUMENTS (or use the active account).

Use burnr8 MCP tools:
1. Call get_campaign_performance for LAST_30_DAYS
2. Call list_budgets for daily budget amounts
3. Use run_gaql_query to check metrics.search_budget_lost_impression_share
4. Identify budget-constrained high-performers and underspending low-performers
5. Present reallocation recommendations as a table
6. Show total budget stays the same — just redistributed
7. Estimate additional conversions from the reallocation
8. Ask for confirmation before making changes via update_budget
