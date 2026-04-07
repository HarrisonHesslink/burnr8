"""Tests for burnr8.tools.conversions — list/get with filters, new fields."""

from burnr8.session import set_active_account
from burnr8.tools.conversions import VALID_CONVERSION_CATEGORIES, VALID_CONVERSION_STATUSES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conversion_action_row(
    cid="700",
    name="Purchase",
    action_type="WEBPAGE",
    category="PURCHASE",
    status="ENABLED",
    counting_type="ONE_PER_CLICK",
    default_value=0.0,
    always_use_default=False,
    attribution_model="GOOGLE_ADS_LAST_CLICK",
    most_recent_conversion="2026-04-01 12:00:00",
    click_lookback_days=30,
    view_lookback_days=1,
    include_in_conversions=True,
):
    return {
        "conversion_action": {
            "id": cid,
            "name": name,
            "type": action_type,
            "category": category,
            "status": status,
            "counting_type": counting_type,
            "value_settings": {
                "default_value": default_value,
                "always_use_default_value": always_use_default,
            },
            "attribution_model_settings": {
                "attribution_model": attribution_model,
            },
            "most_recent_conversion_date": most_recent_conversion,
            "click_through_lookback_window_days": click_lookback_days,
            "view_through_lookback_window_days": view_lookback_days,
            "include_in_conversions_metric": include_in_conversions,
        }
    }


def _register_tool(name):
    """Register conversion tools and return the one matching *name*."""
    from burnr8.tools.conversions import register

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    register(cap)
    return captured["func"]


# ---------------------------------------------------------------------------
# Validation sets
# ---------------------------------------------------------------------------


class TestValidationSets:
    def test_valid_statuses(self):
        assert {"ENABLED", "REMOVED", "HIDDEN"} == VALID_CONVERSION_STATUSES

    def test_valid_categories(self):
        assert "PURCHASE" in VALID_CONVERSION_CATEGORIES
        assert "LEAD" in VALID_CONVERSION_CATEGORIES
        assert "SIGNUP" in VALID_CONVERSION_CATEGORIES
        assert len(VALID_CONVERSION_CATEGORIES) == 8


# ---------------------------------------------------------------------------
# list_conversion_actions — new fields
# ---------------------------------------------------------------------------


class TestListConversionActionsNewFields:
    def test_returns_activity_fields(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    _conversion_action_row(
                        most_recent_conversion="2026-04-01 12:00:00",
                        click_lookback_days=30,
                        view_lookback_days=1,
                        include_in_conversions=True,
                    ),
                ],
            }
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 1
        row = result[0]
        assert row["most_recent_conversion"] == "2026-04-01 12:00:00"
        assert row["click_lookback_days"] == 30
        assert row["view_lookback_days"] == 1
        assert row["include_in_conversions"] is True

    def test_returns_none_for_missing_activity_fields(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    {
                        "conversion_action": {
                            "id": "700",
                            "name": "Legacy Action",
                            "type": "WEBPAGE",
                            "category": "DEFAULT",
                            "status": "ENABLED",
                            "counting_type": "ONE_PER_CLICK",
                            "value_settings": {},
                            "attribution_model_settings": {},
                        }
                    }
                ],
            }
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890")

        row = result[0]
        assert row["most_recent_conversion"] is None
        assert row["click_lookback_days"] is None
        assert row["view_lookback_days"] is None
        assert row["include_in_conversions"] is None

    def test_output_has_all_expected_keys(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {"FROM conversion_action": [_conversion_action_row()]}
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890")

        expected_keys = {
            "id",
            "name",
            "type",
            "category",
            "status",
            "counting_type",
            "default_value",
            "always_use_default_value",
            "attribution_model",
            "most_recent_conversion",
            "click_lookback_days",
            "view_lookback_days",
            "include_in_conversions",
        }
        assert set(result[0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# list_conversion_actions — status filter
# ---------------------------------------------------------------------------


class TestListConversionActionsStatusFilter:
    def test_filter_by_status_enabled(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    _conversion_action_row(status="ENABLED"),
                ],
            }
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", status="ENABLED")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["status"] == "ENABLED"

    def test_invalid_status_returns_error(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", status="BOGUS")

        assert result["error"] is True
        assert "Invalid status" in result["message"]

    def test_status_case_insensitive(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {"FROM conversion_action": [_conversion_action_row(status="HIDDEN")]}
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", status="hidden")

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# list_conversion_actions — category filter
# ---------------------------------------------------------------------------


class TestListConversionActionsCategoryFilter:
    def test_filter_by_category_purchase(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    _conversion_action_row(category="PURCHASE"),
                ],
            }
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", category="PURCHASE")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["category"] == "PURCHASE"

    def test_invalid_category_returns_error(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", category="FAKE_CATEGORY")

        assert result["error"] is True
        assert "Invalid category" in result["message"]

    def test_category_case_insensitive(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {"FROM conversion_action": [_conversion_action_row(category="LEAD")]}
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", category="lead")

        assert isinstance(result, list)

    def test_filter_by_extended_category(self, mock_ads_client):
        """Categories like CONTACT exist in Google Ads but not in the create-only set."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {"FROM conversion_action": [_conversion_action_row(category="CONTACT")]}
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", category="CONTACT")

        assert isinstance(result, list)
        assert len(result) == 1

    def test_combined_status_and_category_filter(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    _conversion_action_row(status="ENABLED", category="LEAD"),
                ],
            }
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890", status="ENABLED", category="LEAD")

        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# list_conversion_actions — no filter (default)
# ---------------------------------------------------------------------------


class TestListConversionActionsNoFilter:
    def test_returns_all_actions(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    _conversion_action_row(cid="700", name="Purchase"),
                    _conversion_action_row(cid="701", name="Signup", category="SIGNUP"),
                ],
            }
        )

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 2

    def test_empty_list(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("list_conversion_actions")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# get_conversion_action — new fields
# ---------------------------------------------------------------------------


class TestGetConversionActionNewFields:
    def test_returns_activity_fields(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    _conversion_action_row(
                        cid="700",
                        most_recent_conversion="2026-03-15 09:30:00",
                        click_lookback_days=90,
                        view_lookback_days=7,
                        include_in_conversions=False,
                    ),
                ],
            }
        )

        tool = _register_tool("get_conversion_action")
        result = tool(conversion_action_id="700", customer_id="1234567890")

        assert result["most_recent_conversion"] == "2026-03-15 09:30:00"
        assert result["click_lookback_days"] == 90
        assert result["view_lookback_days"] == 7
        assert result["include_in_conversions"] is False


# ---------------------------------------------------------------------------
# No active account
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    def test_list_no_account(self, mock_ads_client):
        tool = _register_tool("list_conversion_actions")
        result = tool()

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_get_no_account(self, mock_ads_client):
        tool = _register_tool("get_conversion_action")
        result = tool(conversion_action_id="700")

        assert result["error"] is True
        assert "No customer_id" in result["message"]
