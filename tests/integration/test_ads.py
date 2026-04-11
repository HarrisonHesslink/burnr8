# tests/integration/test_ads.py
"""Integration tests for ad tools — list, create RSA, set status."""

import uuid

import pytest

from tests.integration.conftest import INVALID_CUSTOMER_IDS, register_tool


def _register(name: str, module: str = "ads"):
    return register_tool(name, module)


# ---------------------------------------------------------------------------
# list_ads (read-only)
# ---------------------------------------------------------------------------


class TestListAds:
    def test_list_all(self, test_customer_id):
        tool = _register("list_ads")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert "error" not in result
        assert "summary" in result
        assert "total_ads" in result["summary"]
        assert "ad_strength_distribution" in result["summary"]

    def test_filter_by_ad_group(self, test_customer_id):
        tool = _register("list_ads")
        result = tool(customer_id=test_customer_id, ad_group_id="9999999999")

        assert isinstance(result, dict)
        assert "error" not in result
        assert result["summary"]["total_ads"] == 0

    def test_invalid_ad_group_id(self, test_customer_id):
        tool = _register("list_ads")
        result = tool(customer_id=test_customer_id, ad_group_id="bad-id")

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("list_ads")
        result = tool(customer_id=customer_id)

        assert result["error"] is True


# ---------------------------------------------------------------------------
# create_responsive_search_ad + set_ad_status
# ---------------------------------------------------------------------------


class TestCreateAndManageAd:
    """Tests RSA creation and status changes with real campaign + ad group."""

    campaign_id = None
    budget_id = None
    ad_group_id = None
    ad_id = None

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, test_customer_id):
        uid = uuid.uuid4().hex[:8]

        budget_tool = _register("create_budget", "budgets")
        budget_result = budget_tool(
            name=f"ads-test-budget-{uid}",
            amount_dollars=1.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = budget_result.get("id")

        campaign_tool = _register("create_campaign", "campaigns")
        campaign_result = campaign_tool(
            name=f"ads-test-campaign-{uid}",
            budget_id=self.__class__.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = campaign_result.get("id")

        ag_tool = _register("create_ad_group", "ad_groups")
        ag_result = ag_tool(
            campaign_id=self.__class__.campaign_id,
            name=f"ads-test-adgroup-{uid}",
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.ad_group_id = ag_result.get("id")
        yield

        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    # --- create_responsive_search_ad ---

    def test_create_rsa_dry_run(self, test_customer_id):
        tool = _register("create_responsive_search_ad")
        result = tool(
            ad_group_id=self.ad_group_id,
            headlines=["Headline One", "Headline Two", "Headline Three"],
            descriptions=["Description one for testing.", "Description two for testing."],
            final_url="https://example.com",
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True
        assert result.get("validated") is True

    def test_create_rsa_with_confirm(self, test_customer_id):
        tool = _register("create_responsive_search_ad")
        result = tool(
            ad_group_id=self.ad_group_id,
            headlines=["Test Headline A", "Test Headline B", "Test Headline C"],
            descriptions=["Test description alpha.", "Test description beta."],
            final_url="https://burnrate.sh",
            customer_id=test_customer_id,
            confirm=True,
        )

        # Google Ads may reject with policy_finding_error on test accounts
        if result.get("error") and "policy" in result.get("message", "").lower():
            pytest.skip("Policy rejection on test account — not a code bug")

        assert "error" not in result
        assert "id" in result
        assert result["headlines_count"] == 3
        assert result["descriptions_count"] == 2
        # id is "ad_group_id~ad_id" composite; extract the ad_id part
        composite_id = result["id"]
        self.__class__.ad_id = composite_id.split("~")[1] if "~" in composite_id else composite_id

    def test_create_rsa_with_pinning(self, test_customer_id):
        tool = _register("create_responsive_search_ad")
        result = tool(
            ad_group_id=self.ad_group_id,
            headlines=["Pinned H1", "Pinned H2", "Unpinned H3"],
            descriptions=["Pinned D1", "Unpinned D2"],
            final_url="https://example.com/pinned",
            pinned_headlines=[1, 2, None],
            pinned_descriptions=[1, None],
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("validated") is True

    def test_create_rsa_invalid_pin_length(self, test_customer_id):
        tool = _register("create_responsive_search_ad")
        result = tool(
            ad_group_id=self.ad_group_id,
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            pinned_headlines=[1, 2],  # length mismatch
            customer_id=test_customer_id,
        )

        assert result["error"] is True
        assert "length" in result["message"].lower()

    def test_create_rsa_path2_without_path1(self, test_customer_id):
        tool = _register("create_responsive_search_ad")
        result = tool(
            ad_group_id=self.ad_group_id,
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            path2="oops",
            customer_id=test_customer_id,
        )

        assert result["error"] is True
        assert "path1" in result["message"].lower()

    def test_create_rsa_invalid_ad_group_id(self, test_customer_id):
        tool = _register("create_responsive_search_ad")
        result = tool(
            ad_group_id="not-numeric",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id=test_customer_id,
        )

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_create_rsa_invalid_customer_id(self, label, customer_id):
        tool = _register("create_responsive_search_ad")
        result = tool(
            ad_group_id="9999999999",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id=customer_id,
        )

        assert result["error"] is True

    # --- set_ad_status ---

    def test_set_ad_status_dry_run(self, test_customer_id):
        if not self.ad_id:
            pytest.skip("No ad created")
        tool = _register("set_ad_status")
        result = tool(
            ad_group_id=self.ad_group_id,
            ad_id=self.ad_id,
            status="PAUSED",
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True
        assert result.get("validated") is True

    def test_set_ad_status_confirm(self, test_customer_id):
        if not self.ad_id:
            pytest.skip("No ad created")
        tool = _register("set_ad_status")
        result = tool(
            ad_group_id=self.ad_group_id,
            ad_id=self.ad_id,
            status="PAUSED",
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result
        assert result["new_status"] == "PAUSED"

    def test_set_ad_status_invalid_status(self, test_customer_id):
        tool = _register("set_ad_status")
        result = tool(
            ad_group_id="9999999999",
            ad_id="9999999999",
            status="INVALID",
            customer_id=test_customer_id,
        )

        assert result["error"] is True
