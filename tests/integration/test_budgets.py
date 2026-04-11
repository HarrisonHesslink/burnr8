# tests/integration/test_budgets.py
import pytest

from tests.integration.conftest import register_tool


def _register_tool(name):
    return register_tool(name, "budgets")


# Happy Path
# Sad Path
# Boundary & Edge Case
# Side Effects & State Changes


INVALID_CUSTOMER_IDS = [
    ("letters", "abc"),
    ("dashes", "123-456-789"),
    ("too_short", "123"),
    ("empty", ""),
    ("special_chars", "123!@#456"),
    ("spaces", "123 456"),
    ("too_long", "123456789012345"),
]

INVALID_BUDGET_AMOUNTS = [
    ("negative", -10.0),
    ("zero_explicit", 0),
]


class TestListBudgets:
    def test_list_budget_invalid_active_account(self):
        tool = _register_tool("list_budgets")
        result = tool()
        assert result["error"] is True
        assert "no active account" in result["message"].lower()

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_list_budgets_invalid_customer_id(self, label, customer_id):
        tool = _register_tool("list_budgets")
        result = tool(customer_id=customer_id)
        assert result["error"] is True, f"Expected error for {label} but got success"

    def test_list_budgets_passed_customer_id(self, test_customer_id):
        tool = _register_tool("list_budgets")
        result = tool(customer_id=test_customer_id)

        for budget in result:
            assert "id" in budget
            assert "name" in budget
            assert "amount_dollars" in budget
            assert "status" in budget
            assert "delivery_method" in budget
            assert "shared" in budget
            assert "campaigns_using" in budget


class TestBudgetCreation:
    # Create a budget to update, and clean up after tests
    @pytest.fixture(autouse=True, scope="class")
    def setup_budget(self, test_customer_id):
        yield
        # cleanup: remove the budget after all tests
        remove_tool = _register_tool("remove_orphan_budgets")
        remove_tool(confirm=True, customer_id=test_customer_id)

    @pytest.mark.parametrize("label,amount", INVALID_BUDGET_AMOUNTS)
    def test_create_budget_invalid_amount(self, label, amount, test_customer_id):
        tool = _register_tool("create_budget")
        result = tool(name="Invalid Amount Test", amount_dollars=amount, customer_id=test_customer_id)
        assert result.get("error") is True, f"Expected error for {label} but got: {result}"

    def test_create_budget_invalid_active_account(self):
        tool = _register_tool("create_budget")
        result = tool(name="Valid Name", amount_dollars=10.0)
        assert result["error"] is True
        assert "no active account" in result["message"].lower()

    def test_create_budget_negative_amount(self, test_customer_id):
        tool = _register_tool("create_budget")
        result = tool(name="Valid Name", amount_dollars=-5.0, customer_id=test_customer_id)
        assert result["error"] is True
        assert "greater than zero" in result["message"].lower()

    def test_create_budget_non_numeric_amount(self, test_customer_id):
        tool = _register_tool("create_budget")
        result = tool(name="Valid Name", amount_dollars="ten dollars", customer_id=test_customer_id)
        assert result["error"] is True

    def test_create_budget_valid_input(self, test_customer_id):
        tool = _register_tool("create_budget")
        result = tool(name="Valid Name", amount_dollars=10.0, customer_id=test_customer_id, confirm=True)
        assert "error" not in result or result["error"] is False, (
            f"Expected success but got error: {result.get('message', '')}"
        )
        assert "id" in result
        assert result["name"] == "Valid Name"
        assert result["amount_dollars"] == 10.0

        # Read-back: verify budget actually persisted
        list_tool = _register_tool("list_budgets")
        budgets = list_tool(customer_id=test_customer_id)
        created = [b for b in budgets if str(b.get("id")) == str(result["id"])]
        assert len(created) == 1, f"Created budget {result['id']} not found in list"
        assert created[0]["name"] == "Valid Name"


class TestBudgetUpdates:
    # Create a budget to update, and clean up after tests
    @pytest.fixture(autouse=True, scope="class")
    def setup_budget(self, test_customer_id):
        tool = _register_tool("create_budget")
        result = tool(name="Test Budget", amount_dollars=10.0, customer_id=test_customer_id, confirm=True)
        self.__class__.budget_id = result["id"]
        yield
        # cleanup: remove the budget after all tests
        remove_tool = _register_tool("remove_orphan_budgets")
        remove_tool(confirm=True, customer_id=test_customer_id)

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_update_budget_invalid_customer_id_confirm_false(self, label, customer_id):
        tool = _register_tool("update_budget")
        result = tool(
            budget_id=self.budget_id,
            amount_dollars=10.0,
            customer_id=customer_id,
        )

        assert result["error"] is True, f"Expected error for {label} but got success"

    def test_update_budget_invalid_amount_confirm_false(self, test_customer_id):
        tool = _register_tool("update_budget")
        result = tool(
            budget_id=self.budget_id,
            amount_dollars=-10.0,
            customer_id=test_customer_id,
        )
        print(result)  # Debug output to inspect the structure

        assert result["error"] is True
        assert "greater than zero" in result["message"].lower()

    def test_update_budget_valid_confirm_false(self, test_customer_id):
        tool = _register_tool("update_budget")
        result = tool(
            budget_id=self.budget_id,
            amount_dollars=11.0,
            customer_id=test_customer_id,
        )
        print(result)  # Debug output to inspect the structure

        assert result["warning"] is True

    def test_update_budget_valid_confirm_true(self, test_customer_id):
        tool = _register_tool("update_budget")

        result = tool(
            budget_id=self.budget_id,
            amount_dollars=12.0,
            customer_id=test_customer_id,
            confirm=True,
        )

        assert "error" not in result or result["error"] is False, (
            f"Expected success but got error: {result.get('message', '')}"
        )
        assert "resource_name" in result
        assert result["new_amount_dollars"] == 12.0

        # Read-back: verify budget amount actually changed
        list_tool = _register_tool("list_budgets")
        budgets = list_tool(customer_id=test_customer_id)
        updated = [b for b in budgets if str(b.get("id")) == str(self.budget_id)]
        assert len(updated) == 1, f"Budget {self.budget_id} not found after update"
        assert updated[0]["amount_dollars"] == 12.0

    def test_update_budget_invalid_active_account_confirm_false(self):
        tool = _register_tool("update_budget")

        result = tool(budget_id=self.budget_id, amount_dollars=18.0)
        print(result)  # Debug output to inspect the structure
        assert result["error"] is True
        assert "no active account" in result["message"].lower()


class TestBudgetOrphans:
    # Create an orphan budget to update, and clean up after tests
    @pytest.fixture(autouse=True, scope="class")
    def setup_budget(self, test_customer_id):
        tool = _register_tool("create_budget")
        result = tool(name="Test Budget", amount_dollars=10.0, customer_id=test_customer_id, confirm=True)
        self.__class__.budget_id = result["id"]
        yield
        # cleanup: remove the budget after all tests
        remove_tool = _register_tool("remove_orphan_budgets")
        remove_tool(confirm=True, customer_id=test_customer_id)

    def test_remove_orphan_budgets_invalid_active_account(self):
        tool = _register_tool("remove_orphan_budgets")
        result = tool()
        assert result["error"] is True
        assert "no active account" in result["message"].lower()

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_remove_orphan_budgets_invalid_customer_id(self, label, customer_id):
        tool = _register_tool("remove_orphan_budgets")
        result = tool(customer_id=customer_id)
        assert result["error"] is True, f"Expected error for {label} but got success"

    def test_remove_orphan_budgets_valid_customer_id_confirm_false(self, test_customer_id):
        tool = _register_tool("remove_orphan_budgets")
        result = tool(customer_id=test_customer_id)

        if result.get("warning"):
            # orphans found — dry run
            assert isinstance(result["orphan_budgets"], list)
            assert len(result["orphan_budgets"]) > 0
        else:
            # no orphans
            assert result["removed"] == 0
            assert "No orphan" in result["message"]

    def test_remove_orphan_budgets_valid_customer_id_confirm_true(self, test_customer_id):
        tool = _register_tool("remove_orphan_budgets")
        result = tool(customer_id=test_customer_id, confirm=True)
        assert "error" not in result or result["error"] is False, (
            f"Expected success but got error: {result.get('message', '')}"
        )
        assert "removed" in result
        if result["removed"] > 0:
            assert "removed_budgets" in result
            assert "id" in result["removed_budgets"][0]
        else:
            assert "No orphan" in result.get("message", "")
