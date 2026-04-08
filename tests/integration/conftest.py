"""Shared integration test fixtures — e2e Google Ads client tests."""

import os, pytest

import logging
logging.getLogger("google.ads.googleads").setLevel(logging.CRITICAL)

from dotenv import load_dotenv

load_dotenv(".env.local")

def pytest_collection_modifyitems(config, items):
    """
    Mark all e2e tests if env is set up for it, otherwise skip them with a clear message.
    This allows running the full suite in CI when credentials are available, while preventing confusing failures for developers who haven't set up their env yet.
    """
    has_env_var = "GOOGLE_ADS_LOGIN_CUSTOMER_ID" in os.environ
    skip_e2e = pytest.mark.skip(reason="Missing Google Ads credentials in ENV")
    
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            if not has_env_var:
                item.add_marker(skip_e2e)

            # Auto-mark by filename for easier selective test runs (e.g. pytest -m "campaigns")
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
        pytest.skip("Skipping test: Missing GOOGLE_ADS_LOGIN_CUSTOMER_ID env var.")
        
    if not (client_id.isdigit() and len(client_id) == 10):
        pytest.skip("Skipping test: Invalid GOOGLE_ADS_LOGIN_CUSTOMER_ID format. Must be 10 digits.")
        
    return client_id

@pytest.fixture(scope="session")
def test_account_ads_client():
    """A real GoogleAdsClient for integration tests that make real API calls."""
    from burnr8.client import get_client
    try:
        client = get_client()
        # Make a simple call to verify credentials are valid
        print(get_client())
        client.get_service("GoogleAdsService")
        return client
    except Exception as e:
        pytest.skip(f"Skipping test due to invalid Google Ads credentials: {e}")