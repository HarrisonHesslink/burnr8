"""Shared integration test fixtures — e2e Google Ads client tests."""

import logging
import os

import pytest
from dotenv import load_dotenv

logging.getLogger("google.ads.googleads").setLevel(logging.CRITICAL)
load_dotenv(".env.local")


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
    except Exception as e:
        pytest.skip(f"Skipping test due to invalid Google Ads credentials: {e}")
