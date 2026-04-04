Run a full Google Ads audit for account $ARGUMENTS (or prompt for customer_id if not provided).

Use the burnr8 MCP tools:
1. Call quick_audit with the customer_id to get the full account snapshot
2. Analyze the results across all categories:
   - Campaign performance (CTR, CPA, conversion rate)
   - Keyword quality scores (flag QS < 5)
   - Ad strength (flag below GOOD)
   - Wasted spend (keywords with spend but 0 conversions)
   - Negative keyword coverage
   - Conversion tracking setup
3. Calculate a health score out of 100
4. Present findings as a formatted report with:
   - Score per category
   - Top issues sorted by impact
   - Quick wins with estimated savings
   - Recommended next actions
