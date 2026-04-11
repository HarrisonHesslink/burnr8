"""Shared integration test fixtures — e2e Google Ads client tests."""

import logging
import os
import time
from importlib import import_module
from typing import Any

import pytest
from dotenv import load_dotenv

logging.getLogger("google.ads.googleads").setLevel(logging.CRITICAL)
load_dotenv(".env.local")


INVALID_CUSTOMER_IDS = [
    ("letters", "abc"),
    ("dashes", "123-456-789"),
    ("empty", ""),
    ("special_chars", "123!@#456"),
    ("spaces", "123 456"),
]


def register_tool(tool_name: str, module_name: str):
    """Register a tool from a burnr8 module and return the callable.

    Usage: tool = register_tool("create_budget", "budgets")
    """
    mod = import_module(f"burnr8.tools.{module_name}")
    captured: dict = {}

    class _Capture:
        def tool(self, fn):  # type: ignore[no-untyped-def]
            if fn.__name__ == tool_name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    mod.register(cap)
    if "func" not in captured:
        raise ValueError(f"Tool '{tool_name}' not found in burnr8.tools.{module_name}")
    return captured["func"]


def retry_on_concurrent(fn, *args: Any, retries: int = 3, delay: float = 1.0, **kwargs: Any) -> dict:
    """Retry a tool call if Google Ads returns CONCURRENT_MODIFICATION.

    This happens when a validate_only (dry-run) request and a real mutate
    hit the same resource back-to-back before the API releases its lock.
    """
    for attempt in range(retries):
        result = fn(*args, **kwargs)
        is_concurrent = isinstance(result, dict) and "CONCURRENT_MODIFICATION" in str(result.get("errors", ""))
        if is_concurrent and attempt < retries - 1:
            time.sleep(delay * (attempt + 1))
            continue
        return result
    return result


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    """Mark all e2e tests if env is set up, otherwise skip them."""
    has_env_var = "GOOGLE_ADS_LOGIN_CUSTOMER_ID" in os.environ
    skip_e2e = pytest.mark.skip(reason="Missing Google Ads credentials in ENV")

    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            if not has_env_var:
                item.add_marker(skip_e2e)

            filename = item.fspath.basename
            if "accounts" in filename:
                item.add_marker(pytest.mark.accounts)
            elif "budgets" in filename:
                item.add_marker(pytest.mark.budgets)
            elif "campaigns" in filename:
                item.add_marker(pytest.mark.campaigns)
            elif "campaign_safety_workflow" in filename:
                item.add_marker(pytest.mark.safety)
            elif "destructive_safety_workflow" in filename:
                item.add_marker(pytest.mark.destructive)


@pytest.fixture(autouse=True)
def _reset_session():
    """Reset active account between tests but preserve real client credentials."""
    from burnr8 import session as _session

    _session._active_account.set(None)
    yield
    _session._active_account.set(None)


@pytest.fixture(scope="session")
def test_customer_id():
    """A valid customer ID for integration tests that make real API calls."""
    client_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if not client_id:
        pytest.skip("Missing GOOGLE_ADS_LOGIN_CUSTOMER_ID env var.")
    if not (client_id.isdigit() and len(client_id) == 10):
        pytest.skip("Invalid GOOGLE_ADS_LOGIN_CUSTOMER_ID format. Must be 10 digits.")
    return client_id


@pytest.fixture(scope="session")
def test_account_ads_client():
    """A real GoogleAdsClient for integration tests that make real API calls."""
    from burnr8.client import get_client

    try:
        client = get_client()
        client.get_service("GoogleAdsService")
        return client
    except (ValueError, OSError) as e:
        pytest.skip(f"Skipping: invalid/missing Google Ads credentials: {e}")
