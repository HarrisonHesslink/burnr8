Launch a new Google Ads search campaign for account $ARGUMENTS (or prompt for details).

Use burnr8 MCP tools:
1. Ask for: product/service description, landing page URL, daily budget
2. Call research_keywords with seed keywords from the description
3. Recommend keyword selections from the research results
4. Write 15 RSA headlines and 4 descriptions following Google Ads best practices:
   - Include CTAs, pricing, differentiators
   - Stay within character limits (30 chars headlines, 90 chars descriptions)
5. Call launch_campaign to create everything (budget + campaign + ad group + keywords + RSA)
6. Confirm everything was created PAUSED
7. Show a summary of what was created
