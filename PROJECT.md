# burnr8 — Architecture & Tool Reference

## System Architecture

```
                          Claude Code
                              |
                         MCP Protocol (stdio)
                              |
                    +---------+---------+
                    |    burnr8 Server  |
                    |   (FastMCP 3.x)  |
                    +---------+---------+
                              |
            +-----------------+-----------------+
            |                 |                 |
        60 Tools        5 Resources       3 Prompts
            |                 |                 |
            v                 v                 v
    +---------------+   burnr8://...    audit, optimize,
    | Google Ads    |                   new_campaign
    | API v23       |
    | (gRPC)        |
    +---------------+
```

## Core Modules

### Request Flow

```
Tool call from Claude
    → server.py (FastMCP routes to tool function)
        → @handle_google_ads_errors (errors.py — catches exceptions, logs call)
            → Tool function (tools/*.py — validates inputs, builds GAQL/mutation)
                → get_client() (client.py — lazy singleton, env-based credentials)
                    → Google Ads API v23 (gRPC)
                → run_gaql() (helpers.py — executes GAQL, converts proto→dict)
            ← Returns plain dict/list
        ← Logs duration, status, error details to ~/.burnr8/logs/
    ← JSON response to Claude
```

### Module Responsibilities

| Module | Lines | Purpose |
|--------|-------|---------|
| `server.py` | 289 | FastMCP entry point. Registers tools, resources, prompts. Loads `.env` at import. |
| `client.py` | 21 | Lazy `GoogleAdsClient` singleton. Reads 5 env vars, strips dashes from login_customer_id. |
| `helpers.py` | 58 | `run_gaql()`, `proto_to_dict()`, `micros_to_dollars()`, `dollars_to_micros()`, input validators. |
| `errors.py` | 59 | `@handle_google_ads_errors` decorator. Catches `GoogleAdsException` + Python errors. Logs every call. |
| `logging.py` | 86 | File logger (`~/.burnr8/logs/burnr8.log`), daily usage counter (`usage.json`), rate limit tracking. |
| `dashboard.py` | 145 | Terminal dashboard (`burnr8` command). Shows API usage, recent calls, campaign spend. |

### Key Design Decisions

**Lazy client initialization** — `GoogleAdsClient` is created on first tool call, not at server startup. The server starts instantly; credential errors surface when you use a tool.

**Error decorator with logging** — Every tool is wrapped by `@handle_google_ads_errors` which: catches `GoogleAdsException` + `KeyError/ValueError/TypeError`, logs tool name + duration + status, updates daily ops counter.

**Proto-to-dict conversion** — All protobuf responses are converted to plain Python dicts via `MessageToDict`. Cost fields are converted from micros to dollars. Enums are returned as strings.

**GAQL LIMIT injection** — `run_gaql()` appends `LIMIT N` to queries that don't already have one, preventing unbounded result sets.

---

## Tool Categories

### 1. Accounts (`accounts.py` — 54 lines, 3 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_accessible_accounts` | Read | List all accounts accessible via manager account |
| `get_account_info` | Read | Account name, currency, timezone, status |
| `get_api_usage` | Read | Today's API ops count, errors, rate limit %, version |

### 2. Campaigns (`campaigns.py` — 369 lines, 5 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_campaigns` | Read | All campaigns with status, channel type, bidding, metrics |
| `get_campaign` | Read | Full campaign details with network settings |
| `create_campaign` | Write | New campaign (always PAUSED). All 9 bidding strategies. EU political ads. |
| `update_campaign` | Write | Name, budget, bidding strategy, network settings (search/display partners) |
| `set_campaign_status` | Write | Enable/pause/remove. Requires `confirm=true`. |

**Bidding strategy support** — Shared `_apply_bidding_strategy()` function handles all 9 strategies with correct field mask paths:

| Strategy | Field Mask (with target) | Field Mask (without target) |
|----------|------------------------|---------------------------|
| MANUAL_CPC | `manual_cpc` | `manual_cpc` |
| MANUAL_CPM | `manual_cpm` | `manual_cpm` |
| MAXIMIZE_CLICKS | `target_spend.cpc_bid_ceiling_micros` | `target_spend` |
| MAXIMIZE_CONVERSIONS | `maximize_conversions.target_cpa_micros` | `maximize_conversions` |
| MAXIMIZE_CONVERSION_VALUE | `maximize_conversion_value.target_roas` | `maximize_conversion_value` |
| TARGET_CPA | `target_cpa.target_cpa_micros` | `target_cpa` |
| TARGET_ROAS | `target_roas.target_roas` | `target_roas` |
| TARGET_IMPRESSION_SHARE | `target_impression_share.location` + subfields | N/A (always has location) |
| TARGET_SPEND | `target_spend.cpc_bid_ceiling_micros` | `target_spend` |

### 3. Ad Groups (`ad_groups.py` — 139 lines, 3 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_ad_groups` | Read | Ad groups with CPC bids, metrics. Filter by campaign. |
| `create_ad_group` | Write | New ad group. SEARCH_STANDARD type. |
| `update_ad_group` | Write | Name, CPC bid, status. |

### 4. Ads (`ads.py` — 161 lines, 3 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_ads` | Read | Ads with ad_strength, approval status, headlines, descriptions, metrics |
| `create_responsive_search_ad` | Write | RSA with 3-15 headlines, 2-4 descriptions, final URL |
| `set_ad_status` | Write | Enable/pause/remove. Requires `confirm=true`. |

### 5. Keywords (`keywords.py` — 202 lines, 4 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_keywords` | Read | Keywords with bids, match types, quality scores, metrics |
| `add_keywords` | Write | Batch add keywords (Pydantic model: text + match_type) |
| `remove_keyword` | Write | Remove by criterion_id. Requires `confirm=true`. |
| `research_keywords` | Read | Keyword ideas with volume, competition, CPC estimates |

### 6. Negative Keywords (`negative_keywords.py` — 248 lines, 4 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_negative_keywords` | Read | Campaign + ad group level negatives |
| `add_negative_keywords` | Write | Campaign-level negatives (CampaignCriterionService) |
| `add_ad_group_negative_keywords` | Write | Ad group-level negatives (AdGroupCriterionService) |
| `remove_negative_keyword` | Write | Remove by criterion_id + scope. Requires `confirm=true`. |

### 7. Budgets (`budgets.py` — 162 lines, 4 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_budgets` | Read | Budgets with amount, delivery method, reference count |
| `create_budget` | Write | Daily budget. `explicitly_shared=False` for Smart Bidding. |
| `update_budget` | Write | Change amount. Requires `confirm=true`. |
| `remove_orphan_budgets` | Write | Find + remove budgets with 0 campaigns. Requires `confirm=true`. |

### 8. Reporting (`reporting.py` — 249 lines, 5 tools)

| Tool | Type | Description |
|------|------|-------------|
| `run_gaql_query` | Read | Raw GAQL escape hatch. Any query. |
| `get_campaign_performance` | Read | Impressions, clicks, CTR, CPC, cost, conversions, CPA |
| `get_ad_group_performance` | Read | Ad group metrics with campaign context |
| `get_keyword_performance` | Read | Keyword metrics with quality scores |
| `get_search_terms_report` | Read | Actual search queries that triggered ads |

### 9. Extensions (`extensions.py` — 355 lines, 6 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_extensions` | Read | Sitelinks, callouts, snippets, images on campaigns |
| `create_sitelink` | Write | Two-step: create asset + link to campaign |
| `create_callout` | Write | Two-step: create asset + link to campaign |
| `create_structured_snippet` | Write | Two-step: create asset + link to campaign |
| `create_image_extension` | Write | Downloads image from URL, creates asset, links to campaign |
| `remove_extension` | Write | Remove campaign-asset link. Requires `confirm=true`. |

### 10. Conversions (`conversions.py` — 250 lines, 4 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_conversion_actions` | Read | All conversion actions with settings, attribution model |
| `get_conversion_action` | Read | Single conversion action details |
| `create_conversion_action` | Write | New conversion action (WEBPAGE, SIGNUP, PURCHASE, etc.) |
| `update_conversion_action` | Write | Name, status, counting type, value settings |

### 11. Compound (`compound.py` — 556 lines, 3 tools)

| Tool | Type | Description |
|------|------|-------------|
| `quick_audit` | Read | Full account snapshot in one call: campaigns, keywords, ads, negatives, conversions, budgets. Returns summary with totals. |
| `launch_campaign` | Write | Creates budget + campaign + ad group + keywords + RSA in 5 sequential API calls. Tracks partial failures. |
| `cleanup_wasted_spend` | Read | Finds keywords with spend but 0 conversions. Flags informational intent. Calculates total waste. |

**`launch_campaign` failure handling:**
```
Step 1: Create budget       → created["budget"] = resource_name
Step 2: Create campaign     → created["campaign"] = resource_name
Step 3: Create ad group     → created["ad_group"] = resource_name
Step 4: Add keywords        → created["keywords"] = [resource_names]
Step 5: Create RSA          → created["ad"] = resource_name

If any step fails → returns {error: true, partial_failure: true, created_before_failure: {...}}
```

### 12. Adjustments (`adjustments.py` — 512 lines, 11 tools)

| Tool | Type | Description |
|------|------|-------------|
| `pause_keyword` | Write | Pause keyword by criterion_id |
| `set_device_bid_adjustment` | Write | Set mobile/desktop/tablet bid modifier. Creates criterion if missing. |
| `list_device_bid_adjustments` | Read | Current device bid modifiers |
| `set_ad_schedule` | Write | Dayparting: day + hours (0-24) + bid modifier |
| `list_ad_schedules` | Read | Current ad schedules |
| `remove_ad_schedule` | Write | Remove schedule. Requires `confirm=true`. |
| `list_location_targets` | Read | Geo targets on a campaign |
| `add_location_target` | Write | Add location (or exclusion) with bid modifier |
| `remove_location_target` | Write | Remove location. Requires `confirm=true`. |
| `get_geo_target_type_setting` | Read | Presence vs Presence or Interest |
| `set_geo_target_type_setting` | Write | Set targeting mode (PRESENCE recommended) |

### 13. Goals (`goals.py` — 200 lines, 5 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_conversion_goals` | Read | Customer goals with biddable status |
| `set_conversion_goal_biddable` | Write | Toggle what Smart Bidding optimizes toward |
| `get_campaign_conversion_goal_config` | Read | Account vs campaign-level goal config |
| `set_campaign_conversion_goal` | Write | Override campaign with specific conversion actions |
| `list_custom_conversion_goals` | Read | Existing custom conversion goals |

---

## MCP Resources

| URI | Type | Description |
|-----|------|-------------|
| `burnr8://usage` | Static | API ops today, errors, rate limit % |
| `burnr8://accounts` | Static | Accessible account IDs |
| `burnr8://accounts/{id}/performance` | Template | 30-day campaign metrics, total spend, CPA |
| `burnr8://accounts/{id}/keywords` | Template | Keyword health, avg QS, low-QS list |
| `burnr8://accounts/{id}/structure` | Template | Campaigns, budgets, ad group counts |

## MCP Prompts

| Name | Params | Workflow |
|------|--------|---------|
| `audit` | `customer_id` | quick_audit → analyze QS, wasted spend, tracking → health score |
| `optimize` | `customer_id` | cleanup_wasted_spend → search terms → negative keywords → pause |
| `new_campaign` | `customer_id, product, url` | research → structure → copy → launch_campaign |

## Safety Architecture

### Layer 1: Tool-Level Confirmation
9 destructive tools require `confirm=true` parameter. Without it, they return a warning describing what would happen.

### Layer 2: Claude Code Permission Rules
`.claude/settings.json` lists 30 write tools under `"ask"`. Claude Code prompts the user for approval before execution. This is enforced by the harness — Claude cannot bypass it.

### Layer 3: Agent Restrictions
The `ads-auditor` agent is explicitly forbidden from calling mutation tools. It can only read data.

### Layer 4: Default PAUSED
`create_campaign` and `launch_campaign` always create campaigns in PAUSED state. Going live requires an explicit `set_campaign_status(status="ENABLED", confirm=true)`.

---

## Input Validation

All tools validate inputs before making API calls:

| Validator | What It Checks | Used By |
|-----------|---------------|---------|
| `validate_id(value, name)` | Must be numeric (regex `^\d+$`) | All tools with customer_id, campaign_id, etc. |
| `validate_status(value)` | Must be ENABLED, PAUSED, or REMOVED | set_campaign_status, set_ad_status, update_ad_group |
| `validate_date_range(value)` | Must be valid GAQL DURING value | All reporting tools |
| Enum allowlists | Strategy, device type, day of week, etc. | Per-tool validation |

## Logging & Monitoring

```
~/.burnr8/logs/
├── burnr8.log          # All tool calls with name, customer, duration, status
└── usage.json          # Daily ops counter, error counter, last 50 calls
```

Every tool call is logged automatically by the error decorator:
```
2026-04-04 18:32:15 INFO  tool=list_campaigns customer=637446 duration=0.8s status=ok rows=2
2026-04-04 18:31:42 ERROR tool=update_campaign customer=637446 duration=0.5s status=error request_id=xxx msg="..."
```

## File Map

```
burnr8/                          4,145 lines total
├── src/burnr8/
│   ├── __init__.py              (1)    Version: 0.4.0
│   ├── server.py                (289)  FastMCP + resources + prompts
│   ├── client.py                (21)   Google Ads client singleton
│   ├── helpers.py               (58)   GAQL runner + validators
│   ├── errors.py                (59)   Error decorator + logging
│   ├── logging.py               (86)   File logger + usage tracking
│   ├── dashboard.py             (145)  Terminal dashboard
│   └── tools/
│       ├── __init__.py          (29)   Tool registration
│       ├── accounts.py          (54)   3 tools
│       ├── campaigns.py         (369)  5 tools + bidding strategy engine
│       ├── ad_groups.py         (139)  3 tools
│       ├── ads.py               (161)  3 tools
│       ├── keywords.py          (202)  4 tools
│       ├── negative_keywords.py (248)  4 tools
│       ├── budgets.py           (162)  4 tools
│       ├── reporting.py         (249)  5 tools
│       ├── extensions.py        (355)  6 tools
│       ├── conversions.py       (250)  4 tools
│       ├── compound.py          (556)  3 compound tools
│       ├── adjustments.py       (512)  11 tools
│       └── goals.py             (200)  5 tools
├── .claude/
│   ├── agents/                  2 agents (ads-optimizer, ads-auditor)
│   ├── commands/                5 slash commands
│   └── settings.json            30 write tools gated with "ask"
├── tests/
│   └── test_helpers.py          27 tests
├── .github/
│   ├── workflows/ci.yml         CI pipeline
│   └── ISSUE_TEMPLATE/          Bug report + feature request
├── CLAUDE.md                    Project instructions for Claude
├── README.md                    User-facing documentation
├── CONTRIBUTING.md              Contribution guide
├── CHANGELOG.md                 Version history
├── CODE_OF_CONDUCT.md           Contributor Covenant
├── SECURITY.md                  Vulnerability reporting
├── LICENSE                      MIT
├── pyproject.toml               Package config + dependencies
└── setup_oauth.py               OAuth refresh token generator
```
