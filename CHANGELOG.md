# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.1] - 2026-04-11

### Fixed

- **v30 mutate migration**: all 44 mutate calls now use request objects with `validate_only` on the request proto — fixes silent live mutations when `confirm=False` (#67)
- **Bidding strategy field masks**: `ManualCpc` uses subfield path `manual_cpc.enhanced_cpc_enabled`; `ManualCpm` correctly uses bare path (empty proto); `TargetSpend`, `MaximizeConversions`, `MaximizeConversionValue` always include subfield paths to avoid zeroing targets
- **Dict-to-Pydantic coercion**: `add_keywords`, `add_negative_keywords`, `add_ad_group_negative_keywords` now coerce raw dicts to model instances — fixes `AttributeError` when MCP sends JSON
- **`get_recent_errors_tool`**: validates `limit` param (rejects negative, non-numeric, float, null)

### Added

- **246 integration tests** across 13 files — reporting, negative keywords, ad groups, ads, budgets, campaigns, accounts, validate-only, destructive safety, new campaign safety, update campaign safety (BUR-218 through BUR-222)
- **Mandatory state verification**: all `confirm=True` mutations read back and assert persisted state
- **Claude Code dev hooks**: pre-push safety gates for development workflow (#68)
- **CLAUDE.md gotchas**: documented v30 mutate pattern, `or` with empty collections, `start_date`/`end_date` removal (#69)

### Changed

- **CI**: bumped docker/build-push-action v7, docker/login-action v4, docker/setup-qemu-action v4, docker/setup-buildx-action v4, astral-sh/setup-uv v7 (#72–#76)
- Integration test infrastructure: shared `register_tool()` helper, `_reset_session` fixture resets active account between tests

## [0.7.0] - 2026-04-10

### Added

- **Financial circuit breakers**: 5 configurable hard-caps (daily budget, CPC bid, bid modifier, target CPA, target ROAS) with NaN/Inf protection and env-var overrides (`BURNR8_MAX_*`)
- **Thread-local tenant isolation**: Session state migrated to `contextvars.ContextVar` for safe concurrent request handling
- **Dry-run validation**: `validate_only=not confirm` pattern across all mutating tools — server-side validation before execution
- **GAQL injection prevention**: `escape_gaql_string()` and `validate_gaql_query()` with cross-tenant ID detection and DML blocklist
- **Tracking URL support**: `tracking_url_template`, `final_url_suffix`, `url_custom_parameters` on campaigns, ad groups, ads, keywords (#52)
- **Keyword power tools**: bulk operations, quality score filtering, bid recommendations (#53)
- **RSA pinning**: headline/description pin positions, display paths, ad policy details (#54)
- **Smart Bidding for launch_campaign**: all 9 bidding strategies with target params (#55)
- **Conversion validation**: goal name resolution, status filtering (#56)
- **Property-based fuzzing suite**: Hypothesis tests for financial validators, GAQL gatekeeper, CSV sanitization
- **29 unit tests** for financial circuit breaker validators
- **Pre-commit hooks**, semgrep security rules, mypy strict mode (0 errors)
- Internal `remove_campaign` tool for test cleanup (#59)

### Changed

- **CI modernized**: switched to `uv` for ~10x faster installs, pip cache on all jobs, lockfile for 3.12 reproducibility
- **Setup simplified**: removed OAuth flow, added docs link and cloud CTA (#61)
- **CWD `.env` loading removed**: credentials only from `~/.burnr8/.env` to prevent injection via malicious repo clones
- Tool count: 65 → 66 (14 modules)

### Fixed

- `IndexError` handler added to error decorator — protects 34 `response.results[0]` call sites (#60)
- Null/type validation on `validate_status` and `validate_date_range` (#60)
- Campaign param validation (`target_cpa_dollars`, `max_cpc_bid_ceiling_dollars`, `target_roas`) (#60)
- `set_campaign_status` no longer accepts REMOVED (must use `remove_campaign`) (#59)
- `validate_budget_amount` allows $0 budgets (valid for pausing spend) (#62)
- `validate_daily_budget` 0 vs 0.0 inconsistency fixed
- cryptography bumped to 46.0.7 (CVE-2026-39892)

### Security

- Financial validators reject NaN, Infinity, and negative values
- `set_financial_limits()` validates inputs before storing
- Env var parsing fails fast with clear error messages on bad values
- Atomic file writes for credential storage

## [0.6.1] - 2026-04-06

### Fixed

- Reliability and error handling improvements
- Dashboard exception handling
- Test hardening and coverage expansion
- Repository hygiene: version sync, pre-commit config

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

[0.7.1]: https://github.com/harrisonhesslink/burnr8/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/harrisonhesslink/burnr8/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.5.0...v0.6.0
[0.5.1]: https://github.com/harrisonhesslink/burnr8/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/harrisonhesslink/burnr8/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/harrisonhesslink/burnr8/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/harrisonhesslink/burnr8/releases/tag/v0.1.0
