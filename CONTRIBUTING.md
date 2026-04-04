# Contributing to burnr8

Thanks for wanting to help! burnr8 is an open-source Google Ads MCP server.

## Quick Start

```bash
git clone https://github.com/HarrisonHesslink/burnr8.git
cd burnr8
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Making Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add tests if you're adding new helpers or validators
4. Run `pytest tests/ -v` to make sure tests pass
5. Run `PYTHONPATH=src python -c "from burnr8.server import mcp"` to verify imports
6. Submit a PR

## Adding a New Tool

Tools live in `src/burnr8/tools/`. Follow these patterns:

- Use `@mcp.tool` then `@handle_google_ads_errors` decorators (in that order)
- Validate all IDs with `validate_id(value, name)`
- Validate enum inputs against allowlists
- Use `Annotated[type, Field(description="...")]` for all parameters
- Destructive operations need `confirm: bool = False` parameter
- Return plain dicts/lists, not protobuf
- Convert micros to dollars in responses
- Add the tool to `tools/__init__.py`
- Add write tools to `.claude/settings.json` under `"ask"`

## Testing

We use pytest. Tests are in `tests/`. Currently testing helpers and validators — contributions to expand test coverage are welcome.

```bash
pytest tests/ -v
```

## Google Ads API Notes

- We use API v23 via the `google-ads` Python client library
- GAQL queries go through `run_gaql()` in `helpers.py`
- Metric fields are NOT filterable in GAQL WHERE clauses — filter in Python
- Field masks must use leaf-level paths for strategies with subfields
- `proto_to_dict()` converts protobuf responses to plain dicts

## Code Style

- Python 3.11+
- No external linter enforced — just keep it consistent with existing code
- Imports from `burnr8.*`

## Reporting Issues

Use GitHub Issues. Include:
- What you were trying to do
- The error message or unexpected behavior
- Your Python version and `burnr8` version (`get_api_usage` tool shows the version)
