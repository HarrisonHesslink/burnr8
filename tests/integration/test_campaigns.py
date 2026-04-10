# tests/integration/test_campaigns.py
import pytest

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

INVALID_BUDGET_NAME = [
    ("negative", -1),
    ("float", 3.14),
    ("null", None),
    ("empty", ""),
    ("too_long", "B" * 256),  # Assuming 255 char limit
    ("special_chars", "Budget!@#")
]

def _register_tool(name):
    """Register list_accessible_accounts tools and return the one matching *name*."""
    from burnr8.tools.campaigns import register

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    register(cap)
    return captured["func"]

class TestCreateCampaign:
    def test_create_campaign_invalid_resource_budget(self, test_customer_id):
        tool = _register_tool("create_campaign")
        result = tool(name="Test Campaign", budget_id="123", customer_id=test_customer_id)

        assert result["error"] is True
        assert "status" in result


    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_create_campaign_invalid_customer_id(self, label, customer_id):
        tool = _register_tool("create_campaign")
        result = tool(name="Test Campaign", budget_id="123", customer_id=customer_id)

        assert result["error"] is True, f"Expected error for {label} but got success"

class TestUpdateCampaign:
    def test_update_campaign_invalid_resource_budget(self, test_customer_id):
        tool = _register_tool("update_campaign")
        result = tool(campaign_id="123", budget_id="123", customer_id=test_customer_id)

        assert result["error"] is True
        assert "status" in result

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_update_campaign_invalid_customer_id(self, label, customer_id):
        tool = _register_tool("update_campaign")
        result = tool(campaign_id="123", budget_id="123", customer_id=customer_id)

        assert result["error"] is True, f"Expected error for {label} but got success"

class TestSetCampaignStatus:
    def test_set_campaign_status_invalid_resource_no_confirmation(self, test_customer_id):
        """With confirm=False and invalid campaign_id, API validate_only returns an error."""
        tool = _register_tool("set_campaign_status")
        result = tool(campaign_id="123", status="PAUSED", confirm=False, customer_id=test_customer_id)

        # Server-side validation catches invalid resource even in dry-run mode
        assert result.get("error") is True or result.get("warning") is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_set_campaign_status_invalid_customer_id(self, label, customer_id):
        tool = _register_tool("set_campaign_status")
        result = tool(campaign_id="123", status="PAUSED", confirm=False, customer_id=customer_id)

        assert result["error"] is True, f"Expected error for {label} but got success"

    def test_set_campaign_status_invalid_status(self, test_customer_id):
        tool = _register_tool("set_campaign_status")
        result = tool(campaign_id="123", status="REMOVED", confirm=False, customer_id=test_customer_id)

        assert result["error"] is True
        assert "REMOVED" in result.get("message", "") or "status" in result

class TestRemoveCampaign:
    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_remove_campaign_invalid_customer_id(self, label, customer_id):
        tool = _register_tool("remove_campaign")
        result = tool(campaign_id="123", confirm=True, customer_id=customer_id)

        assert result["error"] is True, f"Expected error for {label} but got success"
