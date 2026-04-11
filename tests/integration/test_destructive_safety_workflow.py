# tests/integration/test_destructive_safety_workflow.py
import pytest

# Happy Path
# Sad Path
# Boundary & Edge Case
# Side Effects & State Changes


DESTRUCTIVE_TOOLS = [
    ("campaigns", "set_campaign_status", {"campaign_id": "123", "status": "REMOVED"}),
    ("budgets", "update_budget", {"budget_id": "123", "amount_dollars": 999}),
    ("keywords", "remove_keyword", {"criterion_id": "123", "ad_group_id": "456"}),
]

def _register_tool(tool_name, module_name):
    """Register list_accessible_accounts tools and return the one matching *name*."""
    from importlib import import_module
    mod = import_module(f"burnr8.tools.{module_name}")

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == tool_name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    mod.register(cap)
    return captured["func"]

@pytest.mark.parametrize("module,tool_name,kwargs", DESTRUCTIVE_TOOLS)
def test_destructive_tool_requires_confirm(module, tool_name, kwargs, test_customer_id):
    tool = _register_tool(tool_name, module)
    result = tool(customer_id=test_customer_id, **kwargs)

    print(result)

    assert result.get("warning") is True or result.get("error") is True
    # Must NOT have a resource_name (proof nothing was mutated)
    assert "resource_name" not in result
