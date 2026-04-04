# burnr8

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tools](https://img.shields.io/badge/MCP_tools-60-green.svg)]()
[![CI](https://github.com/HarrisonHesslink/burnr8/actions/workflows/ci.yml/badge.svg)](https://github.com/HarrisonHesslink/burnr8/actions)
[![Version](https://img.shields.io/badge/version-0.4.0-blue.svg)]()
[![Docker](https://img.shields.io/badge/docker-hub-blue?logo=docker)](https://hub.docker.com/r/harrisonhesslink/burnr8)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-Support-orange?logo=buy-me-a-coffee)](https://buymeacoffee.com/harrisonhesslink)

**Stop burning money on Google Ads. Manage everything from your terminal.**

> **Want zero setup?** The hosted version at [burnrate.sh](https://burnrate.sh) handles credentials for you — connect Google Ads via OAuth, get an MCP endpoint, done. [Join the waitlist →](https://burnrate.sh)

## Table of Contents

- [What You Can Do](#what-you-can-do)
- [Installation](#installation)
- [Terminal Dashboard](#terminal-dashboard)
- [Custom Agents](#custom-agents)
- [Slash Commands](#slash-commands)
- [MCP Resources & Prompts](#mcp-resources--prompts)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [FAQ](#faq)
- [License](#license)

burnr8 is an MCP server that gives [Claude Code](https://claude.ai/code) full control over Google Ads. 60 tools across 13 categories for managing campaigns, keywords, budgets, ads, extensions, conversion tracking, bid adjustments, ad scheduling, conversion goals, and reporting — all from your CLI. Includes 2 custom agents, 5 slash commands, MCP resources, and prompt templates.

> This is an unofficial tool and is not affiliated with or endorsed by Google.

## What You Can Do

```
You:    "Audit my Google Ads account"
Claude: *pulls performance data, keywords, search terms, extensions, conversion actions*
        *identifies $200/month in wasted spend on free-intent keywords*
        *recommends negative keywords, pausing underperformers, fixing conversion tracking*

You:    "Add 'free' as a phrase match negative keyword"
Claude: Done. Estimated savings: ~$55/month.
```

### 55 Tools Across 13 Categories

| Category | Tools | What They Do |
|----------|-------|-------------|
| **Accounts** | 3 | List accounts, get info, check API usage |
| **Campaigns** | 5 | List, create, update, pause/enable campaigns |
| **Ad Groups** | 3 | List, create, update ad groups |
| **Ads** | 3 | List ads (with ad strength), create RSAs, set status |
| **Keywords** | 4 | List, add, remove keywords; keyword research with volumes |
| **Negative Keywords** | 4 | List, add (campaign + ad group level), remove negatives |
| **Budgets** | 4 | List, create, update, delete campaign budgets |
| **Reporting** | 5 | Campaign/ad group/keyword performance, search terms, raw GAQL — all save full results to CSV |
| **Extensions** | 6 | List, create sitelinks/callouts/snippets/images, remove |
| **Conversions** | 4 | List, get, create, update conversion actions |
| **Compound** | 3 | `quick_audit`, `launch_campaign`, `cleanup_wasted_spend` — multi-step operations in one call |
| **Adjustments** | 11 | Pause keywords, device bids, ad schedules, location targeting, geo presence settings |
| **Goals** | 5 | List/set conversion goals, campaign-level goal config, custom conversion goals |

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

### Safety Built In

- Destructive operations require `confirm=true` — no accidental campaign enables or keyword deletions
- New campaigns always start **PAUSED**
- `run_gaql_query` is a read-only escape hatch for any Google Ads data
- All inputs validated (IDs must be numeric, statuses allowlisted, date ranges checked)
- API usage tracked with 15,000 ops/day rate limit awareness
- CSV reports saved with formula injection sanitization and `0o600` permissions

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

### Option A: pip install

```bash
pip install burnr8
```

### Option B: Docker (no Python needed)

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
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
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
```

**Don't have a refresh token?** Run the included OAuth helper:

```bash
python setup_oauth.py
```

It will open a browser for Google login and print your refresh token.

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
│   └── tools/             # 60 MCP tools
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
│       └── goals.py
├── .claude/
│   ├── agents/            # 2 custom agents (ads-optimizer, ads-auditor)
│   └── commands/          # 5 slash commands (audit, spend, waste, launch, status)
├── setup_oauth.py         # OAuth refresh token generator
├── .env.example           # Credential template
└── pyproject.toml         # v0.4.0
```

---

## Contributing

PRs welcome. Some areas that would be great to expand:

- **Display campaigns** — create/manage display ads
- **Performance Max** — asset groups, audience signals, search themes
- **YouTube ads** — video campaign management
- **Audience targeting** — remarketing lists, customer match
- **Location bid adjustments** — geographic bid modifiers
- **Tests** — unit tests for helpers, integration tests with test accounts

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
