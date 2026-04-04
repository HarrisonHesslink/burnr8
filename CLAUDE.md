# burnr8 — Google Ads MCP Server

A FastMCP server with 60 tools for managing Google Ads via Claude Code.

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

## Development

```bash
pip install -e ".[dev]"       # Install with dev deps
pytest tests/ -v              # Run 60 tests
ruff check src/ tests/        # Lint
pip-audit                     # CVE scan
burnr8                        # Terminal dashboard (API usage + spend)
./scripts/ci-local.sh         # Run full CI pipeline locally before pushing
```

## Architecture

```
src/burnr8/
├── server.py       # FastMCP entry + resources + prompts
├── client.py       # GoogleAdsClient singleton (thread-safe, lazy init)
├── helpers.py      # run_gaql(), validators, micros↔dollars
├── errors.py       # @handle_google_ads_errors (catches + logs every tool call)
├── logging.py      # File logger + daily usage counter (~/.burnr8/logs/)
├── dashboard.py    # Terminal dashboard (burnr8 command)
└── tools/          # 13 modules, 60 tools
```

## Tool Categories (60 tools)

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

## Gotchas

- **GAQL metrics are not filterable**: `metrics.conversions = 0` in a WHERE clause will fail. Query without the filter and filter in Python.
- **Field masks need subfield paths**: For bidding strategies with targets (e.g. maximize_conversions), use `maximize_conversions.target_cpa_micros`, NOT bare `maximize_conversions`. The bare name sets all subfields to 0.
- **MAXIMIZE_CLICKS doesn't exist in API v23**: It's implemented via `target_spend` under the hood.
- **Device criteria may not exist**: Smart Bidding campaigns don't auto-create device criteria. `set_device_bid_adjustment` handles this by creating if missing.
- **Budget `explicitly_shared` matters**: Must be `False` for Maximize Conversions to work. `create_budget` and `launch_campaign` handle this.
- **`search_term_view` can't join `ad_group_criterion`**: These resources are incompatible in GAQL SELECT.
- **`conversion_action.tag_snippets` is not GAQL-selectable**: Don't include it in queries.
- **`end_hour=24` is valid**: Google Ads API uses 24 to mean end of day / midnight.

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
