# Contributing to burnr8

Thanks for your interest in contributing. burnr8 is an open-source Google Ads MCP server built with FastMCP.

## Quick Start

```bash
git clone https://github.com/HarrisonHesslink/burnr8.git
cd burnr8
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pre-commit install
pytest tests/ -v
```

## Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting/formatting and [mypy](https://mypy-lang.org/) for strict type checking.

```bash
ruff check src/ tests/        # Lint (includes security checks)
ruff format src/ tests/        # Format
mypy src/                      # Strict type check
```

No manual formatting needed — ruff handles everything. Run it before committing.

## Adding a New Tool

Tools live in `src/burnr8/tools/`. Each module exports a `register(mcp)` function. Follow this pattern:

```python
from typing import Annotated
from pydantic import Field, validate_call
from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id, validate_cpc_bid
from burnr8.session import resolve_customer_id

def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    @validate_call
    def my_new_tool(
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID")] = None,
        cpc_bid: Annotated[float, Field(description="Max CPC bid")] = 1.0,
    ) -> dict:
        """One-line description of what this tool does."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id and no active account set."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        rows = run_gaql(client, customer_id, "SELECT ... FROM ...")
        return {"results": rows}
```

Checklist for new tools:
- Decorators: `@mcp.tool` → `@handle_google_ads_errors` → `@validate_call` (strict order)
- Validate IDs with `validate_id(value, name)`
- Enforce financial circuit breakers with `validate_cpc_bid()`, `validate_daily_budget()`, etc.
- Use `resolve_customer_id()` for active account fallback
- Use `Annotated[type, Field(description="...")]` for all parameters
- Destructive tools: add `confirm: Annotated[bool, Field(...)] = False` guard
- Convert micros to dollars in responses (`cost / 1_000_000`)
- Return plain dicts, not protobuf objects
- Register in `tools/__init__.py`
- Add write tools to `.claude/settings.json` under `"ask"` permissions
- Update tool count in `tests/test_server.py`

## Running Tests and CI Locally

```bash
pytest tests/ -v                # Run all tests
ruff check src/ tests/          # Lint check
./scripts/ci-local.sh           # Full CI pipeline (lint + security + tests + build)
```

The local CI script runs the same checks as GitHub Actions: ruff, pip-audit, pytest, and build verification.

## PR Process

1. Fork the repo and branch from `main`
2. Use descriptive branch names: `feat/add-audience-tools`, `fix/budget-validation`
3. Run `./scripts/ci-local.sh` before pushing
4. Open a PR against `main`
5. CI runs: lint, security scan, tests (3.11/3.12/3.13), build check

Keep PRs focused. One feature or fix per PR.

## Google Ads API Notes

- We use API v23 via the `google-ads` Python client library
- All queries go through `run_gaql()` in `helpers.py`
- Metric fields are NOT filterable in GAQL WHERE clauses — filter in Python after querying
- Field masks must use leaf-level paths for strategies with subfields (see Gotchas in CLAUDE.md)
- `proto_to_dict()` converts protobuf responses to plain dicts

## Areas That Need Help

- **Performance Max** — asset groups, audience signals, search themes
- **Audience targeting** — remarketing lists, customer match
- **Shopping campaigns** — product feeds, listing groups
- **Display campaigns** — managed placements, responsive display ads
- **YouTube/Video** — video campaign management
- **Automated rules** — scheduled bid/budget changes
- **Unit Test coverage** — unit tests for individual tool modules
- **Integration Test coverage** — integration tests for individual tool modules using google ads test accounts

## Reporting Issues

Use [GitHub Issues](https://github.com/HarrisonHesslink/burnr8/issues). Include:
- What you were trying to do
- The error message or unexpected behavior
- Your Python version and burnr8 version (`get_api_usage` shows the version)
