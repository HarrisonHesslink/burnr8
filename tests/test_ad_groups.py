"""Tests for burnr8.tools.ad_groups — list, create, update ad groups."""

from burnr8.session import set_active_account

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_tool(name):
    """Register ad group tools and return the one matching *name*."""
    from burnr8.tools.ad_groups import register

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


def _ad_group_row(
    ag_id="333",
    name="Ad Group A",
    status="ENABLED",
    ag_type="SEARCH_STANDARD",
    cpc_bid_micros=1_500_000,
    campaign_id="222",
    campaign_name="Campaign A",
    impressions=100,
    clicks=10,
    cost_micros=5_000_000,
):
    return {
        "ad_group": {
            "id": ag_id,
            "name": name,
            "status": status,
            "type": ag_type,
            "cpc_bid_micros": cpc_bid_micros,
        },
        "campaign": {"id": campaign_id, "name": campaign_name},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
        },
    }


# ---------------------------------------------------------------------------
# list_ad_groups
# ---------------------------------------------------------------------------


class TestListAdGroups:
    def test_returns_ad_groups(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM ad_group": [_ad_group_row()]})
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert len(result) == 1
        assert result[0]["id"] == "333"
        assert result[0]["name"] == "Ad Group A"
        assert result[0]["status"] == "ENABLED"
        assert result[0]["campaign_id"] == "222"
        assert result[0]["campaign_name"] == "Campaign A"

    def test_converts_micros_to_dollars(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM ad_group": [
            _ad_group_row(cpc_bid_micros=2_500_000, cost_micros=10_000_000)
        ]})
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert result[0]["cpc_bid_dollars"] == 2.50
        assert result[0]["cost_dollars"] == 10.00

    def test_filter_by_campaign(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM ad_group": [_ad_group_row()]})
        fn = _register_tool("list_ad_groups")
        result = fn(campaign_id="222")
        assert len(result) == 1

    def test_empty_results(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert result == []

    def test_no_customer_id(self):
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_invalid_customer_id(self, mock_ads_client):
        set_active_account("bad-id")
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert result["error"] is True

    def test_invalid_campaign_id_filter(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("list_ad_groups")
        result = fn(campaign_id="not-numeric")
        assert result["error"] is True

    def test_multiple_ad_groups(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM ad_group": [
            _ad_group_row(ag_id="333", name="Group A"),
            _ad_group_row(ag_id="444", name="Group B"),
        ]})
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert len(result) == 2
        assert result[0]["id"] == "333"
        assert result[1]["id"] == "444"

    def test_zero_metrics(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM ad_group": [
            _ad_group_row(impressions=0, clicks=0, cost_micros=0)
        ]})
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert result[0]["impressions"] == 0
        assert result[0]["clicks"] == 0
        assert result[0]["cost_dollars"] == 0.0

    def test_tracking_url_fields_returned(self, mock_ads_client):
        set_active_account("1234567890")
        row = _ad_group_row()
        row["ad_group"]["tracking_url_template"] = "{lpurl}?src=google"
        row["ad_group"]["final_url_suffix"] = "utm_source=google"
        row["ad_group"]["url_custom_parameters"] = [{"key": "season", "value": "winter"}]
        mock_ads_client["set_gaql"]({"FROM ad_group": [row]})
        fn = _register_tool("list_ad_groups")
        result = fn()
        assert result[0]["tracking_url_template"] == "{lpurl}?src=google"
        assert result[0]["final_url_suffix"] == "utm_source=google"
        assert result[0]["url_custom_parameters"] == {"season": "winter"}


# ---------------------------------------------------------------------------
# create_ad_group
# ---------------------------------------------------------------------------


class TestCreateAdGroup:
    def test_creates_ad_group(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_ad_group")
        result = fn(campaign_id="222", name="New Ad Group")
        assert result["name"] == "New Ad Group"
        assert "resource_name" in result
        assert "id" in result

    def test_default_cpc_bid(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_ad_group")
        fn(campaign_id="222", name="Test")
        # Verify AdGroupService was called
        svc = mock_ads_client["client"].get_service("AdGroupService")
        svc.mutate_ad_groups.assert_called_once()

    def test_custom_cpc_bid(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_ad_group")
        result = fn(campaign_id="222", name="Test", cpc_bid=2.50)
        assert "resource_name" in result

    def test_no_customer_id(self):
        fn = _register_tool("create_ad_group")
        result = fn(campaign_id="222", name="Test")
        assert result["error"] is True

    def test_invalid_campaign_id(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_ad_group")
        result = fn(campaign_id="bad-id", name="Test")
        assert result["error"] is True

    def test_extracts_id_from_resource_name(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_ad_group")
        result = fn(campaign_id="222", name="Test")
        # Mock returns "customers/1234567890/adGroups/333"
        assert result["id"] == "333"

    def test_create_with_tracking_url_template(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        fn = _register_tool("create_ad_group")
        result = fn(
            campaign_id="222",
            name="Tracked Group",
            tracking_url_template="{lpurl}?utm_source=google",
            final_url_suffix="utm_medium=cpc",
        )
        assert "error" not in result
        assert result["name"] == "Tracked Group"
        # Verify proto fields were actually set
        call_args = client.get_service("AdGroupService").mutate_ad_groups.call_args
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
        fn = _register_tool("create_ad_group")
        result = fn(
            campaign_id="222",
            name="Custom Params Group",
            url_custom_parameters={"season": "winter", "promo": "sale"},
        )
        assert "error" not in result
        assert result["url_custom_parameters"] == {"season": "winter", "promo": "sale"}
        # Verify url_custom_parameters list was populated with 2 items (real list from conftest)
        call_args = client.get_service("AdGroupService").mutate_ad_groups.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert len(op.create.url_custom_parameters) == 2
            for param in op.create.url_custom_parameters:
                assert hasattr(param, "key")
                assert hasattr(param, "value")


# ---------------------------------------------------------------------------
# update_ad_group
# ---------------------------------------------------------------------------


class TestUpdateAdGroup:
    def test_update_name(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", name="Renamed")
        assert "name" in result["updated_fields"]
        assert "resource_name" in result

    def test_update_cpc_bid(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", cpc_bid=3.00)
        assert "cpc_bid_micros" in result["updated_fields"]

    def test_update_status_enabled(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", status="ENABLED")
        assert "status" in result["updated_fields"]

    def test_update_status_paused(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", status="PAUSED")
        assert "status" in result["updated_fields"]

    def test_update_multiple_fields(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", name="New Name", cpc_bid=5.00, status="PAUSED")
        assert set(result["updated_fields"]) == {"name", "cpc_bid_micros", "status"}

    def test_no_fields_returns_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333")
        assert result["error"] is True
        assert "No fields" in result["message"]

    def test_invalid_status(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", status="BANANA")
        assert result["error"] is True

    def test_no_customer_id(self):
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", name="Test")
        assert result["error"] is True

    def test_invalid_ad_group_id(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="bad-id", name="Test")
        assert result["error"] is True

    def test_case_insensitive_status(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", status="paused")
        assert "status" in result["updated_fields"]

    def test_update_status_removed(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", status="REMOVED")
        assert "status" in result["updated_fields"]

    def test_update_tracking_url_template(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", tracking_url_template="{lpurl}?src=google")
        assert "tracking_url_template" in result["updated_fields"]
        # Verify proto field was set
        call_args = client.get_service("AdGroupService").mutate_ad_groups.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.update.tracking_url_template == "{lpurl}?src=google"
            assert "tracking_url_template" in op.update_mask.paths

    def test_update_final_url_suffix(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", final_url_suffix="utm_source=google")
        assert "final_url_suffix" in result["updated_fields"]
        # Verify proto field was set
        call_args = client.get_service("AdGroupService").mutate_ad_groups.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.update.final_url_suffix == "utm_source=google"
            assert "final_url_suffix" in op.update_mask.paths

    def test_clear_tracking_url_template(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", tracking_url_template="")
        assert "tracking_url_template" in result["updated_fields"]
        # Verify proto was set to empty string (clear)
        call_args = client.get_service("AdGroupService").mutate_ad_groups.call_args
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
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", url_custom_parameters={"season": "winter"})
        assert "url_custom_parameters" in result["updated_fields"]
        # Verify field mask
        call_args = client.get_service("AdGroupService").mutate_ad_groups.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert "url_custom_parameters" in op.update_mask.paths

    def test_clear_url_custom_parameters(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        fn = _register_tool("update_ad_group")
        result = fn(ad_group_id="333", url_custom_parameters={})
        assert "url_custom_parameters" in result["updated_fields"]
        # Verify field mask is set (clearing means field mask present with no params appended)
        call_args = client.get_service("AdGroupService").mutate_ad_groups.call_args
        operation = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert "url_custom_parameters" in op.update_mask.paths

    def test_uses_field_mask(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_ad_group")
        fn(ad_group_id="333", name="X")
        svc = mock_ads_client["client"].get_service("AdGroupService")
        svc.mutate_ad_groups.assert_called_once()
