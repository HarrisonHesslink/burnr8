# burnr8

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tools](https://img.shields.io/badge/MCP_tools-115-green.svg)]()
[![CI](https://github.com/HarrisonHesslink/burnr8/actions/workflows/ci.yml/badge.svg)](https://github.com/HarrisonHesslink/burnr8/actions)
[![PyPI](https://img.shields.io/pypi/v/burnr8)](https://pypi.org/project/burnr8/)
[![Docker](https://img.shields.io/badge/docker-hub-blue?logo=docker)](https://hub.docker.com/r/harrisonhesslink/burnr8)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-Support-orange?logo=buy-me-a-coffee)](https://buymeacoffee.com/harrisonhesslink)

**Connect paid media and organic search intelligence from your terminal.**

> **Want zero setup?** The hosted version at [burnrate.sh](https://burnrate.sh) handles credentials for you — connect Google Ads via OAuth, get an MCP endpoint, done. [Join the waitlist →](https://burnrate.sh)

## Table of Contents

- [What You Can Do](#what-you-can-do)
- [Meta Reels Quick Start](#meta-reels-quick-start)
- [Reddit Ads Quick Start](#reddit-ads-quick-start)
- [SEO Intelligence Quick Start](#seo-intelligence-quick-start)
- [Installation](#installation)
- [Terminal Dashboard](#terminal-dashboard)
- [Custom Agents](#custom-agents)
- [Slash Commands](#slash-commands)
- [MCP Resources & Prompts](#mcp-resources--prompts)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [FAQ](#faq)
- [License](#license)

burnr8 is an MCP server that gives [Claude Code](https://claude.ai/code) control over Google Ads, Meta campaign creation/management/reporting, Reddit Ads, and first-party SEO intelligence. Its 115 tools cover paid campaigns plus Search Console, URL Inspection, sitemaps, PageSpeed/CrUX, bounded site audits, and paid/organic demand gaps. Includes 2 custom agents, 9 slash commands, 7 prompt templates, and MCP resources.

> This is an unofficial tool and is not affiliated with or endorsed by Google, Meta, or Reddit.

## What You Can Do

```
You:    "Audit my Google Ads account"
Claude: *pulls performance data, keywords, search terms, extensions, conversion actions*
        *identifies $200/month in wasted spend on free-intent keywords*
        *recommends negative keywords, pausing underperformers, fixing conversion tracking*

You:    "Add 'free' as a phrase match negative keyword"
Claude: Done. Estimated savings: ~$55/month.

You:    "Find StudyWithLily SEO opportunities and compare them with paid search demand"
Claude: *joins Search Console queries to Google Ads search terms*
        *ranks striking-distance pages, CTR gaps, and paid terms with weak organic visibility*
```

### 115 Tools Across 17 Categories

| Category | Tools | What They Do |
|----------|-------|-------------|
| **Accounts** | 6 | List/select accounts, get account info, inspect API usage and recent errors |
| **Campaigns** | 5 | List, create, update, pause/enable campaigns |
| **Ad Groups** | 3 | List, create, update ad groups |
| **Ads** | 3 | List ads (with ad strength), create RSAs, set status |
| **Keywords** | 5 | List, add, update, remove keywords; keyword research with volumes |
| **Negative Keywords** | 4 | List, add (campaign + ad group level), remove negatives |
| **Budgets** | 4 | List, create, update, delete campaign budgets |
| **Reporting** | 5 | Campaign/ad group/keyword performance, search terms, raw GAQL — all save full results to CSV |
| **Extensions** | 6 | List account/campaign/ad-group assets; create sitelinks at all three levels; remove links |
| **Conversions** | 4 | List, get, create, update conversion actions |
| **Compound** | 3 | `quick_audit`, `launch_campaign`, `cleanup_wasted_spend` — multi-step operations in one call |
| **Adjustments** | 11 | Pause keywords, device bids, ad schedules, location targeting, geo presence settings |
| **Goals** | 5 | List/set conversion goals, campaign-level goal config, custom conversion goals |
| **Competitive** | 2 | Impression share metrics, auction insights (competitor domains) |
| **Meta Ads** | 14 | Accounts/assets, photo Reels creation, campaign/ad-set/ad inventory, Insights, previews, status, and budgets |
| **SEO Intelligence** | 12 | Search Console performance/comparisons/opportunities, URL Inspection, sitemaps, PageSpeed/CrUX, bounded crawling, paid/organic demand gaps |
| **Reddit Ads** | 23 | Account/profile/pixel discovery and event diagnostics, community search, reports, media imports, image/video ad posts, paused campaigns/ad groups/ads, status and budgets |

### Custom Agents

- **`ads-optimizer`** — Finds and fixes wasted ad spend, recommends negative keywords, pauses underperformers
- **`ads-auditor`** — Runs a full account audit with health scoring and prioritized action items

### Slash Commands

| Command | What It Does |
|---------|-------------|
| `/project:audit` | Full account audit |
| `/project:spend` | Spend analysis |
| `/project:waste` | Wasted spend report |
| `/project:launch` | Launch a new campaign |
| `/project:status` | Account status check |
| `/project:competitors` | Competitive positioning analysis |
| `/project:budget` | Budget reallocation recommendations |
| `/project:adcopy` | Generate new RSA ad variations |
| `/project:trends` | Week-over-week performance trends |

### MCP Resources & Prompts

**Resources** — auto-loaded context for Claude:
- `burnr8://usage` — current API usage stats
- `burnr8://accounts` — list of accessible accounts
- `burnr8://accounts/{id}/performance` — 30-day campaign performance
- `burnr8://accounts/{id}/keywords` — keyword health summary
- `burnr8://accounts/{id}/structure` — account structure overview

**Prompts** — guided workflows:
- `audit` — run a complete account audit
- `optimize` — find and fix wasted spend
- `new_campaign` — plan and launch a new search campaign
- `competitors` — competitive positioning analysis
- `budget_reallocation` — optimize budget distribution
- `ad_copy` — generate new RSA ad variations
- `trends` — detect week-over-week performance changes

### Safety Built In

- Destructive operations require `confirm=true` — no accidental campaign enables or keyword deletions
- New campaigns always start **PAUSED**
- `run_gaql_query` is a read-only escape hatch for any Google Ads data
- All inputs validated (IDs must be numeric, statuses allowlisted, date ranges checked)
- API usage tracked with 15,000 ops/day rate limit awareness
- CSV reports saved with formula injection sanitization and `0o600` permissions
- **Thread Safety**: ContextVars isolate session state per-request, preventing tenant leakage in concurrent environments
- **Financial Circuit Breakers**: Configurable hard-caps enforced at the point of mutation (budgets, bids, modifiers, ROAS/CPA targets)
- Meta uploads, delivery changes, and budget changes require `confirm=true`; new Meta campaign objects start **PAUSED**
- Meta object mutations verify ad-account ownership before writing and read the object back afterward; deletion is not exposed
- Sitemap submission requires `confirm=true`; all other SEO tools are read-only
- SEO crawling stays on the starting host, rejects non-public IPs, validates every redirect, respects `robots.txt` by default, and enforces page/depth/response caps

## Meta Reels Quick Start

The first Meta workflow creates a USD traffic campaign restricted to Facebook Reels and Instagram Reels on mobile. Pass one to ten local JPEG/PNG paths and Burnr8 uploads each photo, then creates one creative and one paused ad per photo under a shared paused campaign and ad set.

Run `burnr8-setup` and enter a Meta access token with `ads_management` permission. These values are stored in `~/.burnr8/.env` with `0600` permissions:

```dotenv
META_ACCESS_TOKEN=your-meta-access-token
META_APP_SECRET=your-meta-app-secret
META_AD_ACCOUNT_ID=123456789012345
META_GRAPH_API_VERSION=v25.0
BURNR8_MEDIA_ROOT=/absolute/path/to/approved/ad-photos
```

Then ask Claude to:

1. Call `meta_list_ad_accounts` and `meta_set_active_ad_account`.
2. Call `meta_get_account_assets` to find the Facebook Page ID and connected Instagram account ID.
3. Call `meta_create_reels_campaign` with `confirm=false` to validate the plan and photos locally.
4. Review the plan, then repeat with `confirm=true` to upload and create the paused objects.

Photos must be JPEG or PNG, at most 30 MB, and located beneath `BURNR8_MEDIA_ROOT`. A 9:16 image is recommended; other ratios are accepted with a crop/padding warning. The campaign creator never enables the resulting campaign—review it in Meta Ads Manager or use the guarded status tools before turning on delivery.

### Meta Operations

The management layer can inspect and operate existing campaigns without recreating them:

1. Use `meta_list_campaigns`, `meta_list_ad_sets`, and `meta_list_ads` to inspect configured and effective delivery state. Collection tools use bounded cursor pagination and return `next_after` rather than Meta's token-bearing next-page URL.
2. Use `meta_get_insights` for account, campaign, ad-set, or ad reporting. It returns spend, reach, clicks, cost metrics, raw action arrays, and keyed `*_by_type` action maps. Date presets, custom dates, daily/monthly increments, and up to three allowlisted breakdowns are supported.
3. Use `meta_get_ad_preview` to request Meta-rendered Feed, Stories, Facebook Reels, or Instagram Reels preview markup.
4. Dry-run `meta_set_campaign_status`, `meta_set_ad_set_status`, or `meta_set_ad_status`, then repeat with `confirm=true` to apply an `ACTIVE` or `PAUSED` state. Delete/archive states are deliberately unavailable.
5. Dry-run `meta_update_ad_set_budget`, then repeat with `confirm=true`. It only changes existing USD ad-set daily budgets, applies the global daily-budget circuit breaker, warns on changes over 30%, and verifies the saved amount.

Meta-reported conversions use the ad account's attribution settings. Compare them with first-party analytics before making allocation decisions.

## Reddit Ads Quick Start

Create an app in Reddit Ads Manager → Business → Developer Portal, with the redirect URL `http://localhost:8765/callback`. Then run `burnr8-reddit-setup` on the same machine as your browser. It authorizes `adsread`/`adsedit` and saves the refresh token privately to `~/.burnr8/.env`, preserving other providers.

Restart the MCP server, call `reddit_list_businesses` and `reddit_list_ad_accounts`, and select `REDDIT_AD_ACCOUNT_ID` or pass `account_id` on each call. No Google or Meta credentials are needed for Reddit.

Reddit campaigns, ad groups and ads start paused. Writes default to previews; saved objects and asynchronous media/post jobs have verification steps. Import images/videos from public HTTPS URLs, create an ad post, then attach it to a paused ad with a placement preview link. Conversion-event forwarding remains separate. See the [Reddit setup, complete creation workflow, budget controls and reporting guide](docs/reddit-ads.md).

## SEO Intelligence Quick Start

Burnr8 combines four evidence sources instead of treating “SEO” as one opaque score:

- **Search Console** — first-party queries, pages, clicks, impressions, CTR, average position, index state, and sitemaps
- **PageSpeed + CrUX** — Lighthouse lab diagnostics plus optional real-user field data from the standalone CrUX API
- **Bounded crawler** — static-HTML titles, descriptions, canonicals, headings, robots directives, images, links, duplicates, and static JSON-LD
- **Google Ads** — `search_demand_gap` joins paid search terms to organic queries without changing campaign delivery

Enable the [Search Console API](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing) in the Google Cloud project for your OAuth client, then create a separate refresh token authorized for `https://www.googleapis.com/auth/webmasters.readonly`. Use `https://www.googleapis.com/auth/webmasters` only if Burnr8 should be allowed to submit sitemaps. The Search Console client can reuse the Google Ads OAuth client ID and secret, but it deliberately does not reuse the Ads refresh token because the scopes differ. Enable the PageSpeed Insights API and Chrome UX Report API in the key's project if you configure those optional keys.

```dotenv
GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN=your-search-console-refresh-token
GOOGLE_SEARCH_CONSOLE_PROPERTY=sc-domain:studywithlily.com

# Optional; otherwise GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET are reused
GOOGLE_SEARCH_CONSOLE_CLIENT_ID=your-oauth-client-id
GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET=your-oauth-client-secret

# Recommended for reliable PageSpeed quota; required for standalone CrUX field data
GOOGLE_PAGESPEED_API_KEY=your-google-api-key
GOOGLE_CRUX_API_KEY=your-google-api-key
```

Then ask Claude to:

1. Call `gsc_list_properties`, then `gsc_set_active_property`.
2. Call `gsc_search_performance`, `gsc_compare_periods`, or `gsc_find_opportunities` for first-party organic evidence.
3. Call `gsc_inspect_url` for a specific index diagnosis and `gsc_list_sitemaps` for sitemap state.
4. Call `pagespeed_analyze`, `seo_audit_url`, or `seo_crawl_site` for performance and technical checks.
5. Call `search_demand_gap` to combine the selected property with the active Google Ads account.

`gsc_submit_sitemap` is a dry run until `confirm=true`. Burnr8 intentionally does not expose Google’s general Indexing API because it is limited to job posting and livestream pages, and it does not ship an unrestricted Google results/competitor-rank tool. Google’s official Custom Search JSON API is closed to new customers; a future live-SERP feature should use an explicit third-party provider adapter.

The crawler fetches static HTML and does not execute JavaScript. Its `static_json_ld_blocks=0` result is therefore not proof that rendered schema is absent; use Search Console rich-result findings or a rendered test for confirmation.

### CSV Report Export

All reporting tools save full results to `~/.burnr8/reports/` as CSV files and return a compact summary to Claude's context instead of dumping thousands of rows. Claude can `Read` the CSV for deeper analysis when needed.

- Files auto-pruned after 7 days
- Formula injection sanitized (Excel/LibreOffice safe)
- Storage stats visible via `get_api_usage` and `burnr8` dashboard

---

## Installation

### Prerequisites

- Python 3.11+
- A Google Ads account
- A [Google Ads API developer token](https://developers.google.com/google-ads/api/docs/get-started/dev-token) (Basic Access)
- OAuth2 credentials (client ID + secret) from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- For Meta tools only: a Meta app/access token with `ads_management`, a Meta ad account, a Facebook Page, and a connected Instagram account
- For Search Console tools only: Search Console API access and a refresh token with `webmasters.readonly` (or `webmasters` for sitemap submission)

### Option A: Claude Code Plugin (recommended)

Add to your `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "burnr8": {
      "source": {"source": "github", "repo": "HarrisonHesslink/burnr8"},
      "autoUpdate": true
    }
  }
}
```

Then run `/plugin` in Claude Code and enable **burnr8**. This auto-configures the MCP server, agents, commands, and audit skill. You still need to `pip install burnr8` and set up credentials (see below).

### Option B: pip/uv install

```bash
uv pip install burnr8
# or: pip install burnr8
```

### Option C: Docker (no Python needed)

```bash
docker pull harrisonhesslink/burnr8          # Docker Hub
# or
docker pull ghcr.io/harrisonhesslink/burnr8  # GitHub Container Registry
```

Add to `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "burnr8": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GOOGLE_ADS_DEVELOPER_TOKEN",
        "-e", "GOOGLE_ADS_CLIENT_ID",
        "-e", "GOOGLE_ADS_CLIENT_SECRET",
        "-e", "GOOGLE_ADS_REFRESH_TOKEN",
        "-e", "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        "-e", "META_ACCESS_TOKEN",
        "-e", "META_APP_SECRET",
        "-e", "META_AD_ACCOUNT_ID",
        "-e", "BURNR8_MEDIA_ROOT=/ad-media",
        "-e", "GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN",
        "-e", "GOOGLE_SEARCH_CONSOLE_PROPERTY",
        "-e", "GOOGLE_PAGESPEED_API_KEY",
        "-e", "GOOGLE_CRUX_API_KEY",
        "-v", "/absolute/path/to/ad-photos:/ad-media:ro",
        "ghcr.io/harrisonhesslink/burnr8"
      ]
    }
  }
}
```

Set your credentials as environment variables in your shell, or use `--env-file .env` instead of individual `-e` flags.

### Option C: Clone and install

```bash
git clone https://github.com/HarrisonHesslink/burnr8.git
cd burnr8
uv venv .venv
source .venv/bin/activate
uv pip install -e .
```

### 2. Set Up Credentials

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```
GOOGLE_ADS_DEVELOPER_TOKEN=your-developer-token
GOOGLE_ADS_CLIENT_ID=your-oauth-client-id
GOOGLE_ADS_CLIENT_SECRET=your-oauth-client-secret
GOOGLE_ADS_REFRESH_TOKEN=your-refresh-token
GOOGLE_ADS_LOGIN_CUSTOMER_ID=your-mcc-id (optional, for manager accounts)

# Optional: Search Console / SEO intelligence
GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN=your-search-console-refresh-token
GOOGLE_SEARCH_CONSOLE_PROPERTY=sc-domain:example.com
GOOGLE_PAGESPEED_API_KEY=your-google-api-key
GOOGLE_CRUX_API_KEY=your-google-api-key

# Optional: Financial Circuit Breakers
BURNR8_MAX_DAILY_BUDGET_DOLLARS=10000
BURNR8_MAX_CPC_BID_DOLLARS=100
BURNR8_MAX_BID_MODIFIER=5.0
BURNR8_MAX_TARGET_CPA_DOLLARS=500
BURNR8_MIN_TARGET_ROAS=0.5
```

**Don't have a refresh token?** Follow [Google's OAuth documentation](https://developers.google.com/identity/protocols/oauth2) to authorize the required API scope, then run `burnr8-setup` to save the resulting token. Google Ads and Search Console should use separate refresh tokens because their scopes differ.

### 3. Register with Claude Code

Add burnr8 as a global MCP server so it's available in all Claude Code sessions:

```bash
claude mcp add --scope user --transport stdio burnr8 \
  --env PYTHONPATH=$(pwd)/src \
  -- $(pwd)/.venv/bin/python -m burnr8.server
```

Or manually create/edit `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "burnr8": {
      "type": "stdio",
      "command": "/path/to/burnr8/.venv/bin/python",
      "args": ["-m", "burnr8.server"],
      "cwd": "/path/to/burnr8",
      "env": {
        "PYTHONPATH": "/path/to/burnr8/src"
      }
    }
  }
}
```

### 4. Restart Claude Code

```bash
claude
```

You should see `burnr8` tools available. Test with:

```
list_accessible_accounts
```

---

## Terminal Dashboard

Check your API usage, recent tool calls, and campaign spend:

```bash
burnr8
```

```
  burnr8 Dashboard
  2026-04-04 03:26 UTC
  --------------------------------------------------

  API Ops Today:    142 / 15,000  [##------------------]  0.9%
  Errors (24h):     2
  Last Tool Call:   get_campaign_performance (3m ago)

  Campaign Spend:
    My Campaign:
      Today:  $48.21 / $150.00 budget  |  74 clicks  |  12 conv
      MTD:    $1,612.00
```

---

## How Google Ads API Access Works

1. **Create a Google Ads manager account** (if you don't have one) at [ads.google.com](https://ads.google.com)
2. **Get a developer token** from the API Center in your manager account (Tools > API Center)
3. **Create OAuth2 credentials** in [Google Cloud Console](https://console.cloud.google.com/apis/credentials) — choose "Desktop app"
4. **Enable the Google Ads API** in your GCP project
5. **Apply for Basic Access** — allows 15,000 operations/day on live accounts

Your developer token starts with Test Account Access. Apply for Basic Access to manage live accounts.

---

## Project Structure

```
burnr8/
├── src/burnr8/
│   ├── server.py          # FastMCP entry point (resources, prompts)
│   ├── client.py          # Google Ads client (lazy singleton)
│   ├── helpers.py         # GAQL runner, validators, converters
│   ├── errors.py          # Error handling + logging decorator
│   ├── logging.py         # Structured logging + rate limit tracking
│   ├── reports.py         # CSV export + sanitization + storage stats
│   ├── dashboard.py       # Terminal dashboard
│   ├── meta/              # Meta Graph client, session state, media safety
│   ├── seo/               # Search Console REST clients, analysis, safe crawler
│   └── tools/             # 115 MCP tools across 19 modules
│       ├── accounts.py
│       ├── campaigns.py
│       ├── ad_groups.py
│       ├── ads.py
│       ├── keywords.py
│       ├── negative_keywords.py
│       ├── budgets.py
│       ├── reporting.py
│       ├── extensions.py
│       ├── conversions.py
│       ├── compound.py
│       ├── adjustments.py
│       ├── goals.py
│       ├── competitive.py
│       ├── meta_ads.py
│       ├── meta_management.py
│       └── seo.py
├── .claude/
│   ├── agents/            # 2 custom agents (ads-optimizer, ads-auditor)
│   └── commands/          # 9 slash commands
├── .env.example           # Credential template
└── pyproject.toml
```

---

## Contributing

PRs welcome. Some areas that would be great to expand:

- **Display campaigns** — create/manage display ads
- **Performance Max** — asset groups, audience signals, search themes
- **YouTube ads** — video campaign management
- **Audience targeting** — remarketing lists, customer match
- **Location bid adjustments** — geographic bid modifiers
- **Tests** — unit tests for logic/helpers, integration tests with active test accounts (test account agnostic)

---

## FAQ

**Do I need a Google Ads manager (MCC) account?**
No. burnr8 works with both individual Google Ads accounts and manager accounts. Set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` only if you use a manager account.

**What Google Ads API access level do I need?**
Basic Access (15,000 operations/day). This is sufficient for most use cases. Apply through the API Center in your Google Ads account.

**Does this work with Claude Desktop or just Claude Code?**
burnr8 is an MCP server that uses stdio transport. It works with Claude Code and any MCP client that supports stdio servers.

**Can I use this with accounts I manage for clients?**
Yes. Use your manager account's `LOGIN_CUSTOMER_ID` and pass the client's `customer_id` to each tool call.

**Will this accidentally spend my money?**
No. All write operations require user approval (via Claude Code permission rules). Campaign creation always starts PAUSED. Destructive operations require `confirm=true`.

**What happens if I hit the API rate limit?**
burnr8 tracks usage via `get_api_usage`. At 15,000 ops/day with Basic Access, most users won't hit the limit. The dashboard shows current usage.

---

## Support

If burnr8 saved you money on Google Ads, consider buying me a coffee.

<a href="https://buymeacoffee.com/harrisonhesslink" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50"></a>

## License

MIT
