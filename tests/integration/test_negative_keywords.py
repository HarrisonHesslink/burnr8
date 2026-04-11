# tests/integration/test_negative_keywords.py
"""Integration tests for negative keyword tools — campaign and ad group level."""

import uuid

import pytest

from tests.integration.conftest import INVALID_CUSTOMER_IDS, register_tool


def _register(name: str):
    return register_tool(name, "negative_keywords")


def _register_other(name: str, module: str):
    return register_tool(name, module)


# ---------------------------------------------------------------------------
# list_negative_keywords (read-only)
# ---------------------------------------------------------------------------


class TestListNegativeKeywords:
    def test_list_campaign_level(self, test_customer_id):
        tool = _register("list_negative_keywords")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert "error" not in result
        assert "summary" in result
        assert "total" in result["summary"]
        assert "by_level" in result["summary"]
        assert "CAMPAIGN" in result["summary"]["by_level"]

    def test_list_with_invalid_campaign_id(self, test_customer_id):
        tool = _register("list_negative_keywords")
        result = tool(customer_id=test_customer_id, campaign_id="not-numeric")

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("list_negative_keywords")
        result = tool(customer_id=customer_id)

        assert result["error"] is True


# ---------------------------------------------------------------------------
# add_negative_keywords (campaign-level) — dry-run + live
# ---------------------------------------------------------------------------


class TestAddNegativeKeywordsCampaign:
    """Tests campaign-level negative keyword creation with a real campaign."""

    campaign_id = None
    budget_id = None

    @pytest.fixture(autouse=True, scope="class")
    def _setup_campaign(self, test_customer_id):
        """Create a budget + campaign for testing, clean up after."""
        uid = uuid.uuid4().hex[:8]

        budget_tool = _register_other("create_budget", "budgets")
        budget_result = budget_tool(
            name=f"neg-kw-test-budget-{uid}",
            amount_dollars=1.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = budget_result.get("id")

        campaign_tool = _register_other("create_campaign", "campaigns")
        campaign_result = campaign_tool(
            name=f"neg-kw-test-campaign-{uid}",
            budget_id=self.__class__.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = campaign_result.get("id")
        yield

        # Cleanup
        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register_other("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register_other("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    def test_dry_run_validates(self, test_customer_id):
        tool = _register("add_negative_keywords")
        result = tool(
            campaign_id=self.campaign_id,
            keywords=[{"text": "free stuff", "match_type": "EXACT"}],
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True
        assert result.get("validated") is True

    def test_dry_run_does_not_add(self, test_customer_id):
        """Dry-run should not create any negatives."""
        tool = _register("add_negative_keywords")
        tool(
            campaign_id=self.campaign_id,
            keywords=[{"text": "should not exist dry run neg", "match_type": "BROAD"}],
            customer_id=test_customer_id,
            confirm=False,
        )

        list_tool = _register("list_negative_keywords")
        result = list_tool(customer_id=test_customer_id, campaign_id=self.campaign_id)
        assert "should not exist dry run neg" not in str(result)

    def test_add_with_confirm(self, test_customer_id):
        tool = _register("add_negative_keywords")
        result = tool(
            campaign_id=self.campaign_id,
            keywords=[
                {"text": "cheap junk", "match_type": "EXACT"},
                {"text": "free trial", "match_type": "PHRASE"},
            ],
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result
        assert result["added"] == 2
        assert len(result["resource_names"]) == 2
        assert result["keywords"][0]["text"] == "cheap junk"

    def test_add_dict_coercion(self, test_customer_id):
        """Verify dict inputs are coerced to NegativeKeyword models (bug fix regression)."""
        tool = _register("add_negative_keywords")
        result = tool(
            campaign_id=self.campaign_id,
            keywords=[{"text": "dict coercion test", "match_type": "BROAD"}],
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result
        assert result["added"] == 1

    def test_invalid_campaign_id(self, test_customer_id):
        tool = _register("add_negative_keywords")
        result = tool(
            campaign_id="not-a-number",
            keywords=[{"text": "test", "match_type": "BROAD"}],
            customer_id=test_customer_id,
        )

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("add_negative_keywords")
        result = tool(
            campaign_id="9999999999",
            keywords=[{"text": "test", "match_type": "BROAD"}],
            customer_id=customer_id,
        )

        assert result["error"] is True


# ---------------------------------------------------------------------------
# add_ad_group_negative_keywords
# ---------------------------------------------------------------------------


class TestAddAdGroupNegativeKeywords:
    """Tests ad-group-level negative keyword creation."""

    campaign_id = None
    budget_id = None
    ad_group_id = None

    @pytest.fixture(autouse=True, scope="class")
    def _setup_campaign_and_ad_group(self, test_customer_id):
        uid = uuid.uuid4().hex[:8]

        budget_tool = _register_other("create_budget", "budgets")
        budget_result = budget_tool(
            name=f"ag-neg-kw-budget-{uid}",
            amount_dollars=1.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = budget_result.get("id")

        campaign_tool = _register_other("create_campaign", "campaigns")
        campaign_result = campaign_tool(
            name=f"ag-neg-kw-campaign-{uid}",
            budget_id=self.__class__.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = campaign_result.get("id")

        ag_tool = _register_other("create_ad_group", "ad_groups")
        ag_result = ag_tool(
            campaign_id=self.__class__.campaign_id,
            name=f"ag-neg-kw-adgroup-{uid}",
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.ad_group_id = ag_result.get("id")
        yield

        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register_other("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register_other("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    def test_dry_run(self, test_customer_id):
        tool = _register("add_ad_group_negative_keywords")
        result = tool(
            ad_group_id=self.ad_group_id,
            keywords=[{"text": "ad group neg dry run", "match_type": "EXACT"}],
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True
        assert result.get("validated") is True

    def test_add_with_confirm(self, test_customer_id):
        tool = _register("add_ad_group_negative_keywords")
        result = tool(
            ad_group_id=self.ad_group_id,
            keywords=[{"text": "ad group negative test", "match_type": "PHRASE"}],
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result
        assert result["added"] == 1

    def test_invalid_ad_group_id(self, test_customer_id):
        tool = _register("add_ad_group_negative_keywords")
        result = tool(
            ad_group_id="bad-id",
            keywords=[{"text": "test", "match_type": "BROAD"}],
            customer_id=test_customer_id,
        )

        assert result["error"] is True


# ---------------------------------------------------------------------------
# remove_negative_keyword
# ---------------------------------------------------------------------------


class TestRemoveNegativeKeyword:
    def test_requires_campaign_or_ad_group(self, test_customer_id):
        tool = _register("remove_negative_keyword")
        result = tool(
            criterion_id="12345",
            customer_id=test_customer_id,
        )

        assert result["error"] is True
        assert "campaign_id" in result["message"] or "ad_group_id" in result["message"]

    def test_rejects_both_campaign_and_ad_group(self, test_customer_id):
        tool = _register("remove_negative_keyword")
        result = tool(
            criterion_id="12345",
            campaign_id="9999999999",
            ad_group_id="9999999999",
            customer_id=test_customer_id,
        )

        assert result["error"] is True
        assert "not both" in result["message"].lower()

    def test_dry_run_validates(self, test_customer_id):
        tool = _register("remove_negative_keyword")
        result = tool(
            criterion_id="9999999999",
            campaign_id="9999999999",
            customer_id=test_customer_id,
            confirm=False,
        )

        # Dry-run against a non-existent criterion should still validate
        # (may return warning or error depending on API behavior)
        assert isinstance(result, dict)

    def test_invalid_criterion_id(self, test_customer_id):
        tool = _register("remove_negative_keyword")
        result = tool(
            criterion_id="not-numeric",
            campaign_id="9999999999",
            customer_id=test_customer_id,
        )

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("remove_negative_keyword")
        result = tool(
            criterion_id="12345",
            campaign_id="9999999999",
            customer_id=customer_id,
        )

        assert result["error"] is True


# ---------------------------------------------------------------------------
# Full lifecycle: add → verify → remove → verify gone
# ---------------------------------------------------------------------------


class TestNegativeKeywordLifecycle:
    """Add a negative keyword, verify it exists, remove it, verify it's gone."""

    campaign_id = None
    budget_id = None

    @pytest.fixture(autouse=True, scope="class")
    def _setup_campaign(self, test_customer_id):
        uid = uuid.uuid4().hex[:8]

        budget_tool = _register_other("create_budget", "budgets")
        budget_result = budget_tool(
            name=f"lifecycle-neg-kw-budget-{uid}",
            amount_dollars=1.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = budget_result.get("id")

        campaign_tool = _register_other("create_campaign", "campaigns")
        campaign_result = campaign_tool(
            name=f"lifecycle-neg-kw-campaign-{uid}",
            budget_id=self.__class__.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = campaign_result.get("id")
        yield

        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register_other("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register_other("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    def test_add_verify_remove_verify(self, test_customer_id):
        # 1. Add a negative keyword
        add_tool = _register("add_negative_keywords")
        add_result = add_tool(
            campaign_id=self.campaign_id,
            keywords=[{"text": "lifecycle removal test", "match_type": "EXACT"}],
            customer_id=test_customer_id,
            confirm=True,
        )
        assert "error" not in add_result
        assert add_result["added"] == 1

        # Extract criterion ID from resource name (format: customers/X/campaignCriteria/Y~Z)
        resource_name = add_result["resource_names"][0]
        criterion_id = resource_name.split("~")[-1]

        # 2. Verify it appears in list
        list_tool = _register("list_negative_keywords")
        list_result = list_tool(customer_id=test_customer_id, campaign_id=self.campaign_id)
        assert "lifecycle removal test" in str(list_result)

        # 3. Remove it
        remove_tool = _register("remove_negative_keyword")
        remove_result = remove_tool(
            criterion_id=criterion_id,
            campaign_id=self.campaign_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        assert "error" not in remove_result
        assert "removed" in remove_result

        # 4. Verify it's gone
        list_result_after = list_tool(customer_id=test_customer_id, campaign_id=self.campaign_id)
        assert "lifecycle removal test" not in str(list_result_after)
