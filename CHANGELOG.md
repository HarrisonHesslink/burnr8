# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-04-05

### Added

- Multi-account management: `set_active_account_tool`, `get_active_account_tool`, `resolve_customer_id` fallback (BUR-8, BUR-9, BUR-10)
- 2 competitive insight tools: `get_competitive_metrics` (impression share, all accounts), `get_auction_insights` (competitor domains, requires allowlisting) (BUR-65)
- 4 new MCP prompts: `budget_reallocation`, `ad_copy`, `trends`, `competitors`
- 4 new slash commands: `/project:budget`, `/project:adcopy`, `/project:trends`, `/project:competitors`
- Business context awareness in agents — ask about business type and benchmarks before auditing (BUR-64)
- `test_competitive.py` with 8 tests for `_fmt_share`

### Changed

- Tool count: 63 → 65 (14 modules)
- Prompt count: 3 → 7
- Slash command count: 5 → 9

## [0.5.1] - 2026-04-05

### Added

- Claude Code plugin for one-click install via marketplace
- Pluggable report handler: `BURNR8_REPORT_MODE=disk|supabase` (BUR-48)
- Supabase Storage backend for cloud deployments

### Fixed

- Release script for branch protection (two-phase: PR then tag)

## [0.5.0] - 2026-04-04

### Added

- Docker image with multi-arch builds (amd64 + arm64)
- Docker Hub + GHCR publishing
- CSV export for all list/report tools (BUR-1 through BUR-7)
- CSV formula injection sanitization
- 7-day report auto-prune with throttling
- Report storage stats in `get_api_usage`

## [0.4.0] - 2026-04-04

### Added

- Location targeting tools (5 new tools)
- Search/display partner network settings for `update_campaign`
- CODE_OF_CONDUCT.md, SECURITY.md for open-source launch
- README badges, table of contents, FAQ section
- Production-ready documentation for public release

## [0.3.0] - 2026-04-04

### Added

- 5 conversion goal management tools
- 6 adjustment tools (pause keyword, device bids, ad schedules)

### Fixed

- `cleanup_wasted_spend` was dead code (never registered as MCP tool)
- `create_sitelink` writing `final_url` to wrong proto path
- `set_ad_schedule` rejecting `end_hour=24` (valid for end of day)
- Bidding strategy field masks setting $0 targets when no value provided
- Dashboard "ago" label

### Removed

- Always-null `tag_snippets` from conversion responses

### Changed

- Updated docs to reflect 55 tools / 13 categories

## [0.2.1] - 2026-04-04

### Fixed

- All bidding strategy field masks to use subfield paths
- `MAXIMIZE_CLICKS` mapped to `target_spend` (v23 equivalent)
- Budget creation with `explicitly_shared=false` for Smart Bidding

## [0.2.0] - 2026-04-04

### Added

- Version tracking (`get_api_usage` returns version)
- README.md and MIT LICENSE
- 3 compound tools (`quick_audit`, `launch_campaign`, `cleanup_wasted_spend`)
- MCP resources (2) and prompts (3)
- 5 slash commands
- 2 custom agent definitions (`ads-optimizer`, `ads-auditor`)
- Resource templates for account context
- Terminal dashboard and structured logging
- All 9 bidding strategies supported with target params
- EU political advertising support
- Permission rules for write operations

### Changed

- Renamed package to `burnr8`

## [0.1.0] - 2026-04-03

### Added

- Initial release
- 40 tools across 10 categories
- Accounts, campaigns, ad groups, ads, keywords, negative keywords, budgets, reporting, extensions, conversions
- Input validation on all parameters
- Confirmation gates on destructive operations
- OAuth setup script
- Google Ads API v23

[0.6.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.5.0...v0.6.0
[0.5.1]: https://github.com/harrisonhesslink/burnr8/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/harrisonhesslink/burnr8/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/harrisonhesslink/burnr8/releases/tag/v0.1.0
