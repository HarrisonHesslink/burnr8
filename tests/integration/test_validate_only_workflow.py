# tests/integration/test_validate_only_workflow.py
"""
Integration tests for the validate_only (dry-run) pattern.

Google Ads SDK v30 moved validate_only from a kwarg to a field on the
request object. These tests verify that confirm=False actually sends
validate_only=True to the API, and that no mutations occur.

The bug: if validate_only isn't threaded through the request object,
confirm=False would execute live mutations — silently spending money.
"""

import uuid

import pytest


def _register_tool(tool_name, module_name):
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


class TestBudgetDryRun:
    """Verify create_budget with confirm=False validates but doesn't create."""

    def test_create_budget_dry_run_validates(self, test_customer_id):
        tool = _register_tool("create_budget", "budgets")
        result = tool(
            name=f"DryRun Budget {uuid.uuid4().hex[:8]}",
            amount_dollars=10.0,
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True, f"Expected dry-run warning, got: {result}"
        assert result.get("validated") is True, f"Expected validated=True from API, got: {result}"
        assert "resource_name" not in result, "Dry-run should not return a resource_name"

    def test_create_budget_dry_run_rejects_invalid(self, test_customer_id):
        """Negative amount should fail server-side validation even in dry-run."""
        tool = _register_tool("create_budget", "budgets")
        result = tool(
            name=f"Bad Budget {uuid.uuid4().hex[:8]}",
            amount_dollars=-5.0,
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("error") is True, f"Expected error for negative budget, got: {result}"


class TestCampaignDryRun:
    """Verify campaign mutations with confirm=False don't mutate state."""

    @pytest.fixture(autouse=True, scope="class")
    def setup_resources(self, test_customer_id):
        budget_tool = _register_tool("create_budget", "budgets")
        result = budget_tool(
            name=f"ValidateOnly Test Budget {uuid.uuid4().hex[:8]}",
            amount_dollars=10.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = result["id"]

        campaign_tool = _register_tool("create_campaign", "campaigns")
        result = campaign_tool(
            name=f"ValidateOnly Test Campaign {uuid.uuid4().hex[:8]}",
            budget_id=self.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = result["id"]
        yield
        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register_tool("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register_tool("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    def test_update_campaign_dry_run_validates(self, test_customer_id):
        """confirm=False should call API with validate_only=True and return validated response."""
        tool = _register_tool("update_campaign", "campaigns")
        result = tool(
            campaign_id=self.campaign_id,
            name=f"Should Not Change {uuid.uuid4().hex[:8]}",
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True, f"Expected dry-run warning, got: {result}"
        assert result.get("validated") is True, f"Expected validated=True, got: {result}"

    def test_update_campaign_dry_run_no_state_change(self, test_customer_id):
        """After dry-run, campaign name should be unchanged."""
        get_tool = _register_tool("get_campaign", "campaigns")
        before = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)
        original_name = before["name"]

        update_tool = _register_tool("update_campaign", "campaigns")
        update_tool(
            campaign_id=self.campaign_id,
            name="THIS SHOULD NOT PERSIST",
            customer_id=test_customer_id,
            confirm=False,
        )

        after = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)
        assert after["name"] == original_name, (
            f"Dry-run mutated state! Name changed from '{original_name}' to '{after['name']}'"
        )

    def test_set_campaign_status_dry_run_no_state_change(self, test_customer_id):
        """confirm=False on set_campaign_status should not change status."""
        get_tool = _register_tool("get_campaign", "campaigns")
        before = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)

        status_tool = _register_tool("set_campaign_status", "campaigns")
        result = status_tool(
            campaign_id=self.campaign_id,
            status="ENABLED",
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True or result.get("validated") is True

        after = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)
        assert after["status"] == before["status"], (
            f"Dry-run changed status from '{before['status']}' to '{after['status']}'"
        )

    def test_update_campaign_confirm_true_mutates(self, test_customer_id):
        """confirm=True should actually change the campaign name (proves the tool works)."""
        new_name = f"Confirmed Change {uuid.uuid4().hex[:8]}"
        tool = _register_tool("update_campaign", "campaigns")
        result = tool(
            campaign_id=self.campaign_id,
            name=new_name,
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "resource_name" in result, f"Expected resource_name on confirmed update, got: {result}"

        get_tool = _register_tool("get_campaign", "campaigns")
        after = get_tool(campaign_id=self.campaign_id, customer_id=test_customer_id)
        assert after["name"] == new_name, (
            f"Confirmed update didn't persist! Expected '{new_name}', got '{after['name']}'"
        )


class TestKeywordDryRun:
    """Verify keyword mutations with confirm=False validate but don't execute."""

    @pytest.fixture(autouse=True, scope="class")
    def setup_resources(self, test_customer_id):
        budget_tool = _register_tool("create_budget", "budgets")
        result = budget_tool(
            name=f"KW DryRun Budget {uuid.uuid4().hex[:8]}",
            amount_dollars=10.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = result["id"]

        campaign_tool = _register_tool("create_campaign", "campaigns")
        result = campaign_tool(
            name=f"KW DryRun Campaign {uuid.uuid4().hex[:8]}",
            budget_id=self.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = result["id"]

        ag_tool = _register_tool("create_ad_group", "ad_groups")
        result = ag_tool(
            name=f"KW DryRun AdGroup {uuid.uuid4().hex[:8]}",
            campaign_id=self.campaign_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.ad_group_id = result["id"]
        yield
        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register_tool("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register_tool("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    def test_add_keywords_dry_run_validates(self, test_customer_id):
        tool = _register_tool("add_keywords", "keywords")
        result = tool(
            ad_group_id=self.ad_group_id,
            keywords=[{"text": "dry run test keyword", "match_type": "EXACT"}],
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True, f"Expected dry-run warning, got: {result}"
        assert result.get("validated") is True, f"Expected validated=True, got: {result}"

    def test_add_keywords_dry_run_no_keywords_created(self, test_customer_id):
        """After dry-run add, no keywords should exist in the ad group."""
        tool = _register_tool("add_keywords", "keywords")
        tool(
            ad_group_id=self.ad_group_id,
            keywords=[{"text": "should not exist", "match_type": "BROAD"}],
            customer_id=test_customer_id,
            confirm=False,
        )

        list_tool = _register_tool("list_keywords", "keywords")
        result = list_tool(
            ad_group_id=self.ad_group_id,
            customer_id=test_customer_id,
        )

        keyword_texts = [kw.get("text", "") for kw in result.get("keywords", [])]
        assert "should not exist" not in keyword_texts, (
            f"Dry-run created a keyword! Found 'should not exist' in {keyword_texts}"
        )

    def test_add_keywords_dict_coercion(self, test_customer_id):
        """Verify raw dict inputs are coerced to KeywordInput models (regression test)."""
        tool = _register_tool("add_keywords", "keywords")
        result = tool(
            ad_group_id=self.ad_group_id,
            keywords=[{"text": "dict coercion kw test", "match_type": "EXACT"}],
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result, f"Dict coercion failed: {result}"
        assert result["added"] == 1
        assert result["keywords"][0]["text"] == "dict coercion kw test"


class TestExtensionDryRun:
    """Verify extension creation with confirm=False validates but doesn't create."""

    @pytest.fixture(autouse=True, scope="class")
    def setup_campaign(self, test_customer_id):
        budget_tool = _register_tool("create_budget", "budgets")
        result = budget_tool(
            name=f"Ext DryRun Budget {uuid.uuid4().hex[:8]}",
            amount_dollars=10.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = result["id"]

        campaign_tool = _register_tool("create_campaign", "campaigns")
        result = campaign_tool(
            name=f"Ext DryRun Campaign {uuid.uuid4().hex[:8]}",
            budget_id=self.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = result["id"]
        yield
        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register_tool("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register_tool("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    def test_create_sitelink_dry_run(self, test_customer_id):
        tool = _register_tool("create_sitelink", "extensions")
        result = tool(
            link_text="DryRun Sitelink",
            final_url="https://example.com",
            campaign_id=self.campaign_id,
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True, f"Expected dry-run warning, got: {result}"
        assert result.get("validated") is True, f"Expected validated=True, got: {result}"
        assert "asset_resource_name" not in result, "Dry-run should not create an asset"

    def test_create_callout_dry_run(self, test_customer_id):
        tool = _register_tool("create_callout", "extensions")
        result = tool(
            callout_text="DryRun Callout",
            campaign_id=self.campaign_id,
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True, f"Expected dry-run warning, got: {result}"
        assert result.get("validated") is True, f"Expected validated=True, got: {result}"
