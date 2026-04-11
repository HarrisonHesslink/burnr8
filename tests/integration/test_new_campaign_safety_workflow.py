# tests/integration/test_new_campaign_safety_workflow.py
import uuid

import pytest

from tests.integration.conftest import register_tool as _register_tool

# Goal is to test that new campaigns always start paused, and that duplicate campaign names are handled gracefully with an error message, not by creating a new campaign or mutating an existing one. This is critical to prevent accidental overspending and ensure a safe workflow for users. We will also test the case where no budget ID is provided, which should also result in an error without creating a campaign.


class TestCampaignCreationSafety:
    @pytest.fixture(autouse=True, scope="class")
    def setup_budget(self, test_customer_id):
        tool = _register_tool("create_budget", "budgets")
        result = tool(name="Test Budget", amount_dollars=10.0, customer_id=test_customer_id, confirm=True)
        self.__class__.budget_id = result["id"]
        yield
        # cleanup: remove the budget after all tests
        remove_tool = _register_tool("remove_orphan_budgets", "budgets")
        remove_tool(confirm=True, customer_id=test_customer_id)

    @pytest.fixture(autouse=True, scope="class")
    def remove_test_campaign(self, test_customer_id):
        yield
        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register_tool("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)

    # non-duplicate campaign case.
    def test_create_campaign(self, test_customer_id):
        tool = _register_tool("create_campaign", "campaigns")
        name = f"Test Campaign {uuid.uuid4().hex[:8]}"  # Unique name to avoid duplicates
        result = tool(name=name, budget_id=self.budget_id, customer_id=test_customer_id, confirm=True)

        self.__class__.campaign_id = result["id"]  # Store for cleanup
        self.__class__.campaign_name = name

        assert "resource_name" in result
        assert "name" in result and name == result["name"]
        assert "status" in result and result["status"] == "PAUSED"

    # duplicate campaign case.
    def test_create_duplicate_campaign(self, test_customer_id):
        tool = _register_tool("create_campaign", "campaigns")
        name = self.campaign_name  # Use the same name to trigger duplicate handling

        result = tool(name=name, budget_id=self.budget_id, customer_id=test_customer_id, confirm=True)

        assert "error" in result and result["error"] is True
        assert "errors" in result
        assert "status" in result and result["status"] == "INVALID_ARGUMENT"

    # no budget id case.
    def test_create_campaign_no_budget_id(self, test_customer_id):
        tool = _register_tool("create_campaign", "campaigns")
        name = f"Test Campaign No Budget {uuid.uuid4().hex[:8]}"  # Unique name to avoid duplicates

        result = tool(name=name, customer_id=test_customer_id)

        assert "error" in result and result["error"] is True
