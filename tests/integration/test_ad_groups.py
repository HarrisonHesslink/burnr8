# tests/integration/test_ad_groups.py
"""Integration tests for ad group tools — list, create, update."""

import uuid

import pytest

from tests.integration.conftest import INVALID_CUSTOMER_IDS, register_tool


def _register(name: str, module: str = "ad_groups"):
    return register_tool(name, module)


INVALID_AD_GROUP_IDS = [
    ("letters", "abc"),
    ("dashes", "123-456"),
    ("empty", ""),
    ("special", "12!@#"),
]


# ---------------------------------------------------------------------------
# list_ad_groups (read-only)
# ---------------------------------------------------------------------------


class TestListAdGroups:
    def test_list_all(self, test_customer_id):
        tool = _register("list_ad_groups")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, list)
        if result:
            row = result[0]
            assert "id" in row
            assert "name" in row
            assert "status" in row
            assert "campaign_id" in row
            assert "cpc_bid_dollars" in row

    def test_filter_by_campaign(self, test_customer_id):
        tool = _register("list_ad_groups")
        result = tool(customer_id=test_customer_id, campaign_id="9999999999")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_invalid_campaign_id_format(self, test_customer_id):
        tool = _register("list_ad_groups")
        result = tool(customer_id=test_customer_id, campaign_id="bad-id")

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("list_ad_groups")
        result = tool(customer_id=customer_id)

        assert result["error"] is True


# ---------------------------------------------------------------------------
# create_ad_group + update_ad_group (mutating)
# ---------------------------------------------------------------------------


class TestCreateAndUpdateAdGroup:
    """Tests create and update in a single class sharing a campaign fixture."""

    campaign_id = None
    budget_id = None
    ad_group_id = None

    @pytest.fixture(autouse=True, scope="class")
    def _setup_campaign(self, test_customer_id):
        uid = uuid.uuid4().hex[:8]

        budget_tool = _register("create_budget", "budgets")
        budget_result = budget_tool(
            name=f"ag-test-budget-{uid}",
            amount_dollars=1.0,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.budget_id = budget_result.get("id")

        campaign_tool = _register("create_campaign", "campaigns")
        campaign_result = campaign_tool(
            name=f"ag-test-campaign-{uid}",
            budget_id=self.__class__.budget_id,
            customer_id=test_customer_id,
            confirm=True,
        )
        self.__class__.campaign_id = campaign_result.get("id")
        yield

        campaign_id = getattr(self.__class__, "campaign_id", None)
        if campaign_id:
            remove_tool = _register("remove_campaign", "campaigns")
            remove_tool(confirm=True, customer_id=test_customer_id, campaign_id=campaign_id)
        cleanup_tool = _register("remove_orphan_budgets", "budgets")
        cleanup_tool(confirm=True, customer_id=test_customer_id)

    # --- create_ad_group ---

    def test_create_dry_run(self, test_customer_id):
        tool = _register("create_ad_group")
        result = tool(
            campaign_id=self.campaign_id,
            name="dry-run-ad-group",
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True
        assert result.get("validated") is True

    def test_create_with_confirm(self, test_customer_id):
        uid = uuid.uuid4().hex[:8]
        tool = _register("create_ad_group")
        result = tool(
            campaign_id=self.campaign_id,
            name=f"test-ad-group-{uid}",
            cpc_bid=1.50,
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result
        assert "id" in result
        assert "resource_name" in result
        self.__class__.ad_group_id = result["id"]

    def test_create_invalid_campaign_id(self, test_customer_id):
        tool = _register("create_ad_group")
        result = tool(
            campaign_id="not-numeric",
            name="should-fail",
            customer_id=test_customer_id,
        )

        assert result["error"] is True

    def test_create_negative_cpc_bid(self, test_customer_id):
        tool = _register("create_ad_group")
        result = tool(
            campaign_id=self.campaign_id,
            name="negative-bid-test",
            cpc_bid=-5.0,
            customer_id=test_customer_id,
        )

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_create_invalid_customer_id(self, label, customer_id):
        tool = _register("create_ad_group")
        result = tool(
            campaign_id="9999999999",
            name="should-fail",
            customer_id=customer_id,
        )

        assert result["error"] is True

    # --- update_ad_group ---

    def test_update_name(self, test_customer_id):
        if not self.ad_group_id:
            pytest.skip("No ad group created")
        uid = uuid.uuid4().hex[:8]
        tool = _register("update_ad_group")
        result = tool(
            ad_group_id=self.ad_group_id,
            name=f"updated-name-{uid}",
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result
        assert "resource_name" in result
        assert "name" in result["updated_fields"]

    def test_update_cpc_bid(self, test_customer_id):
        if not self.ad_group_id:
            pytest.skip("No ad group created")
        tool = _register("update_ad_group")
        result = tool(
            ad_group_id=self.ad_group_id,
            cpc_bid=2.00,
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result
        assert "cpc_bid_micros" in result["updated_fields"]

    def test_update_dry_run(self, test_customer_id):
        if not self.ad_group_id:
            pytest.skip("No ad group created")
        tool = _register("update_ad_group")
        result = tool(
            ad_group_id=self.ad_group_id,
            name="dry-run-name-change",
            customer_id=test_customer_id,
            confirm=False,
        )

        assert result.get("warning") is True
        assert result.get("validated") is True

    def test_update_no_fields(self, test_customer_id):
        if not self.ad_group_id:
            pytest.skip("No ad group created")
        tool = _register("update_ad_group")
        result = tool(
            ad_group_id=self.ad_group_id,
            customer_id=test_customer_id,
        )

        assert result["error"] is True
        assert "no fields" in result["message"].lower()

    @pytest.mark.parametrize("label,ad_group_id", INVALID_AD_GROUP_IDS)
    def test_update_invalid_ad_group_id(self, label, ad_group_id, test_customer_id):
        tool = _register("update_ad_group")
        result = tool(
            ad_group_id=ad_group_id,
            name="should-fail",
            customer_id=test_customer_id,
        )

        assert result["error"] is True

    def test_update_invalid_status(self, test_customer_id):
        if not self.ad_group_id:
            pytest.skip("No ad group created")
        tool = _register("update_ad_group")
        result = tool(
            ad_group_id=self.ad_group_id,
            status="INVALID_STATUS",
            customer_id=test_customer_id,
        )

        assert result["error"] is True

    # --- list after mutations ---

    def test_list_shows_created_ad_group(self, test_customer_id):
        if not self.ad_group_id:
            pytest.skip("No ad group created")
        tool = _register("list_ad_groups")
        result = tool(customer_id=test_customer_id, campaign_id=self.campaign_id)

        assert isinstance(result, list)
        ids = [str(r["id"]) for r in result]
        assert self.ad_group_id in ids
