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
    def test_returns_expected_structure(self, mock_ads_client):
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

        tool = _register_tool("quick_audit")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        summary = result["summary"]
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

        assert "files" in result
        for key in ("campaigns", "keywords", "low_quality_keywords", "ads", "conversion_actions", "budgets"):
            assert key in result["files"]

        assert "top_campaigns" in result
        assert "top_keywords" in result
        assert "top_ads" in result

    def test_campaigns_without_tracking(self, mock_ads_client):
        set_active_account("1234567890")
        tracked = _campaign_row(cid="1", name="Tracked Campaign", status="ENABLED")
        tracked["campaign"]["tracking_url_template"] = "{lpurl}?src=google"
        tracked["campaign"]["final_url_suffix"] = "utm_source=google"
        untracked = _campaign_row(cid="2", name="Untracked Campaign", status="ENABLED")
        # No tracking_url_template on untracked campaign
        paused_no_tracking = _campaign_row(cid="3", name="Paused No Track", status="PAUSED")
        # Paused campaigns should NOT appear in campaigns_without_tracking

        mock_ads_client["set_gaql"](
            {
                "campaign.advertising_channel_type": [tracked, untracked, paused_no_tracking],
                "FROM keyword_view": [],
                "FROM ad_group_ad": [],
                "FROM campaign_criterion": [],
                "FROM conversion_action": [],
                "FROM campaign_budget": [],
            }
        )

        tool = _register_tool("quick_audit")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        without_tracking = result["summary"]["campaigns_without_tracking"]
        assert "Untracked Campaign" in without_tracking
        assert "Tracked Campaign" not in without_tracking
        # Paused campaign should not be in the list (only ENABLED checked)
        assert "Paused No Track" not in without_tracking

    def test_handles_empty_results(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("quick_audit")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        summary = result["summary"]
        assert summary["total_campaigns"] == 0
        assert summary["total_keywords"] == 0
        assert summary["total_ads"] == 0
        assert summary["total_spend_dollars"] == 0
        assert summary["total_conversions"] == 0
        assert summary["avg_cpa_dollars"] is None
        assert summary["avg_quality_score"] is None


# ---------------------------------------------------------------------------
# cleanup_wasted_spend
# ---------------------------------------------------------------------------


class TestCleanupWastedSpend:
    def test_identifies_zero_conversion_keywords(self, mock_ads_client):
        set_active_account("1234567890")
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

        tool = _register_tool("cleanup_wasted_spend")
        result = tool(customer_id="1234567890", min_spend=10.0)

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["wasted_keyword_count"] == 1
        assert result["total_wasted_dollars"] == 15.0
        neg_kws = [n["keyword"] for n in result["suggested_negatives"]]
        assert "free shoe tutorial" in neg_kws
        assert "buy shoes" not in neg_kws

    def test_returns_empty_when_all_keywords_convert(self, mock_ads_client):
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

        tool = _register_tool("cleanup_wasted_spend")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["wasted_keyword_count"] == 0
        assert result["total_wasted_dollars"] == 0
        assert result["suggested_negative_count"] == 0


# ---------------------------------------------------------------------------
# launch_campaign
# ---------------------------------------------------------------------------


class TestLaunchCampaign:
    def test_creates_full_campaign_structure(self, mock_ads_client):
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
        assert result["budget"]["id"] == "111"
        assert result["budget"]["daily_dollars"] == 50.0
        assert result["campaign"]["id"] == "222"
        assert result["campaign"]["name"] == "Test Campaign"
        assert result["ad_group"]["id"] == "333"
        assert result["keywords"]["added"] == 2
        assert result["ad"]["headlines_count"] == 3
        assert result["ad"]["descriptions_count"] == 2
        assert result["ad"]["final_url"] == "https://example.com"

        # Verify all 5 mutate calls
        client.get_service("CampaignBudgetService").mutate_campaign_budgets.assert_called_once()
        client.get_service("CampaignService").mutate_campaigns.assert_called_once()
        client.get_service("AdGroupService").mutate_ad_groups.assert_called_once()
        client.get_service("AdGroupCriterionService").mutate_ad_group_criteria.assert_called_once()
        client.get_service("AdGroupAdService").mutate_ad_group_ads.assert_called_once()

    def test_validates_headline_count(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Bad",
            daily_budget_dollars=10.0,
            keywords=["test"],
            headlines=["H1", "H2"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )
        assert result["error"] is True
        assert "headlines" in result["message"]

    def test_validates_description_count(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Bad",
            daily_budget_dollars=10.0,
            keywords=["test"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1"],
            final_url="https://example.com",
            customer_id="1234567890",
        )
        assert result["error"] is True
        assert "descriptions" in result["message"]

    def test_validates_empty_keywords(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Bad",
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
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        # Use a realistic gRPC error (not RuntimeError, which would be a programming bug)
        import grpc

        rpc_error = grpc.RpcError()
        rpc_error.code = lambda: grpc.StatusCode.RESOURCE_EXHAUSTED
        rpc_error.details = lambda: "API quota exceeded"
        client.get_service("AdGroupService").mutate_ad_groups.side_effect = rpc_error

        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Fail",
            daily_budget_dollars=20.0,
            keywords=["test"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert result["partial_failure"] is True
        created = result["created_before_failure"]
        assert created["budget"] == "customers/1234567890/campaignBudgets/111"
        assert created["campaign"] == "customers/1234567890/campaigns/222"
        assert "ad_group" not in created

    def test_partial_failure_negative_keywords(self, mock_ads_client):
        """When negative keyword creation fails, partial failure includes budget and campaign but not negative_keywords."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]
        import grpc

        rpc_error = grpc.RpcError()
        rpc_error.code = lambda: grpc.StatusCode.INVALID_ARGUMENT
        rpc_error.details = lambda: "Invalid negative keyword criteria"
        client.get_service("CampaignCriterionService").mutate_campaign_criteria.side_effect = rpc_error

        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Fail Negatives",
            daily_budget_dollars=20.0,
            keywords=["test"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            negative_keywords=["free", "cheap"],
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert result["partial_failure"] is True
        created = result["created_before_failure"]
        assert created["budget"] == "customers/1234567890/campaignBudgets/111"
        assert created["campaign"] == "customers/1234567890/campaigns/222"
        assert "negative_keywords" not in created


# ---------------------------------------------------------------------------
# launch_campaign — bidding strategies, negative keywords, locations
# ---------------------------------------------------------------------------


class TestLaunchBiddingStrategies:
    def _get_campaign_op(self, mock_ads_client):
        """Extract the CampaignOperation from the mock CampaignService call_args."""
        svc = mock_ads_client["client"].get_service("CampaignService")
        call_args = svc.mutate_campaigns.call_args
        operations = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if operations and not isinstance(operations, list):
            operations = [operations]
        return operations[0]

    def test_launch_default_manual_cpc(self, mock_ads_client):
        """Default bidding strategy is MANUAL_CPC — existing behavior preserved."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Default Strategy",
            daily_budget_dollars=50.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["status"] == "PAUSED"
        assert result["campaign"]["bidding_strategy"] == "MANUAL_CPC"
        # Verify proto: manual_cpc was set
        op = self._get_campaign_op(mock_ads_client)
        assert hasattr(op.create, "manual_cpc")

    def test_launch_with_maximize_conversions(self, mock_ads_client):
        """MAXIMIZE_CONVERSIONS strategy is accepted and applied to proto."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Max Conv Campaign",
            daily_budget_dollars=100.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["campaign"]["bidding_strategy"] == "MAXIMIZE_CONVERSIONS"
        # Verify proto: maximize_conversions was set
        op = self._get_campaign_op(mock_ads_client)
        assert hasattr(op.create, "maximize_conversions")

    def test_launch_with_target_cpa(self, mock_ads_client):
        """TARGET_CPA with target_cpa_dollars flows through to proto."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Target CPA Campaign",
            daily_budget_dollars=75.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            bidding_strategy="TARGET_CPA",
            target_cpa_dollars=15.0,
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["campaign"]["bidding_strategy"] == "TARGET_CPA"
        # Verify proto: target_cpa.target_cpa_micros was set
        op = self._get_campaign_op(mock_ads_client)
        assert op.create.target_cpa.target_cpa_micros == 15_000_000

    def test_launch_with_invalid_strategy(self, mock_ads_client):
        """Invalid bidding strategy returns a validation error."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Bad Strategy",
            daily_budget_dollars=50.0,
            keywords=["test"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            bidding_strategy="INVALID_STRATEGY",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "Invalid bidding_strategy" in result["message"]

    def test_launch_case_insensitive_strategy(self, mock_ads_client):
        """Lowercase bidding strategy is accepted (upper-cased internally)."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Lowercase Strategy",
            daily_budget_dollars=50.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            bidding_strategy="maximize_conversions",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["campaign"]["bidding_strategy"] == "MAXIMIZE_CONVERSIONS"


class TestLaunchNegativeKeywords:
    def test_launch_with_negative_keywords(self, mock_ads_client):
        """Negative keywords are added as PHRASE match campaign-level negatives."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="With Negatives",
            daily_budget_dollars=50.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            negative_keywords=["free", "cheap"],
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert "negative_keywords" in result
        assert result["negative_keywords"]["match_type"] == "PHRASE"

        # Verify proto: 2 operations with negative=True and PHRASE match
        svc = client.get_service("CampaignCriterionService")
        call_args = svc.mutate_campaign_criteria.call_args
        ops = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if ops and not isinstance(ops, list):
            ops = [ops]
        assert len(ops) == 2
        for op in ops:
            assert op.create.negative is True
            assert op.create.keyword.match_type == "PHRASE"
        texts = {op.create.keyword.text for op in ops}
        assert texts == {"free", "cheap"}

    def test_launch_without_negative_keywords(self, mock_ads_client):
        """When no negative keywords are provided, response omits the section."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="No Negatives",
            daily_budget_dollars=50.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert "negative_keywords" not in result


class TestLaunchLocationTargeting:
    def test_launch_with_location_ids(self, mock_ads_client):
        """Location IDs are added as campaign criteria with correct geo_target_constant."""
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="With Locations",
            daily_budget_dollars=50.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            location_ids=["2840"],
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert "locations" in result
        assert result["locations"]["location_ids"] == ["2840"]

        # Verify proto: geo_target_constant set correctly
        svc = client.get_service("CampaignCriterionService")
        call_args = svc.mutate_campaign_criteria.call_args
        ops = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
        if ops and not isinstance(ops, list):
            ops = [ops]
        assert len(ops) == 1
        assert ops[0].create.location.geo_target_constant == "geoTargetConstants/2840"

    def test_launch_without_location_ids(self, mock_ads_client):
        """When no location IDs are provided, response omits the section."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="No Locations",
            daily_budget_dollars=50.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert "locations" not in result


class TestLaunchCombinedOptions:
    def test_launch_with_negatives_and_locations(self, mock_ads_client):
        """Both negative keywords and location IDs can be set in the same launch."""
        set_active_account("1234567890")
        tool = _register_tool("launch_campaign")
        result = tool(
            campaign_name="Full Setup",
            daily_budget_dollars=50.0,
            keywords=["buy shoes"],
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            negative_keywords=["free"],
            location_ids=["2840", "2826"],
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["campaign"]["bidding_strategy"] == "MAXIMIZE_CONVERSIONS"
        assert "negative_keywords" in result
        assert "locations" in result
        assert result["locations"]["location_ids"] == ["2840", "2826"]

        # CampaignCriterionService should have been called twice (negatives + locations)
        svc = mock_ads_client["client"].get_service("CampaignCriterionService")
        assert svc.mutate_campaign_criteria.call_count == 2


# ---------------------------------------------------------------------------
# Missing account / validation tests
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    def test_quick_audit_no_account(self, mock_ads_client):
        tool = _register_tool("quick_audit")
        result = tool()
        assert result["error"] is True

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
