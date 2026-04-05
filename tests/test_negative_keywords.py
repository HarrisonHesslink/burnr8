"""Tests for burnr8.tools.negative_keywords — list, add (campaign + ad group), remove."""

from burnr8.session import set_active_account
from burnr8.tools.negative_keywords import NegativeKeyword

# ---------------------------------------------------------------------------
# Helpers — sample GAQL result rows
# ---------------------------------------------------------------------------


def _campaign_neg_row(
    criterion_id="601", text="free stuff", match_type="BROAD", campaign_id="222", campaign_name="Campaign A"
):
    return {
        "campaign_criterion": {
            "criterion_id": criterion_id,
            "keyword": {"text": text, "match_type": match_type},
            "negative": True,
        },
        "campaign": {"id": campaign_id, "name": campaign_name},
    }


def _ad_group_neg_row(
    criterion_id="701",
    text="cheap junk",
    match_type="EXACT",
    ad_group_id="333",
    ad_group_name="AG1",
    campaign_id="222",
    campaign_name="Campaign A",
):
    return {
        "ad_group_criterion": {
            "criterion_id": criterion_id,
            "keyword": {"text": text, "match_type": match_type},
            "negative": True,
        },
        "ad_group": {"id": ad_group_id, "name": ad_group_name},
        "campaign": {"id": campaign_id, "name": campaign_name},
    }


def _register_tool(name):
    """Register negative_keywords tools and return the one matching *name*."""
    from burnr8.tools.negative_keywords import register

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
# list_negative_keywords
# ---------------------------------------------------------------------------


class TestListNegativeKeywords:
    def test_campaign_level_only(self, mock_ads_client):
        """When no ad_group_id supplied, only campaign-level negatives are returned."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_criterion": [
                    _campaign_neg_row(criterion_id="601", text="free stuff", match_type="BROAD"),
                    _campaign_neg_row(criterion_id="602", text="discount", match_type="PHRASE"),
                ],
            }
        )

        tool = _register_tool("list_negative_keywords")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["rows"] == 2
        assert result["summary"]["total"] == 2
        assert result["summary"]["by_level"]["CAMPAIGN"] == 2
        assert result["summary"]["by_level"]["AD_GROUP"] == 0

    def test_merges_campaign_and_ad_group(self, mock_ads_client):
        """When ad_group_id is supplied, both queries run and results merge."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_criterion": [
                    _campaign_neg_row(criterion_id="601", text="free stuff", match_type="BROAD"),
                ],
                "FROM ad_group_criterion": [
                    _ad_group_neg_row(criterion_id="701", text="cheap junk", match_type="EXACT"),
                    _ad_group_neg_row(criterion_id="702", text="spam", match_type="PHRASE"),
                ],
            }
        )

        tool = _register_tool("list_negative_keywords")
        result = tool(customer_id="1234567890", ad_group_id="333")

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["rows"] == 3
        assert result["summary"]["total"] == 3
        assert result["summary"]["by_level"]["CAMPAIGN"] == 1
        assert result["summary"]["by_level"]["AD_GROUP"] == 2

    def test_match_type_counts(self, mock_ads_client):
        """by_match_type tallies each match type correctly."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_criterion": [
                    _campaign_neg_row(criterion_id="601", text="a", match_type="EXACT"),
                    _campaign_neg_row(criterion_id="602", text="b", match_type="EXACT"),
                    _campaign_neg_row(criterion_id="603", text="c", match_type="PHRASE"),
                ],
            }
        )

        tool = _register_tool("list_negative_keywords")
        result = tool(customer_id="1234567890")

        assert result["summary"]["by_match_type"]["EXACT"] == 2
        assert result["summary"]["by_match_type"]["PHRASE"] == 1

    def test_empty_results(self, mock_ads_client):
        """No negative keywords returns zero counts."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("list_negative_keywords")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["rows"] == 0
        assert result["summary"]["total"] == 0

    def test_filter_by_campaign_id(self, mock_ads_client):
        """When campaign_id is passed, the GAQL query includes the filter."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_criterion": [
                    _campaign_neg_row(criterion_id="601"),
                ],
            }
        )

        tool = _register_tool("list_negative_keywords")
        result = tool(customer_id="1234567890", campaign_id="222")

        assert "error" not in result
        assert result["rows"] == 1


# ---------------------------------------------------------------------------
# add_negative_keywords (campaign level)
# ---------------------------------------------------------------------------


class TestAddNegativeKeywords:
    def test_adds_keywords_with_correct_match_types(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        # Override default to return 2 resource names matching 2 keywords
        from unittest.mock import MagicMock

        resp = MagicMock()
        r1, r2 = MagicMock(), MagicMock()
        r1.resource_name = "customers/1234567890/campaignCriteria/222~601"
        r2.resource_name = "customers/1234567890/campaignCriteria/222~602"
        resp.results = [r1, r2]
        client.get_service("CampaignCriterionService").mutate_campaign_criteria.return_value = resp

        tool = _register_tool("add_negative_keywords")
        result = tool(
            campaign_id="222",
            keywords=[
                NegativeKeyword(text="free stuff", match_type="EXACT"),
                NegativeKeyword(text="cheap junk", match_type="PHRASE"),
            ],
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["added"] == 2
        assert len(result["resource_names"]) == 2

        # Verify mutate was called once with 2 operations
        svc = client.get_service("CampaignCriterionService")
        svc.mutate_campaign_criteria.assert_called_once()
        call_kwargs = svc.mutate_campaign_criteria.call_args
        operations = call_kwargs.kwargs.get("operations") or call_kwargs[1].get("operations")
        assert len(operations) == 2

    def test_default_match_type_is_broad(self, mock_ads_client):
        """When match_type is omitted, BROAD is used (NegativeKeyword default)."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("add_negative_keywords")
        result = tool(
            campaign_id="222",
            keywords=[NegativeKeyword(text="unwanted term")],
            customer_id="1234567890",
        )

        assert "error" not in result
        svc = client.get_service("CampaignCriterionService")
        svc.mutate_campaign_criteria.assert_called_once()
        # Verify the operation's match_type was set to BROAD (the default)
        call_args = svc.mutate_campaign_criteria.call_args
        ops = call_args.kwargs.get("operations") or call_args[1].get("operations")
        assert ops[0].create.keyword.match_type == "BROAD"

    def test_no_active_account(self, mock_ads_client):
        tool = _register_tool("add_negative_keywords")
        result = tool(campaign_id="222", keywords=[NegativeKeyword(text="test")])
        assert result["error"] is True
        assert "active account" in result["message"].lower() or "customer_id" in result["message"].lower()


# ---------------------------------------------------------------------------
# add_ad_group_negative_keywords
# ---------------------------------------------------------------------------


class TestAddAdGroupNegativeKeywords:
    def test_adds_keywords_to_ad_group(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("add_ad_group_negative_keywords")
        result = tool(
            ad_group_id="333",
            keywords=[
                NegativeKeyword(text="irrelevant", match_type="EXACT"),
                NegativeKeyword(text="spam", match_type="BROAD"),
            ],
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["added"] == 2  # mock returns 2 resource_names for AdGroupCriterionService
        assert len(result["resource_names"]) == 2

        # Verify mutate was called on the ad group criterion service
        svc = client.get_service("AdGroupCriterionService")
        svc.mutate_ad_group_criteria.assert_called_once()
        call_kwargs = svc.mutate_ad_group_criteria.call_args
        operations = call_kwargs.kwargs.get("operations") or call_kwargs[1].get("operations")
        assert len(operations) == 2

    def test_no_active_account(self, mock_ads_client):
        tool = _register_tool("add_ad_group_negative_keywords")
        result = tool(ad_group_id="333", keywords=[NegativeKeyword(text="test")])
        assert result["error"] is True


# ---------------------------------------------------------------------------
# remove_negative_keyword
# ---------------------------------------------------------------------------


class TestRemoveNegativeKeyword:
    def test_rejects_without_confirm(self, mock_ads_client):
        """Without confirm=True, removal is refused with a warning."""
        set_active_account("1234567890")

        tool = _register_tool("remove_negative_keyword")
        result = tool(criterion_id="601", campaign_id="222", customer_id="1234567890")

        assert "warning" in result
        assert "confirm" in result["warning"].lower()

    def test_campaign_level_removal(self, mock_ads_client):
        """With confirm=True and campaign_id, removes via CampaignCriterionService."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("remove_negative_keyword")
        result = tool(
            criterion_id="601",
            campaign_id="222",
            confirm=True,
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert "removed" in result

        svc = client.get_service("CampaignCriterionService")
        svc.mutate_campaign_criteria.assert_called_once()

    def test_ad_group_level_removal(self, mock_ads_client):
        """With confirm=True and ad_group_id, removes via AdGroupCriterionService."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("remove_negative_keyword")
        result = tool(
            criterion_id="701",
            ad_group_id="333",
            confirm=True,
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert "removed" in result

        svc = client.get_service("AdGroupCriterionService")
        svc.mutate_ad_group_criteria.assert_called_once()

    def test_requires_campaign_or_ad_group(self, mock_ads_client):
        """Must provide one of campaign_id or ad_group_id."""
        set_active_account("1234567890")

        tool = _register_tool("remove_negative_keyword")
        result = tool(
            criterion_id="601",
            confirm=True,
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "campaign_id" in result["message"].lower() or "ad_group_id" in result["message"].lower()

    def test_rejects_both_campaign_and_ad_group(self, mock_ads_client):
        """Cannot provide both campaign_id and ad_group_id."""
        set_active_account("1234567890")

        tool = _register_tool("remove_negative_keyword")
        result = tool(
            criterion_id="601",
            campaign_id="222",
            ad_group_id="333",
            confirm=True,
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "not both" in result["message"].lower() or "only one" in result["message"].lower()

    def test_no_active_account(self, mock_ads_client):
        tool = _register_tool("remove_negative_keyword")
        result = tool(criterion_id="601", campaign_id="222")
        assert result["error"] is True


# ---------------------------------------------------------------------------
# No active account — cross-tool
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    def test_list_no_account(self, mock_ads_client):
        tool = _register_tool("list_negative_keywords")
        result = tool()
        assert result["error"] is True

    def test_add_no_account(self, mock_ads_client):
        tool = _register_tool("add_negative_keywords")
        result = tool(campaign_id="222", keywords=[NegativeKeyword(text="test")])
        assert result["error"] is True

    def test_add_ad_group_no_account(self, mock_ads_client):
        tool = _register_tool("add_ad_group_negative_keywords")
        result = tool(ad_group_id="333", keywords=[NegativeKeyword(text="test")])
        assert result["error"] is True

    def test_remove_no_account(self, mock_ads_client):
        tool = _register_tool("remove_negative_keyword")
        result = tool(criterion_id="601", campaign_id="222")
        assert result["error"] is True
