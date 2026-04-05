Detect week-over-week performance changes for account $ARGUMENTS (or use the active account).

Use burnr8 MCP tools:
1. Call get_campaign_performance for LAST_7_DAYS and LAST_14_DAYS
2. Calculate week-over-week changes for spend, CPA, CTR, conversions
3. Flag anything with >20% change
4. Call get_search_terms_report for new high-spend terms
5. Call get_keyword_performance for Quality Score changes
6. Present as a table sorted by severity
7. Recommend actions for each flagged anomaly
