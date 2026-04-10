# tests/integration/test_update_campaign_safety_workflow.py
import uuid

import pytest


def _register_tool(tool_name, module_name):
    """Register list_accessible_accounts tools and return the one matching *name*."""
    from importlib import import_module
    mod = import_module(f"burnr8.tools.{module_name}")

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == tool_name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    mod.register(cap)
    return captured["func"]


VALID_BIDDING_STRATEGIES = [
    ("Manual CPC", "MANUAL_CPC"),
    ("Manual CPM",  "MANUAL_CPM"),
    ("Maximize Clicks", "MAXIMIZE_CLICKS"),
    ("Maximize Conversions", "MAXIMIZE_CONVERSIONS"),
    ("Maximize Conversion Value", "MAXIMIZE_CONVERSION_VALUE"),
    ("Target CPA",  "TARGET_CPA"),
    ("Target ROAS", "TARGET_ROAS"),
    ("Target Impression Share", "TARGET_IMPRESSION_SHARE"),
    ("Target Spend", "TARGET_SPEND")
]

# Goal is to test that new campaigns always start paused, and that duplicate campaign names are handled gracefully with an error message, not by creating a new campaign or mutating an existing one. This is critical to prevent accidental overspending and ensure a safe workflow for users. We will also test the case where no budget ID is provided, which should also result in an error without creating a campaign.

class TestCampaignUpdateSafety:

    @pytest.fixture(autouse=True, scope="class")
    def setup_budget(self, test_customer_id):
        tool =  _register_tool("create_budget", "budgets")
        result = tool(name=f"Test Budget {uuid.uuid4().hex[:8]}", amount_dollars=10.0, customer_id=test_customer_id, confirm=True)
        self.__class__.budget_id = result["id"]

        second_tool = _register_tool("create_budget", "budgets")
        second_result = second_tool(name=f"Test Budget {uuid.uuid4().hex[:8]}", amount_dollars=20.0, customer_id=test_customer_id, confirm=True)
        self.__class__.second_budget_id = second_result["id"]

        yield
        # cleanup: remove the budget after all tests
        remove_tool = _register_tool("remove_orphan_budgets", "budgets")
        result = remove_tool(confirm=True, customer_id=test_customer_id)

    @pytest.fixture(autouse=True, scope="class")
    def setup_campaign(self, test_customer_id):
        tool = _register_tool("create_campaign", "campaigns")
        name = f"Test Campaign {uuid.uuid4().hex[:8]}"  # Unique name to avoid duplicates
        result = tool(name=name, budget_id=self.budget_id, customer_id=test_customer_id, confirm=True)
        self.__class__.campaign_id = result["id"]  # Store for cleanup
        self.__class__.campaign_name = name
        yield
        # cleanup: remove the campaign after all tests
        remove_tool = _register_tool("remove_campaign", "campaigns")
        remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=self.campaign_id)

    def test_update_campaign_no_confirmation(self, test_customer_id):
        tool = _register_tool("update_campaign", "campaigns")
        result = tool(campaign_id=self.campaign_id, budget_id=self.budget_id, customer_id=test_customer_id)

        assert result['warning'] is True

    def test_update_campaign_budget_id(self, test_customer_id):
        tool = _register_tool("update_campaign", "campaigns")
        result = tool(campaign_id=self.campaign_id, budget_id=self.second_budget_id, customer_id=test_customer_id, confirm=True)

        # Response Asserts

        assert "resource_name" in result
        assert "campaign_id" in result and result["campaign_id"] == self.campaign_id
        assert "updated_fields" in result and "campaign_budget" in result["updated_fields"]

        # State Asserts
        get_tool = _register_tool("get_campaign", "campaigns")
        get_result = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)

        assert "campaign_budget" in get_result and get_result["campaign_budget"] == "customers/" + test_customer_id + "/campaignBudgets/" + self.second_budget_id
        assert get_result["campaign_budget"] != "customers/" + test_customer_id + "/campaignBudgets/" + self.budget_id

        self.__class__.budget_id = self.second_budget_id  # Update for potential cleanup if budget ID is used in matching

    @pytest.mark.parametrize("label,bidding_strategy", VALID_BIDDING_STRATEGIES)
    def test_update_campaign_change_bidding_strategy_no_sub_fields(self, label, bidding_strategy, test_customer_id):

        if bidding_strategy in ["MANUAL_CPM", "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS"]:
            # These don't have any required sub-fields, so we skip this test for them.
            pytest.skip(f"{label} skipped due to no conversion in Test Account!")

        tool = _register_tool("update_campaign", "campaigns")
        result = tool(campaign_id=self.campaign_id, bidding_strategy=bidding_strategy, customer_id=test_customer_id, confirm=True)

        if bidding_strategy in ["TARGET_IMPRESSION_SHARE"]:
            # These require subfield values (target_cpa_dollars, target_roas, etc.)
            assert result.get("error") is True, f"Expected error for {label} without required params, got: {result}"
        else:
            # MANUAL_CPC, MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_SPEND
            # succeed without extra params
            assert "resource_name" in result, f"Expected success for {label}, got: {result}"

    @pytest.mark.parametrize("label,bidding_strategy", VALID_BIDDING_STRATEGIES)
    def test_update_campaign_change_bidding_strategy_with_sub_fields(self, label, bidding_strategy, test_customer_id):

        if bidding_strategy == "MANUAL_CPM":
            # Manual CPM doesn't have any required sub-fields, so we skip this test for it.
            pytest.skip("Manual CPM has no required sub-fields for SEARCH, skipping.")
        elif bidding_strategy in ["MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS"]:
            # These don't have any required sub-fields, so we skip this test for them.
            pytest.skip(f"{label} skipped due to no conversion in Test Account!")

        tool = _register_tool("update_campaign", "campaigns")


        kwargs = {"campaign_id": self.campaign_id, "bidding_strategy": bidding_strategy, "customer_id": test_customer_id, "confirm": True}

        expected = bidding_strategy

        match bidding_strategy:
            case "MANUAL_CPC":
                pass  # no extra params needed
            case "MAXIMIZE_CLICKS" | "TARGET_SPEND":
                kwargs["max_cpc_bid_ceiling_dollars"] = 2.0
                expected = "TARGET_SPEND"
            case "MAXIMIZE_CONVERSIONS" | "TARGET_CPA":
                kwargs["target_cpa_dollars"] = 5.0
            case "MAXIMIZE_CONVERSION_VALUE" | "TARGET_ROAS":
                kwargs["target_roas"] = 4.0
            case "TARGET_IMPRESSION_SHARE":
                kwargs["target_impression_share_fraction"] = 0.5
                kwargs["max_cpc_bid_ceiling_dollars"] = 2.0

        result = tool(**kwargs)

        assert "resource_name" in result
        assert "campaign_id" in result and result["campaign_id"] == self.campaign_id
        assert "updated_fields" in result

        # State Asserts
        get_tool = _register_tool("get_campaign", "campaigns")
        get_result = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)

        assert "bidding_strategy_type" in get_result and get_result["bidding_strategy_type"] == expected

    def test_update_campaign_change_target_cpa(self, test_customer_id):

        pytest.skip("skipped due to no conversion in Test Account!")

        tool = _register_tool("update_campaign", "campaigns")

        tool(campaign_id=self.campaign_id, bidding_strategy="TARGET_CPA", customer_id=test_customer_id, confirm=True, target_cpa_dollars=5.0)

        result = tool(campaign_id=self.campaign_id, target_cpa_dollars=10.0, customer_id=test_customer_id, confirm=True)

        assert "resource_name" in result
        assert "campaign_id" in result and result["campaign_id"] == self.campaign_id
        assert "updated_fields" in result

    def test_update_campaign_change_target_roas(self, test_customer_id):

        pytest.skip("skipped due to no conversion in Test Account!")

        tool = _register_tool("update_campaign", "campaigns")
        result = tool(campaign_id=self.campaign_id, target_roas=1.5, customer_id=test_customer_id, confirm=True)

        assert "resource_name" in result

    def test_update_campaign_change_name(self, test_customer_id):
        tool = _register_tool("update_campaign", "campaigns")
        new_name = f"Updated Campaign {uuid.uuid4().hex[:8]}"
        result = tool(campaign_id=self.campaign_id, name=new_name, customer_id=test_customer_id, confirm=True)

        # Response Asserts
        assert "campaign_id" in result and result["campaign_id"] == self.campaign_id
        assert "name" in result and result["name"] == new_name

        # State Asserts
        get_tool = _register_tool("get_campaign", "campaigns")
        get_result = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)

        assert "name" in get_result and get_result["name"] == new_name

        self.__class__.campaign_name = new_name  # Update for potential cleanup if name is used in matching


    def test_update_campaign_change_channel(self, test_customer_id):

        pytest.skip("can't change channel through update_campaign tool, skipping.")

        tool = _register_tool("update_campaign", "campaigns")
        tool(campaign_id=self.campaign_id, channel="DISPLAY", customer_id=test_customer_id, confirm=True)

    def test_set_campaign_status(self, test_customer_id):
        tool = _register_tool("set_campaign_status", "campaigns")
        result = tool(campaign_id=self.campaign_id, status="PAUSED", customer_id=test_customer_id, confirm=True)

        assert "new_status" in result and result["new_status"] == "PAUSED"

        # State Asserts
        get_tool = _register_tool("get_campaign", "campaigns")
        get_result = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)

        assert "status" in get_result and get_result["status"] == "PAUSED"

    def test_set_campaign_status_dry_run(self, test_customer_id):
        tool = _register_tool("set_campaign_status", "campaigns")
        result = tool(campaign_id=self.campaign_id, status="ENABLED", customer_id=test_customer_id, confirm=False)

        assert result.get("warning") is True

        # State Asserts
        get_tool = _register_tool("get_campaign", "campaigns")
        get_result = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)

        assert "status" in get_result and get_result["status"] == "PAUSED", f"Expected campaign to remain PAUSED without confirmation, got: {get_result.get('status')}"

    #TODO: add test for status enabled with budget = 0

    #TODO: Tracking URL Changes
