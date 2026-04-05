Show a quick spend summary for account $ARGUMENTS (or prompt for customer_id if not provided).

Use burnr8 MCP tools:
1. Call get_campaign_performance with the customer_id for LAST_7_DAYS
2. Call list_budgets for budget context
3. Present a clean summary table showing:
   - Each campaign's spend (today, this week, this month)
   - Budget utilization percentage
   - Key metrics: clicks, conversions, CPA
   - Any campaigns limited by budget
