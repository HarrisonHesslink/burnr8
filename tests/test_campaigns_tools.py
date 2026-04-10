"""Tests for burnr8.tools.campaigns — bidding strategies, list, create, update, set_campaign_status."""

from burnr8.session import set_active_account
from burnr8.tools.campaigns import VALID_BIDDING_STRATEGIES

# ---------------------------------------------------------------------------
# VALID_BIDDING_STRATEGIES (moved from test_campaigns.py)
# ---------------------------------------------------------------------------


class TestBiddingStrategies:
    def test_valid_bidding_strategies_set(self):
        assert "MANUAL_CPC" in VALID_BIDDING_STRATEGIES
        assert "MAXIMIZE_CONVERSIONS" in VALID_BIDDING_STRATEGIES
        assert "TARGET_CPA" in VALID_BIDDING_STRATEGIES
        assert "TARGET_ROAS" in VALID_BIDDING_STRATEGIES
        assert "MAXIMIZE_CLICKS" in VALID_BIDDING_STRATEGIES
        assert len(VALID_BIDDING_STRATEGIES) == 9

    def test_invalid_strategy_not_in_set(self):
        assert "INVALID" not in VALID_BIDDING_STRATEGIES
        assert "AUTO" not in VALID_BIDDING_STRATEGIES

    def test_all_strategies_are_uppercase(self):
        for strategy in VALID_BIDDING_STRATEGIES:
            assert strategy == strategy.upper()
            assert " " not in strategy

    def test_complete_strategy_list(self):
        expected = {
            "MANUAL_CPC", "MANUAL_CPM", "MAXIMIZE_CLICKS",
            "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE",
            "TARGET_CPA", "TARGET_ROAS", "TARGET_IMPRESSION_SHARE",
            "TARGET_SPEND",
        }
        assert expected == VALID_BIDDING_STRATEGIES

    def test_strategies_is_a_set(self):
        assert isinstance(VALID_BIDDING_STRATEGIES, set)

# ---------------------------------------------------------------------------
# Helpers — sample GAQL result rows
# ---------------------------------------------------------------------------


def _campaign_row(
    cid="100",
    name="My Campaign",
    status="ENABLED",
    channel_type="SEARCH",
    bidding_strategy_type="MANUAL_CPC",
    budget="customers/1234567890/campaignBudgets/501",
    impressions=2000,
    clicks=100,
    cost_micros=50_000_000,
):
    return {
        "campaign": {
            "id": cid,
            "name": name,
            "status": status,
            "advertising_channel_type": channel_type,
            "bidding_strategy_type": bidding_strategy_type,
            "campaign_budget": budget,
        },
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
        },
    }


def _campaign_detail_row(
    cid="100",
    name="My Campaign",
    status="ENABLED",
    impressions=2000,
    clicks=100,
    cost_micros=50_000_000,
    conversions=10.0,
    conversions_value=500.0,
):
    return {
        "campaign": {
            "id": cid,
            "name": name,
            "status": status,
            "advertising_channel_type": "SEARCH",
            "bidding_strategy_type": "MANUAL_CPC",
            "campaign_budget": "customers/1234567890/campaignBudgets/501",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "network_settings": {
                "target_google_search": True,
                "target_search_network": True,
                "target_content_network": False,
            },
        },
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "conversions": conversions,
            "conversions_value": conversions_value,
        },
    }


def _register_tool(name):
    """Register campaign tools and return the one matching *name*."""
    from burnr8.tools.campaigns import register

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == name:
                def wrapper(*args, **kwargs):
                    import inspect
                    if "confirm" in inspect.signature(fn).parameters and "confirm" not in kwargs:
                        kwargs["confirm"] = True
                    return fn(*args, **kwargs)
                captured["func"] = wrapper
            return fn

    cap = _Capture()
    register(cap)
    return captured["func"]


# ---------------------------------------------------------------------------
# list_campaigns
# ---------------------------------------------------------------------------


class TestListCampaigns:
    def test_returns_campaign_rows(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign": [
                    _campaign_row(cid="100", name="Alpha", impressions=1000, clicks=50, cost_micros=25_000_000),
                    _campaign_row(cid="200", name="Beta", impressions=3000, clicks=150, cost_micros=75_000_000),
                ],
            }
        )

        tool = _register_tool("list_campaigns")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "100"
        assert result[0]["name"] == "Alpha"
        assert result[0]["impressions"] == 1000
        assert result[0]["clicks"] == 50
        assert result[0]["cost_dollars"] == 25.0
        assert result[1]["id"] == "200"
        assert result[1]["name"] == "Beta"
        assert result[1]["cost_dollars"] == 75.0

    def test_returns_empty_list_when_no_campaigns(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("list_campaigns")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_filters_by_status(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign": [_campaign_row(status="PAUSED")],
            }
        )

        tool = _register_tool("list_campaigns")
        result = tool(customer_id="1234567890", status="PAUSED")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["status"] == "PAUSED"

    def test_tracking_url_fields_returned(self, mock_ads_client):
        set_active_account("1234567890")
        row = _campaign_row()
        row["campaign"]["tracking_url_template"] = "{lpurl}?src=google"
        row["campaign"]["final_url_suffix"] = "utm_source=google"
        row["campaign"]["url_custom_parameters"] = [{"key": "season", "value": "winter"}]
        mock_ads_client["set_gaql"]({"FROM campaign": [row]})

        tool = _register_tool("list_campaigns")
        result = tool(customer_id="1234567890")

        assert result[0]["tracking_url_template"] == "{lpurl}?src=google"
        assert result[0]["final_url_suffix"] == "utm_source=google"
        assert result[0]["url_custom_parameters"] == {"season": "winter"}

    def test_invalid_status_returns_error(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("list_campaigns")
        result = tool(customer_id="1234567890", status="BOGUS")

        assert result["error"] is True
        assert "Invalid status" in result["message"]

    def test_structure_fields(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign": [_campaign_row()],
            }
        )

        tool = _register_tool("list_campaigns")
        result = tool(customer_id="1234567890")

        row = result[0]
        expected_keys = {
            "id",
            "name",
            "status",
            "channel_type",
            "bidding_strategy_type",
            "budget",
            "tracking_url_template",
            "final_url_suffix",
            "url_custom_parameters",
            "impressions",
            "clicks",
            "cost_dollars",
        }
        assert set(row.keys()) == expected_keys


# ---------------------------------------------------------------------------
# get_campaign
# ---------------------------------------------------------------------------


class TestGetCampaign:
    def test_returns_campaign_details(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign": [_campaign_detail_row(cid="100", conversions=10.0, conversions_value=500.0)],
            }
        )

        tool = _register_tool("get_campaign")
        result = tool(campaign_id="100", customer_id="1234567890")

        assert result["id"] == "100"
        assert result["impressions"] == 2000
        assert result["clicks"] == 100
        assert result["cost_dollars"] == 50.0
        assert result["conversions"] == 10.0
        assert result["conversions_value"] == 500.0

    def test_campaign_not_found(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("get_campaign")
        result = tool(campaign_id="999", customer_id="1234567890")

        assert result["error"] is True
        assert "not found" in result["message"]


# ---------------------------------------------------------------------------
# create_campaign
# ---------------------------------------------------------------------------


class TestCreateCampaign:
    def test_basic_creation(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("create_campaign")
        result = tool(
            name="Test Campaign",
            budget_id="501",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"
        assert result["status"] == "PAUSED"
        assert result["name"] == "Test Campaign"
        assert "resource_name" in result

        # Verify mutate was called
        client.get_service("CampaignService").mutate_campaigns.assert_called_once()

    def test_manual_cpc_strategy(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(
            name="CPC Campaign",
            budget_id="501",
            bidding_strategy="MANUAL_CPC",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"
        assert result["status"] == "PAUSED"

    def test_maximize_conversions_strategy(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(
            name="Max Conv Campaign",
            budget_id="501",
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"

    def test_maximize_conversions_with_target_cpa(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("create_campaign")
        result = tool(
            name="Max Conv CPA Campaign",
            budget_id="501",
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            target_cpa_dollars=10.0,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"
        # Verify the proto field was set with correct micros value
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.create.maximize_conversions.target_cpa_micros == 10_000_000

    def test_target_cpa_strategy(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(
            name="TCPA Campaign",
            budget_id="501",
            bidding_strategy="TARGET_CPA",
            target_cpa_dollars=15.0,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"

    def test_target_cpa_with_ceiling(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(
            name="TCPA Ceiling Campaign",
            budget_id="501",
            bidding_strategy="TARGET_CPA",
            target_cpa_dollars=15.0,
            max_cpc_bid_ceiling_dollars=5.0,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"

    def test_invalid_bidding_strategy(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(
            name="Bad Strategy",
            budget_id="501",
            bidding_strategy="INVALID_STRATEGY",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "Invalid bidding_strategy" in result["message"]

    def test_display_channel_type(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(
            name="Display Campaign",
            budget_id="501",
            channel_type="DISPLAY",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"

    def test_create_with_tracking_url_template(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("create_campaign")
        result = tool(
            name="Tracked Campaign",
            budget_id="501",
            tracking_url_template="{lpurl}?utm_source=google",
            final_url_suffix="utm_medium=cpc",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"
        # Verify proto fields were actually set
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.create.tracking_url_template == "{lpurl}?utm_source=google"
            assert op.create.final_url_suffix == "utm_medium=cpc"

    def test_create_with_url_custom_parameters(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("create_campaign")
        result = tool(
            name="Custom Params Campaign",
            budget_id="501",
            url_custom_parameters={"season": "winter", "promo": "sale"},
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "222"
        assert result["url_custom_parameters"] == {"season": "winter", "promo": "sale"}
        # Verify url_custom_parameters list was populated with 2 items (real list from conftest)
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert len(op.create.url_custom_parameters) == 2
            # Each appended item should have key/value set
            for param in op.create.url_custom_parameters:
                assert hasattr(param, "key")
                assert hasattr(param, "value")

    def test_invalid_budget_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(
            name="Bad Budget",
            budget_id="abc",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "budget_id" in result["message"]


# ---------------------------------------------------------------------------
# update_campaign
# ---------------------------------------------------------------------------


class TestUpdateCampaign:
    def test_update_name(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            name="Renamed Campaign",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "name" in result["updated_fields"]
        assert "resource_name" in result

    def test_update_bidding_strategy(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "maximize_conversions" in result["updated_fields"]

    def test_update_bidding_strategy_with_target(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            bidding_strategy="TARGET_CPA",
            target_cpa_dollars=20.0,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "target_cpa.target_cpa_micros" in result["updated_fields"]

    def test_update_network_settings(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            target_search_network=False,
            target_content_network=True,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "network_settings.target_search_network" in result["updated_fields"]
        assert "network_settings.target_content_network" in result["updated_fields"]

    def test_update_no_fields_returns_error(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "No fields to update" in result["message"]

    def test_update_invalid_bidding_strategy(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            bidding_strategy="BOGUS",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "Invalid bidding_strategy" in result["message"]

    def test_update_tracking_url_template(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            tracking_url_template="{lpurl}?utm_source=google",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "tracking_url_template" in result["updated_fields"]
        # Verify proto field was set
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.update.tracking_url_template == "{lpurl}?utm_source=google"
            assert "tracking_url_template" in op.update_mask.paths

    def test_update_final_url_suffix(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            final_url_suffix="utm_source=google&utm_medium=cpc",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "final_url_suffix" in result["updated_fields"]
        # Verify proto field was set
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.update.final_url_suffix == "utm_source=google&utm_medium=cpc"
            assert "final_url_suffix" in op.update_mask.paths

    def test_clear_tracking_url_template(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            tracking_url_template="",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "tracking_url_template" in result["updated_fields"]
        # Verify proto was set to empty string (clear)
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.update.tracking_url_template == ""
            assert "tracking_url_template" in op.update_mask.paths

    def test_update_url_custom_parameters(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            url_custom_parameters={"season": "winter", "promo": "sale"},
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "url_custom_parameters" in result["updated_fields"]
        # Verify field mask contains url_custom_parameters
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert "url_custom_parameters" in op.update_mask.paths

    def test_clear_url_custom_parameters(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="100",
            url_custom_parameters={},
            customer_id="1234567890",
        )

        assert "error" not in result
        assert "url_custom_parameters" in result["updated_fields"]
        # Verify field mask is set but url_custom_parameters list is empty (no params appended)
        call_args = client.get_service("CampaignService").mutate_campaigns.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert "url_custom_parameters" in op.update_mask.paths

    def test_update_invalid_campaign_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(
            campaign_id="abc",
            name="Doesn't matter",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "campaign_id" in result["message"]


# ---------------------------------------------------------------------------
# set_campaign_status
# ---------------------------------------------------------------------------


class TestSetCampaignStatus:
    def test_without_confirm_returns_warning(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("set_campaign_status")
        result = tool(confirm=False, 
            campaign_id="100",
            status="ENABLED",
            customer_id="1234567890",
        )

        assert result["warning"] is True
        assert "confirm" in result["message"].lower()

    def test_with_confirm_succeeds(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("set_campaign_status")
        result = tool(
            campaign_id="100",
            status="ENABLED",
            confirm=True,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["new_status"] == "ENABLED"
        assert "resource_name" in result
        client.get_service("CampaignService").mutate_campaigns.assert_called_once()

    def test_pause_campaign(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("set_campaign_status")
        result = tool(
            campaign_id="100",
            status="PAUSED",
            confirm=True,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["new_status"] == "PAUSED"

    def test_removed_status_rejected(self, mock_ads_client):
        """REMOVED is not valid for set_campaign_status — use remove_campaign instead."""
        set_active_account("1234567890")

        tool = _register_tool("set_campaign_status")
        result = tool(
            campaign_id="100",
            status="REMOVED",
            confirm=True,
            customer_id="1234567890",
        )

        assert result["error"] is True

    def test_invalid_status_returns_error(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("set_campaign_status")
        result = tool(
            campaign_id="100",
            status="INVALID",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "Invalid status" in result["message"]


# ---------------------------------------------------------------------------
# No active account
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    def test_list_campaigns_no_account(self, mock_ads_client):
        tool = _register_tool("list_campaigns")
        result = tool()

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_get_campaign_no_account(self, mock_ads_client):
        tool = _register_tool("get_campaign")
        result = tool(campaign_id="100")

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_create_campaign_no_account(self, mock_ads_client):
        tool = _register_tool("create_campaign")
        result = tool(name="Test", budget_id="501")

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_update_campaign_no_account(self, mock_ads_client):
        tool = _register_tool("update_campaign")
        result = tool(campaign_id="100", name="New Name")

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_set_campaign_status_no_account(self, mock_ads_client):
        tool = _register_tool("set_campaign_status")
        result = tool(campaign_id="100", status="PAUSED", confirm=True)

        assert result["error"] is True
        assert "No customer_id" in result["message"]


# ---------------------------------------------------------------------------
# Invalid customer_id
# ---------------------------------------------------------------------------


class TestInvalidCustomerId:
    def test_list_campaigns_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("list_campaigns")
        result = tool(customer_id="abc-def")

        assert result["error"] is True
        assert "customer_id" in result["message"]

    def test_get_campaign_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("get_campaign")
        result = tool(campaign_id="100", customer_id="abc-def")

        assert result["error"] is True
        assert "customer_id" in result["message"]

    def test_create_campaign_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_campaign")
        result = tool(name="Test", budget_id="501", customer_id="abc-def")

        assert result["error"] is True
        assert "customer_id" in result["message"]

    def test_update_campaign_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_campaign")
        result = tool(campaign_id="100", name="X", customer_id="abc-def")

        assert result["error"] is True
        assert "customer_id" in result["message"]

    def test_set_campaign_status_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("set_campaign_status")
        # require_customer_id now validates customer_id format for all tools
        result = tool(campaign_id="100", status="PAUSED", confirm=True, customer_id="abc-def")

        assert result["error"] is True
        assert "customer_id" in result["message"]


# ---------------------------------------------------------------------------
# remove_campaign (internal tool)
# ---------------------------------------------------------------------------


class TestRemoveCampaign:
    def test_confirm_gate(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("remove_campaign")
        result = tool(confirm=False, campaign_id="100", customer_id="1234567890")

        assert result["warning"] is True
        assert "confirm" in result["message"].lower()

    def test_removes_campaign(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("remove_campaign")
        result = tool(campaign_id="100", confirm=True, customer_id="1234567890")

        assert result["removed"] is True
        assert "resource_name" in result
        client.get_service("CampaignService").mutate_campaigns.assert_called_once()

    def test_invalid_campaign_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("remove_campaign")
        result = tool(campaign_id="abc", confirm=True, customer_id="1234567890")

        assert result["error"] is True
        assert "campaign_id" in result["message"]

    def test_no_customer_id(self, mock_ads_client):
        tool = _register_tool("remove_campaign")
        result = tool(campaign_id="100", confirm=True)

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_invalid_customer_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("remove_campaign")
        result = tool(campaign_id="100", confirm=True, customer_id="abc-def")

        assert result["error"] is True
        assert "customer_id" in result["message"]
