# tests/integration/test_list_accounts.py
import pytest

# Happy Path
# Sad Path
# Boundary & Edge Case
# Side Effects & State Changes


INVALID_CUSTOMER_IDS = [
    ("letters", "abc"),
    ("dashes", "123-456-789"),
    ("empty", ""),
    ("special_chars", "123!@#456"),
    ("spaces", "123 456"),
]

INVALID_ERROR_COUNTS = [
    ("negative", -1),
    ("non_numeric", "many"),
    ("float", 3.14),
    ("null", None),
]

def _register_tool(name):
    """Register list_accessible_accounts tools and return the one matching *name*."""
    from burnr8.tools.accounts import register

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    register(cap)
    return captured["func"]

class TestListAccounts:
    def test_list_accessible_accounts_returns_valid_structure(self):
        # Real call through your actual client
        tool = _register_tool("list_accessible_accounts")

        result = tool() # Pass a valid customer_id if required by your implementation

        # Assert shape/contract, not specific data
        assert isinstance(result, dict)
        assert "accounts" in result
        assert isinstance(result["accounts"], list)

        for account in result["accounts"]:
            assert "customer_id" in account
            assert "name" in account

class TestActiveAccountResolution:
    def test_set_active_account(self, test_customer_id):
        tool = _register_tool("set_active_account_tool")
        list_tool = _register_tool("list_accessible_accounts")
        get_tool = _register_tool("get_active_account_tool")

        result = tool(customer_id=test_customer_id)
        list_result = list_tool()
        get_result = get_tool()

        assert isinstance(result["name"], str)
        assert result["active_account"] == test_customer_id

        # After setting active account, list_accessible_accounts should reflect the change
        assert "accounts" in list_result
        assert isinstance(list_result["accounts"], list)
        assert list_result["active_account"] == test_customer_id
        assert list_result["hint"] is None

        #After setting active account, get_active_account_tool should return the correct active account
        assert get_result["active_account"] == test_customer_id

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_set_active_account_bad_customer_id(self, label, customer_id):
        tool = _register_tool("set_active_account_tool")
        list_tool = _register_tool("list_accessible_accounts")
        get_tool = _register_tool("get_active_account_tool")

        result = tool(customer_id=customer_id)

        print(result)  # For debugging — shows actual API response structure and data

        assert result["error"] is True

        # Active account should not change after invalid input
        list_result = list_tool()
        get_result = get_tool()
        assert list_result["active_account"] is None
        assert get_result["active_account"] is None


class TestGetAccountInfo:
    def test_get_account_info(self, test_customer_id):
        tool = _register_tool("get_account_info")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert result.get("id") == test_customer_id
        assert "time_zone" in result
        assert "manager" in result
        assert "resource_name" in result

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_get_account_info_no_customer_id(self, label, customer_id):
        tool = _register_tool("get_account_info")
        result = tool(customer_id=customer_id)
        assert result["error"] is True

class TestGetApiUsage:
    def test_get_api_usage(self, test_customer_id):
        tool = _register_tool("get_api_usage")
        result = tool()

        assert isinstance(result, dict)
        assert "ops_limit" in result
        assert "ops_today" in result
        assert "date" in result
        assert "ops_pct"    in result
        assert "errors_today" in result
        assert isinstance(result["recent_calls"], list)

class TestGetRecentErrors:
    def test_get_recent_errors(self):
        tool = _register_tool("get_recent_errors_tool")
        result = tool(limit=5)

        assert isinstance(result, dict)
        assert "error_count" in result
        assert "errors" in result
        assert isinstance(result["errors"], list)
        assert len(result["errors"]) <= 5
        assert "log_file" in result

    @pytest.mark.parametrize("label,error_count", INVALID_ERROR_COUNTS)
    def test_get_recent_errors_invalid_limit(self, label, error_count):
        tool = _register_tool("get_recent_errors_tool")
        result = tool(limit=error_count)
        assert result.get("error") is True, f"Expected error for {label}, got: {result}"
