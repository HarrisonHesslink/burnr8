# burnr8 — Google Ads MCP Server

A FastMCP server with 55 tools for managing Google Ads via Claude Code.

## Setup

```bash
source .venv/bin/activate
cp .env.example .env  # Fill in credentials
python setup_oauth.py  # If you need a refresh token
```

## Running

Registered globally in `~/.claude/.mcp.json`. Test manually:
```bash
PYTHONPATH=src .venv/bin/python -m burnr8.server
```

## Tool Categories (55 tools)

| Category | Tools | Key Operations |
|----------|-------|---------------|
| Accounts | 3 | list_accessible_accounts, get_account_info, get_api_usage |
| Campaigns | 5 | list/get/create/update + set_campaign_status |
| Ad Groups | 3 | list/create/update |
| Ads | 3 | list (with ad_strength), create RSA, set status |
| Keywords | 4 | list/add/remove + research_keywords |
| Negative Keywords | 4 | list/add (campaign + ad group level)/remove |
| Budgets | 4 | list/create/update + remove_orphan_budgets |
| Reporting | 5 | campaign/ad group/keyword perf, search terms, raw GAQL |
| Extensions | 6 | sitelinks, callouts, snippets, images |
| Conversions | 4 | list/get/create/update conversion actions |
| Compound | 3 | quick_audit, launch_campaign, cleanup_wasted_spend |
| Adjustments | 11 | device bids, ad schedules, location targets, geo presence |
| Goals | 5 | conversion goals, campaign-level goal overrides |

## Common Workflows

- **Full audit**: Use `quick_audit` or `/project:audit` — pulls all data in one call
- **Fix wasted spend**: Use `cleanup_wasted_spend` then `add_negative_keywords`
- **Launch campaign**: Use `launch_campaign` — creates budget + campaign + ad group + keywords + RSA
- **Check usage**: Use `get_api_usage` — shows ops count and version

## Safety

- Destructive tools require `confirm=true`: set_campaign_status, set_ad_status, remove_keyword, update_budget, remove_negative_keyword, remove_extension, remove_ad_schedule, remove_location_target, remove_orphan_budgets
- New campaigns always start PAUSED
- `run_gaql_query` is read-only escape hatch for any GAQL query
- All write tools require user approval via Claude Code permission rules

## Bidding Strategies

create_campaign and update_campaign support all 9 strategies: MANUAL_CPC, MANUAL_CPM, MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, TARGET_ROAS, TARGET_IMPRESSION_SHARE, TARGET_SPEND. Each accepts relevant target params (target_cpa_dollars, target_roas, max_cpc_bid_ceiling_dollars).

## Resources (auto-loaded context)

- `burnr8://usage` — API ops today
- `burnr8://accounts` — accessible accounts
- `burnr8://accounts/{id}/performance` — 30-day campaign metrics
- `burnr8://accounts/{id}/keywords` — keyword health + quality scores
- `burnr8://accounts/{id}/structure` — campaigns, budgets, ad group counts

## Credentials (env vars)

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CLIENT_ID`
- `GOOGLE_ADS_CLIENT_SECRET`
- `GOOGLE_ADS_REFRESH_TOKEN`
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (optional, for manager accounts — dashes auto-stripped)
