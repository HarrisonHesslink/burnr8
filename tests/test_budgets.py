"""Tests for burnr8.tools.budgets — list_budgets, create_budget, update_budget, remove_orphan_budgets."""

from burnr8.session import set_active_account

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _budget_row(
    bid="501",
    name="Budget A",
    amount_micros=50_000_000,
    status="ENABLED",
    delivery_method="STANDARD",
    explicitly_shared=False,
    reference_count=1,
):
    return {
        "campaign_budget": {
            "id": bid,
            "name": name,
            "amount_micros": amount_micros,
            "status": status,
            "delivery_method": delivery_method,
            "explicitly_shared": explicitly_shared,
            "reference_count": reference_count,
        },
    }


def _register_tool(name):
    """Register budget tools and return the one matching *name*."""
    from burnr8.tools.budgets import register

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
# list_budgets
# ---------------------------------------------------------------------------


class TestListBudgets:
    def test_returns_budget_rows(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_budget": [
                    _budget_row(bid="501", name="Budget A", amount_micros=50_000_000),
                    _budget_row(
                        bid="502",
                        name="Budget B",
                        amount_micros=100_000_000,
                        reference_count=3,
                    ),
                ],
            }
        )

        tool = _register_tool("list_budgets")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 2

        first = result[0]
        assert first["id"] == "501"
        assert first["name"] == "Budget A"
        assert first["amount_dollars"] == 50.0
        assert first["status"] == "ENABLED"
        assert first["delivery_method"] == "STANDARD"
        assert first["shared"] is False
        assert first["campaigns_using"] == 1

        second = result[1]
        assert second["id"] == "502"
        assert second["amount_dollars"] == 100.0
        assert second["campaigns_using"] == 3

    def test_returns_empty_list_when_no_budgets(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("list_budgets")
        result = tool(customer_id="1234567890")

        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# create_budget
# ---------------------------------------------------------------------------


class TestCreateBudget:
    def test_creates_budget_successfully(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("create_budget")
        result = tool(
            name="New Budget",
            amount_dollars=25.0,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["id"] == "111"  # from conftest default resource name
        assert result["name"] == "New Budget"
        assert result["amount_dollars"] == 25.0
        assert "resource_name" in result

        # Verify mutate was called
        svc = client.get_service("CampaignBudgetService")
        svc.mutate_campaign_budgets.assert_called_once()
        # Verify explicitly_shared=False (critical for Smart Bidding — see CLAUDE.md)
        call_args = svc.mutate_campaign_budgets.call_args
        ops = call_args.kwargs.get("operations") or call_args[0][1]
        if not isinstance(ops, list):
            ops = [ops]
        assert ops[0].create.explicitly_shared is False


# ---------------------------------------------------------------------------
# update_budget
# ---------------------------------------------------------------------------


class TestUpdateBudget:
    def test_rejects_without_confirm(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("update_budget")
        result = tool(confirm=False,
            budget_id="501",
            amount_dollars=75.0,
            customer_id="1234567890",
        )

        assert result.get("warning") is True
        assert "501" in result["message"]
        assert "$75.00" in result["message"]

    def test_updates_with_confirm(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("update_budget")
        result = tool(
            budget_id="501",
            amount_dollars=75.0,
            confirm=True,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["new_amount_dollars"] == 75.0
        assert "resource_name" in result

        client.get_service("CampaignBudgetService").mutate_campaign_budgets.assert_called_once()


# ---------------------------------------------------------------------------
# remove_orphan_budgets
# ---------------------------------------------------------------------------


class TestRemoveOrphanBudgets:
    def test_no_orphans_found(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("remove_orphan_budgets")
        result = tool(customer_id="1234567890")

        assert result["removed"] == 0
        assert "No orphan" in result["message"]

    def test_dry_run_without_confirm(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "campaign_budget.reference_count = 0": [
                    _budget_row(bid="601", name="Orphan 1", amount_micros=10_000_000, reference_count=0),
                    _budget_row(bid="602", name="Orphan 2", amount_micros=20_000_000, reference_count=0),
                ],
            }
        )

        tool = _register_tool("remove_orphan_budgets")
        result = tool(confirm=False, customer_id="1234567890")

        assert result.get("warning") is True
        assert "2 orphan" in result["message"]
        assert len(result["orphan_budgets"]) == 2
        assert result["orphan_budgets"][0]["id"] == "601"
        assert result["orphan_budgets"][1]["id"] == "602"

    def test_deletes_with_confirm(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        mock_ads_client["set_gaql"](
            {
                "campaign_budget.reference_count = 0": [
                    _budget_row(bid="601", name="Orphan 1", amount_micros=10_000_000, reference_count=0),
                ],
            }
        )

        tool = _register_tool("remove_orphan_budgets")
        result = tool(confirm=True, customer_id="1234567890")

        assert result["removed"] == 1
        assert len(result["removed_budgets"]) == 1
        assert result["removed_budgets"][0]["id"] == "601"

        client.get_service("CampaignBudgetService").mutate_campaign_budgets.assert_called_once()


# ---------------------------------------------------------------------------
# No active account / invalid customer_id
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    def test_list_budgets_no_account(self, mock_ads_client):
        tool = _register_tool("list_budgets")
        result = tool()
        assert result["error"] is True
        assert "active account" in result["message"].lower() or "customer_id" in result["message"].lower()

    def test_create_budget_no_account(self, mock_ads_client):
        tool = _register_tool("create_budget")
        result = tool(name="Test", amount_dollars=10.0)
        assert result["error"] is True

    def test_update_budget_no_account(self, mock_ads_client):
        tool = _register_tool("update_budget")
        result = tool(budget_id="501", amount_dollars=10.0, confirm=True)
        assert result["error"] is True

    def test_remove_orphan_budgets_no_account(self, mock_ads_client):
        tool = _register_tool("remove_orphan_budgets")
        result = tool()
        assert result["error"] is True


class TestInvalidCustomerId:
    def test_list_budgets_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("list_budgets")
        result = tool(customer_id="abc-invalid")
        assert result["error"] is True
        assert "numeric" in result["message"].lower()

    def test_create_budget_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("create_budget")
        result = tool(name="Test", amount_dollars=10.0, customer_id="not-a-number")
        assert result["error"] is True
        assert "numeric" in result["message"].lower()

    def test_update_budget_invalid_customer_id(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("update_budget")
        result = tool(
            budget_id="501",
            amount_dollars=10.0,
            confirm=True,
            customer_id="bad!id",
        )
        assert result["error"] is True

    def test_remove_orphan_budgets_invalid_id(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("remove_orphan_budgets")
        result = tool(customer_id="xxx")
        assert result["error"] is True
