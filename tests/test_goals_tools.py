"""Tests for burnr8.tools.goals — name resolution, enrichment, edge cases."""

from unittest.mock import patch

from burnr8.session import set_active_account
from burnr8.tools.goals import _extract_action_id, _resolve_action_names

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_tool(name):
    """Register goals tools and return the one matching *name*."""
    from burnr8.tools.goals import register

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


def _conversion_goal_row(category="PURCHASE", origin="WEBSITE", biddable=True):
    return {
        "customer_conversion_goal": {
            "category": category,
            "origin": origin,
            "biddable": biddable,
        }
    }


def _action_row(aid="700", name="Purchase", category="PURCHASE"):
    return {
        "conversion_action": {
            "id": aid,
            "name": name,
            "category": category,
        }
    }


def _custom_goal_row(gid="900", name="My Goal", status="ENABLED", action_resource_names=None):
    return {
        "custom_conversion_goal": {
            "id": gid,
            "name": name,
            "status": status,
            "conversion_actions": action_resource_names or [],
        }
    }


# ---------------------------------------------------------------------------
# _extract_action_id
# ---------------------------------------------------------------------------


class TestExtractActionId:
    def test_valid_resource_name(self):
        assert _extract_action_id("customers/123/conversionActions/456") == "456"

    def test_no_slash(self):
        assert _extract_action_id("456") is None

    def test_empty_string(self):
        assert _extract_action_id("") is None

    def test_trailing_slash(self):
        assert _extract_action_id("customers/123/conversionActions/") is None

    def test_simple_slash(self):
        assert _extract_action_id("foo/bar") == "bar"


# ---------------------------------------------------------------------------
# _resolve_action_names
# ---------------------------------------------------------------------------


class TestResolveActionNames:
    def test_empty_list(self, mock_ads_client):
        result = _resolve_action_names(None, "1234567890", [])
        assert result == {}

    def test_resolves_ids(self, mock_ads_client):
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    {"conversion_action": {"id": "700", "name": "Purchase"}},
                    {"conversion_action": {"id": "701", "name": "Signup"}},
                ],
            }
        )
        client = mock_ads_client["client"]
        result = _resolve_action_names(client, "1234567890", ["700", "701"])
        assert result == {"700": "Purchase", "701": "Signup"}

    def test_partial_resolution(self, mock_ads_client):
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    {"conversion_action": {"id": "700", "name": "Purchase"}},
                ],
            }
        )
        client = mock_ads_client["client"]
        result = _resolve_action_names(client, "1234567890", ["700", "999"])
        assert result == {"700": "Purchase"}
        assert "999" not in result

    def test_non_numeric_ids_skipped(self, mock_ads_client):
        client = mock_ads_client["client"]
        result = _resolve_action_names(client, "1234567890", ["abc", "700"])
        assert result == {}

    def test_row_with_none_id_skipped(self, mock_ads_client):
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    {"conversion_action": {"id": None, "name": "Ghost"}},
                    {"conversion_action": {"id": "700", "name": "Purchase"}},
                ],
            }
        )
        client = mock_ads_client["client"]
        result = _resolve_action_names(client, "1234567890", ["700"])
        assert result == {"700": "Purchase"}
        assert "None" not in result


# ---------------------------------------------------------------------------
# list_conversion_goals — enrichment
# ---------------------------------------------------------------------------


class TestListConversionGoalsEnrichment:
    def test_enriches_with_actions_by_category(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM customer_conversion_goal": [
                    _conversion_goal_row(category="PURCHASE"),
                    _conversion_goal_row(category="LEAD", biddable=False),
                ],
                "FROM conversion_action": [
                    _action_row(aid="700", name="Purchase", category="PURCHASE"),
                    _action_row(aid="701", name="Lead Form", category="LEAD"),
                ],
            }
        )

        tool = _register_tool("list_conversion_goals")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 2

        purchase_goal = result[0]
        assert purchase_goal["category"] == "PURCHASE"
        assert purchase_goal["conversion_actions"] == [{"id": "700", "name": "Purchase"}]

        lead_goal = result[1]
        assert lead_goal["category"] == "LEAD"
        assert lead_goal["conversion_actions"] == [{"id": "701", "name": "Lead Form"}]

    def test_goal_with_no_matching_actions(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM customer_conversion_goal": [
                    _conversion_goal_row(category="SIGNUP"),
                ],
                "FROM conversion_action": [
                    _action_row(aid="700", name="Purchase", category="PURCHASE"),
                ],
            }
        )

        tool = _register_tool("list_conversion_goals")
        result = tool(customer_id="1234567890")

        assert result[0]["conversion_actions"] == []

    def test_enrichment_failure_degrades_gracefully(self, mock_ads_client):
        set_active_account("1234567890")

        with patch("burnr8.tools.goals.run_gaql") as mock_rg:
            calls = []

            def _side_effect(_client, _cid, query, limit=0):
                calls.append(query)
                if "FROM customer_conversion_goal" in query:
                    return [_conversion_goal_row(category="PURCHASE")]
                raise RuntimeError("Simulated action query failure")

            mock_rg.side_effect = _side_effect

            tool = _register_tool("list_conversion_goals")
            result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["conversion_actions"] == []


# ---------------------------------------------------------------------------
# list_custom_conversion_goals — name resolution
# ---------------------------------------------------------------------------


class TestListCustomConversionGoals:
    def test_resolves_action_names(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM custom_conversion_goal": [
                    _custom_goal_row(
                        gid="900",
                        name="My Goal",
                        action_resource_names=["customers/123/conversionActions/700"],
                    ),
                ],
                "FROM conversion_action": [
                    {"conversion_action": {"id": "700", "name": "Purchase"}},
                ],
            }
        )

        tool = _register_tool("list_custom_conversion_goals")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 1
        goal = result[0]
        assert goal["id"] == "900"
        assert goal["conversion_actions"] == [{"id": "700", "name": "Purchase"}]

    def test_empty_goals(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("list_custom_conversion_goals")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_resolution_failure_returns_null_names(self, mock_ads_client):
        set_active_account("1234567890")

        with patch("burnr8.tools.goals.run_gaql") as mock_rg:
            def _side_effect(_client, _cid, query, limit=0):
                if "FROM custom_conversion_goal" in query:
                    return [
                        _custom_goal_row(
                            action_resource_names=["customers/123/conversionActions/700"],
                        )
                    ]
                raise RuntimeError("Simulated failure")

            mock_rg.side_effect = _side_effect

            tool = _register_tool("list_custom_conversion_goals")
            result = tool(customer_id="1234567890")

        assert len(result) == 1
        assert result[0]["conversion_actions"] == [{"id": "700", "name": None}]

    def test_deduplicates_action_ids(self, mock_ads_client):
        """Two goals sharing the same action should only resolve it once."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM custom_conversion_goal": [
                    _custom_goal_row(
                        gid="900",
                        name="Goal A",
                        action_resource_names=["customers/123/conversionActions/700"],
                    ),
                    _custom_goal_row(
                        gid="901",
                        name="Goal B",
                        action_resource_names=["customers/123/conversionActions/700"],
                    ),
                ],
                "FROM conversion_action": [
                    {"conversion_action": {"id": "700", "name": "Purchase"}},
                ],
            }
        )

        tool = _register_tool("list_custom_conversion_goals")
        result = tool(customer_id="1234567890")

        assert len(result) == 2
        assert result[0]["conversion_actions"] == [{"id": "700", "name": "Purchase"}]
        assert result[1]["conversion_actions"] == [{"id": "700", "name": "Purchase"}]


# ---------------------------------------------------------------------------
# set_campaign_conversion_goal — response shape
# ---------------------------------------------------------------------------


class TestSetCampaignConversionGoal:
    def _get_custom_goal_op(self, mock_ads_client):
        svc = mock_ads_client["client"].get_service("CustomConversionGoalService")
        call_args = svc.mutate_custom_conversion_goals.call_args
        ops = call_args.kwargs["request"].operations
        if ops and not isinstance(ops, list):
            ops = [ops]
        return ops[0]

    def _get_config_op(self, mock_ads_client):
        svc = mock_ads_client["client"].get_service("ConversionGoalCampaignConfigService")
        call_args = svc.mutate_conversion_goal_campaign_configs.call_args
        ops = call_args.kwargs["request"].operations
        if ops and not isinstance(ops, list):
            ops = [ops]
        return ops[0]

    def test_returns_resolved_actions(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM conversion_action": [
                    {"conversion_action": {"id": "700", "name": "Purchase"}},
                ],
            }
        )

        tool = _register_tool("set_campaign_conversion_goal")
        result = tool(
            campaign_id="222",
            conversion_action_ids=["700"],
            customer_id="1234567890",
        )

        assert "conversion_actions" in result
        assert result["conversion_actions"] == [{"id": "700", "name": "Purchase"}]
        assert result["goal_config_level"] == "CAMPAIGN"
        assert "conversion_action_ids" not in result

    def test_proto_custom_goal_fields(self, mock_ads_client):
        """Verify the proto sent to CustomConversionGoalService."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {"FROM conversion_action": [{"conversion_action": {"id": "700", "name": "Purchase"}}]}
        )

        tool = _register_tool("set_campaign_conversion_goal")
        tool(campaign_id="222", conversion_action_ids=["700"], customer_id="1234567890")

        op = self._get_custom_goal_op(mock_ads_client)
        assert op.create.name == "Campaign 222 Goal"
        assert op.create.status == "ENABLED"
        # conversion_actions is a real list (from conftest); verify resource name appended
        assert len(op.create.conversion_actions) == 1

    def test_proto_config_fields(self, mock_ads_client):
        """Verify the proto sent to ConversionGoalCampaignConfigService."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {"FROM conversion_action": [{"conversion_action": {"id": "700", "name": "Purchase"}}]}
        )

        tool = _register_tool("set_campaign_conversion_goal")
        tool(campaign_id="222", conversion_action_ids=["700"], customer_id="1234567890")

        op = self._get_config_op(mock_ads_client)
        assert op.update.goal_config_level == "CAMPAIGN"
        assert "goal_config_level" in op.update_mask.paths
        assert "custom_conversion_goal" in op.update_mask.paths

    def test_resolution_failure_returns_null_names(self, mock_ads_client):
        set_active_account("1234567890")

        with patch("burnr8.tools.goals.run_gaql") as mock_rg:
            def _side_effect(_client, _cid, query, limit=0):
                if "FROM conversion_action" in query:
                    raise RuntimeError("Simulated failure")
                return []

            mock_rg.side_effect = _side_effect

            tool = _register_tool("set_campaign_conversion_goal")
            result = tool(
                campaign_id="222",
                conversion_action_ids=["700"],
                customer_id="1234567890",
            )

        assert result["conversion_actions"] == [{"id": "700", "name": None}]

    def test_empty_action_ids_error(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("set_campaign_conversion_goal")
        result = tool(campaign_id="222", conversion_action_ids=[], customer_id="1234567890")

        assert result["error"] is True
        assert "must not be empty" in result["message"]


# ---------------------------------------------------------------------------
# No active account
# ---------------------------------------------------------------------------


class TestGoalsNoActiveAccount:
    def test_list_goals_no_account(self, mock_ads_client):
        tool = _register_tool("list_conversion_goals")
        result = tool()
        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_list_custom_goals_no_account(self, mock_ads_client):
        tool = _register_tool("list_custom_conversion_goals")
        result = tool()
        assert result["error"] is True
        assert "No customer_id" in result["message"]
