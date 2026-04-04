Find and fix wasted ad spend for account $ARGUMENTS (or prompt for customer_id if not provided).

Use burnr8 MCP tools:
1. Call cleanup_wasted_spend with the customer_id
2. Call get_search_terms_report to find irrelevant queries
3. Present findings:
   - Total estimated monthly waste in dollars
   - Table of wasted keywords (spend, clicks, 0 conversions)
   - Recommended negative keywords to add (with match type)
   - Keywords to pause
4. Ask if the user wants to execute the recommended changes
