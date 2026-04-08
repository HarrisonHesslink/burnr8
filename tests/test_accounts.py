"""Tests for burnr8.tools.accounts — list, create, update ad groups."""

# ---------------------------------------------------------------------------
# list_accessible_accounts — List all Google Ads customer accounts accessible via the manager account. Shows account names and IDs for easy selection.
# ---------------------------------------------------------------------------

class TestCreateListAccessibleAccounts:
    def test_list_accounts(self, mock_accounts_client):
        client = mock_accounts_client["client"]
        result = list_accessible_accounts()
        assert "accounts" in result
        assert isinstance(result["accounts"], list)
        assert len(result["accounts"]) == 2
        assert result["accounts"][0]["customer_id"] == "1234567890"
        assert result["accounts"][0]["name"] == "Test Account 1"
        assert result["accounts"][0]["is_manager"] is False
        assert result["accounts"][0]["status"] == "ENABLED"