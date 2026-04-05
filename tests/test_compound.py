"""Tests for burnr8.tools.compound — quick_audit, cleanup_wasted_spend, launch_campaign."""

from burnr8.session import set_active_account

# ---------------------------------------------------------------------------
# Helpers — sample GAQL result rows
# ---------------------------------------------------------------------------


def _campaign_row(
    cid="1",
    name="Campaign A",
    status="ENABLED",
    impressions=1000,
    clicks=50,
    cost_micros=25_000_000,
    conversions=5.0,
    conversions_value=100.0,
    ctr=0.05,
    average_cpc=500_000,
):
    return {
        "campaign": {
            "id": cid,
            "name": name,
            "status": status,
            "advertising_channel_type": "SEARCH",
            "bidding_strategy_type": "MANUAL_CPC",
        },
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "conversions": conversions,
            "conversions_value": conversions_value,
            "ctr": ctr,
            "average_cpc": average_cpc,
        },
    }


def _keyword_row(
    text="buy shoes",
    match_type="BROAD",
    quality_score=7,
    impressions=500,
    clicks=30,
    cost_micros=15_000_000,
    conversions=3.0,
    status="ENABLED",
    ad_group="AG1",
    campaign="Campaign A",
    criterion_id="101",
):
    return {
        "ad_group_criterion": {
            "criterion_id": criterion_id,
            "keyword": {"text": text, "match_type": match_type},
            "status": status,
            "quality_info": {"quality_score": quality_score},
        },
        "ad_group": {"id": "10", "name": ad_group},
        "campaign": {"id": "1", "name": campaign},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "conversions": conversions,
        },
    }


def _ad_row(
    ad_id="201",
    ad_type="RESPONSIVE_SEARCH_AD",
    headlines=None,
    descriptions=None,
    ad_strength="GOOD",
    impressions=400,
    clicks=20,
    cost_micros=10_000_000,
    conversions=2.0,
):
    return {
        "ad_group_ad": {
            "ad": {
                "id": ad_id,
                "type": ad_type,
                "final_urls": ["https://example.com"],
                "responsive_search_ad": {
                    "headlines": [{"text": h} for h in (headlines or ["H1", "H2", "H3"])],
                    "descriptions": [{"text": d} for d in (descriptions or ["D1", "D2"])],
                },
            },
            "ad_strength": ad_strength,
            "status": "ENABLED",
            "policy_summary": {"approval_status": "APPROVED"},
        },
        "ad_group": {"name": "AG1"},
        "campaign": {"name": "Campaign A"},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "conversions": conversions,
        },
    }


def _negative_row(criterion_id="301"):
    return {"campaign_criterion": {"criterion_id": criterion_id}}


def _conversion_row(
    ca_id="401",
    name="Purchase",
    status="ENABLED",
    ca_type="WEBPAGE",
    category="PURCHASE",
    counting_type="ONE_PER_CLICK",
):
    return {
        "conversion_action": {
            "id": ca_id,
            "name": name,
            "status": status,
            "type": ca_type,
            "category": category,
            "counting_type": counting_type,
        },
    }


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
    """Register compound tools and return the one matching *name*."""
    from burnr8.tools.compound import register

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
# quick_audit
# ---------------------------------------------------------------------------


class TestQuickAudit:
    """Tests for the quick_audit compound tool."""

    def test_returns_expected_structure(self, mock_ads_client, tmp_path):
        """quick_audit should return summary, files, and top_* keys."""
        set_active_account("1234567890")

        mock_ads_client["set_gaql"](
            {
                "campaign.advertising_channel_type": [_campaign_row()],
                "FROM keyword_view": [_keyword_row()],
                "FROM ad_group_ad": [_ad_row()],
                "FROM campaign_criterion": [_negative_row()],
                "FROM conversion_action": [_conversion_row()],
                "FROM campaign_budget": [_budget_row()],
            }
        )

        import burnr8.reports as reports_mod

        original_dir = reports_mod.REPORTS_DIR
        reports_mod.REPORTS_DIR = tmp_path
        try:
            tool = _register_tool("quick_audit")
            result = tool(customer_id="1234567890")
        finally:
            reports_mod.REPORTS_DIR = original_dir

        assert "error" not in result, f"Unexpected error: {result}"
        assert "summary" in result
        summary = result["summary"]

        # Verify summary fields
        assert summary["total_campaigns"] == 1
        assert summary["total_keywords"] == 1
        assert summary["total_ads"] == 1
        assert summary["negative_keyword_count"] == 1
        assert summary["conversion_action_count"] == 1
        assert summary["budget_count"] == 1
        assert summary["total_spend_dollars"] == 25.0
        assert summary["total_conversions"] == 5.0
        assert summary["avg_cpa_dollars"] == 5.0
        assert summary["avg_quality_score"] == 7.0
        assert summary["date_range"] == "LAST_30_DAYS"

        # Verify files dict
        assert "files" in result
        files = result["files"]
        for key in ("campaigns", "keywords", "low_quality_keywords", "ads", "conversion_actions", "budgets"):
            assert key in files

        # Verify top_ keys
        assert "top_campaigns" in result
        assert "top_keywords" in result
        assert "top_ads" in result

    def test_handles_empty_results(self, mock_ads_client, tmp_path):
        """quick_audit should return zeros/empty lists when no data exists."""
        set_active_account("1234567890")

        # All queries return empty lists (no matching substrings)
        mock_ads_client["set_gaql"]({})

        import burnr8.reports as reports_mod

        original_dir = reports_mod.REPORTS_DIR
        reports_mod.REPORTS_DIR = tmp_path
        try:
            tool = _register_tool("quick_audit")
            result = tool(customer_id="1234567890")
        finally:
            reports_mod.REPORTS_DIR = original_dir

        assert "error" not in result, f"Unexpected error: {result}"
        summary = result["summary"]
        assert summary["total_campaigns"] == 0
        assert summary["total_keywords"] == 0
        assert summary["total_ads"] == 0
        assert summary["total_spend_dollars"] == 0
        assert summary["total_conversions"] == 0
        assert summary["negative_keyword_count"] == 0
        assert summary["conversion_action_count"] == 0
        assert summary["budget_count"] == 0
        assert summary["avg_cpa_dollars"] is None
        assert summary["avg_quality_score"] is None


# ---------------------------------------------------------------------------
# cleanup_wasted_spend
# ---------------------------------------------------------------------------


class TestCleanupWastedSpend:
    """Tests for the cleanup_wasted_spend compound tool."""

    def test_identifies_zero_conversion_keywords(self, mock_ads_client, tmp_path):
        """Keywords with spend >= threshold and 0 conversions should be flagged."""
        set_active_account("1234567890")

        # Two keywords: one with conversions, one wasted
        mock_ads_client["set_gaql"](
            {
                "FROM keyword_view": [
                    _keyword_row(text="buy shoes", cost_micros=20_000_000, conversions=3.0, criterion_id="101"),
                    _keyword_row(
                        text="free shoe tutorial", cost_micros=15_000_000, conversions=0.0, criterion_id="102"
                    ),
                ],
            }
        )

        import burnr8.reports as reports_mod

        original_dir = reports_mod.REPORTS_DIR
        reports_mod.REPORTS_DIR = tmp_path
        try:
            tool = _register_tool("cleanup_wasted_spend")
            result = tool(customer_id="1234567890", min_spend=10.0)
        finally:
            reports_mod.REPORTS_DIR = original_dir

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["wasted_keyword_count"] == 1
        assert result["total_wasted_dollars"] == 15.0

        # "free shoe tutorial" matches informational signal "free" and "tutorial"
        assert result["suggested_negative_count"] >= 1
        neg_kws = [n["keyword"] for n in result["suggested_negatives"]]
        assert "free shoe tutorial" in neg_kws
        # Converting keyword should NOT appear in negatives
        assert "buy shoes" not in neg_kws

    def test_returns_empty_when_all_keywords_convert(self, mock_ads_client, tmp_path):
        """No wasted keywords when every keyword has conversions > 0."""
        set_active_account("1234567890")

        mock_ads_client["set_gaql"](
            {
                "FROM keyword_view": [
                    _keyword_row(text="buy shoes", cost_micros=20_000_000, conversions=5.0, criterion_id="101"),
                    _keyword_row(
                        text="running shoes sale", cost_micros=30_000_000, conversions=2.0, criterion_id="102"
                    ),
                ],
            }
        )

        import burnr8.reports as reports_mod

        original_dir = reports_mod.REPORTS_DIR
        reports_mod.REPORTS_DIR = tmp_path
        try:
            tool = _register_tool("cleanup_wasted_spend")
            result = tool(customer_id="1234567890")
        finally:
            reports_mod.REPORTS_DIR = original_dir

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["wasted_keyword_count"] == 0
        assert result["total_wasted_dollars"] == 0
        assert result["suggested_negative_count"] == 0


# ---------------------------------------------------------------------------
# launch_campaign
# ---------------------------------------------------------------------------


class TestLaunchCampaign:
    """Tests for the launch_campaign compound tool."""

    def test_creates_full_campaign_structure(self, mock_ads_client):
        """launch_campaign should return budget, campaign, ad_group, keywords, ad."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Test Campaign",
            daily_budget_dollars=50.0,
            keywords=["buy shoes", "running shoes"],
            headlines=["Best Shoes", "Buy Now", "Free Shipping"],
            descriptions=["Top quality shoes.", "Order today and save."],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["status"] == "PAUSED"

        # Budget
        assert result["budget"]["id"] == "111"
        assert result["budget"]["daily_dollars"] == 50.0

        # Campaign
        assert result["campaign"]["id"] == "222"
        assert result["campaign"]["name"] == "Test Campaign"

        # Ad group
        assert result["ad_group"]["id"] == "333"
        assert result["ad_group"]["name"] == "Ad Group 1"
        assert result["ad_group"]["cpc_bid_dollars"] == 1.0

        # Keywords
        assert result["keywords"]["added"] == 2
        assert result["keywords"]["match_type"] == "BROAD"

        # Ad
        assert result["ad"]["headlines_count"] == 3
        assert result["ad"]["descriptions_count"] == 2
        assert result["ad"]["final_url"] == "https://example.com"

        # Verify mutate calls were made
        budget_svc = client.get_service("CampaignBudgetService")
        budget_svc.mutate_campaign_budgets.assert_called_once()

        campaign_svc = client.get_service("CampaignService")
        campaign_svc.mutate_campaigns.assert_called_once()

        ad_group_svc = client.get_service("AdGroupService")
        ad_group_svc.mutate_ad_groups.assert_called_once()

        criterion_svc = client.get_service("AdGroupCriterionService")
        criterion_svc.mutate_ad_group_criteria.assert_called_once()

        ad_svc = client.get_service("AdGroupAdService")
        ad_svc.mutate_ad_group_ads.assert_called_once()

    def test_validates_headline_count(self, mock_ads_client):
        """launch_campaign should reject fewer than 3 headlines."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")

        result = tool(
            campaign_name="Bad Campaign",
            daily_budget_dollars=10.0,
            keywords=["test"],
            headlines=["H1", "H2"],  # too few
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "headlines" in result["message"]

    def test_validates_description_count(self, mock_ads_client):
        """launch_campaign should reject fewer than 2 descriptions."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")

        result = tool(
            campaign_name="Bad Campaign",
            daily_budget_dollars=10.0,
            keywords=["test"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1"],  # too few
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "descriptions" in result["message"]

    def test_validates_empty_keywords(self, mock_ads_client):
        """launch_campaign should reject an empty keyword list."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")

        result = tool(
            campaign_name="Bad Campaign",
            daily_budget_dollars=10.0,
            keywords=[],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "keywords" in result["message"]

    def test_partial_failure_reports_created_resources(self, mock_ads_client):
        """If a mutate fails mid-way, launch_campaign should report what was created."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        # Make ad group creation fail
        ag_svc = client.get_service("AdGroupService")
        ag_svc.mutate_ad_groups.side_effect = RuntimeError("API quota exceeded")

        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Fail Campaign",
            daily_budget_dollars=20.0,
            keywords=["test"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert result["partial_failure"] is True
        # Budget and campaign should have been created before the failure
        created = result["created_before_failure"]
        assert created["budget"] == "customers/1234567890/campaignBudgets/111"
        assert created["campaign"] == "customers/1234567890/campaigns/222"
        assert "ad_group" not in created


# ---------------------------------------------------------------------------
# Missing account / validation tests
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    """Tools should error when no customer_id and no active account."""

    def test_quick_audit_no_account(self, mock_ads_client):
        tool = _register_tool("quick_audit")
        result = tool()
        assert result["error"] is True
        assert "customer_id" in result["message"].lower() or "active account" in result["message"].lower()

    def test_cleanup_wasted_spend_no_account(self, mock_ads_client):
        tool = _register_tool("cleanup_wasted_spend")
        result = tool()
        assert result["error"] is True

    def test_launch_campaign_no_account(self, mock_ads_client):
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Test",
            daily_budget_dollars=10.0,
            keywords=["test"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
        )
        assert result["error"] is True


class TestDateRangeValidation:
    """Tools should reject invalid date ranges."""

    def test_quick_audit_invalid_date_range(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("quick_audit")
        result = tool(customer_id="1234567890", date_range="LAST_100_DAYS")
        assert result["error"] is True

    def test_cleanup_invalid_date_range(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("cleanup_wasted_spend")
        result = tool(customer_id="1234567890", date_range="INVALID")
        assert result["error"] is True
