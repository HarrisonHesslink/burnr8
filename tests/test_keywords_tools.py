"""Tests for burnr8.tools.keywords — list, add, remove, update keywords."""

from burnr8.session import set_active_account

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_tool(name):
    """Register keyword tools and return the one matching *name*."""
    from burnr8.tools.keywords import register

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    register(cap)
    return captured["func"]


def _keyword_row(
    criterion_id="444",
    text="running shoes",
    match_type="BROAD",
    status="ENABLED",
    cpc_bid_micros=1_500_000,
    quality_score=7,
    creative_quality_score="ABOVE_AVERAGE",
    post_click_quality_score="AVERAGE",
    search_predicted_ctr="BELOW_AVERAGE",
    first_page_cpc_micros=500_000,
    top_of_page_cpc_micros=1_200_000,
    ad_group_id="333",
    ad_group_name="Ad Group A",
    campaign_id="222",
    campaign_name="Campaign A",
    impressions=100,
    clicks=10,
    cost_micros=5_000_000,
    conversions=2.0,
):
    return {
        "ad_group_criterion": {
            "criterion_id": criterion_id,
            "keyword": {"text": text, "match_type": match_type},
            "status": status,
            "cpc_bid_micros": cpc_bid_micros,
            "quality_info": {
                "quality_score": quality_score,
                "creative_quality_score": creative_quality_score,
                "post_click_quality_score": post_click_quality_score,
                "search_predicted_ctr": search_predicted_ctr,
            },
            "position_estimates": {
                "first_page_cpc_micros": first_page_cpc_micros,
                "top_of_page_cpc_micros": top_of_page_cpc_micros,
            },
        },
        "ad_group": {"id": ad_group_id, "name": ad_group_name},
        "campaign": {"id": campaign_id, "name": campaign_name},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "conversions": conversions,
        },
    }


# ---------------------------------------------------------------------------
# list_keywords
# ---------------------------------------------------------------------------


class TestListKeywords:
    def test_returns_keywords(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM keyword_view": [_keyword_row()]})
        fn = _register_tool("list_keywords")
        result = fn()
        top = result["top"]
        assert len(top) == 1
        assert top[0]["criterion_id"] == "444"
        assert top[0]["text"] == "running shoes"

    def test_quality_score_components(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM keyword_view": [_keyword_row()]})
        fn = _register_tool("list_keywords")
        result = fn()
        row = result["top"][0]
        assert row["creative_quality"] == "ABOVE_AVERAGE"
        assert row["landing_page_quality"] == "AVERAGE"
        assert row["expected_ctr"] == "BELOW_AVERAGE"

    def test_position_estimates(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM keyword_view": [
            _keyword_row(first_page_cpc_micros=500_000, top_of_page_cpc_micros=1_200_000)
        ]})
        fn = _register_tool("list_keywords")
        result = fn()
        row = result["top"][0]
        assert row["first_page_cpc_dollars"] == 0.50
        assert row["top_of_page_cpc_dollars"] == 1.20

    def test_converts_micros_to_dollars(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM keyword_view": [
            _keyword_row(cpc_bid_micros=2_500_000, cost_micros=10_000_000)
        ]})
        fn = _register_tool("list_keywords")
        result = fn()
        row = result["top"][0]
        assert row["cpc_bid_dollars"] == 2.50
        assert row["cost_dollars"] == 10.00

    def test_no_customer_id(self):
        fn = _register_tool("list_keywords")
        result = fn()
        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_empty_results(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})
        fn = _register_tool("list_keywords")
        result = fn()
        assert result["rows"] == 0

    def test_summary_includes_avg_quality(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM keyword_view": [
            _keyword_row(quality_score=8),
            _keyword_row(criterion_id="445", quality_score=6),
        ]})
        fn = _register_tool("list_keywords")
        result = fn()
        assert result["summary"]["keyword_count"] == 2
        assert result["summary"]["avg_quality_score"] == 7.0

    def test_position_estimates_default_zero(self, mock_ads_client):
        """When position_estimates is missing, defaults to 0."""
        set_active_account("1234567890")
        row = _keyword_row()
        del row["ad_group_criterion"]["position_estimates"]
        mock_ads_client["set_gaql"]({"FROM keyword_view": [row]})
        fn = _register_tool("list_keywords")
        result = fn()
        r = result["top"][0]
        assert r["first_page_cpc_dollars"] == 0.0
        assert r["top_of_page_cpc_dollars"] == 0.0


# ---------------------------------------------------------------------------
# update_keyword
# ---------------------------------------------------------------------------


def _get_criterion_operation(mock_ads_client):
    """Extract the AdGroupCriterionOperation from the mock mutate call_args."""
    svc = mock_ads_client["client"].get_service("AdGroupCriterionService")
    call_args = svc.mutate_ad_group_criteria.call_args
    operations = call_args.kwargs.get("operations", call_args[0][1] if len(call_args[0]) > 1 else None)
    if operations and not isinstance(operations, list):
        operations = [operations]
    return operations[0]


class TestUpdateKeyword:
    def test_update_cpc_bid(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(criterion_id="444", ad_group_id="333", cpc_bid=3.00)
        assert "cpc_bid_micros" in result["updated_fields"]
        assert "resource_name" in result
        # Verify proto assignment
        op = _get_criterion_operation(mock_ads_client)
        assert op.update.cpc_bid_micros == 3_000_000
        assert "cpc_bid_micros" in op.update_mask.paths

    def test_update_final_url_suffix(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(
            criterion_id="444",
            ad_group_id="333",
            final_url_suffix="utm_source=google",
        )
        assert "final_url_suffix" in result["updated_fields"]
        # Verify proto assignment
        op = _get_criterion_operation(mock_ads_client)
        assert op.update.final_url_suffix == "utm_source=google"
        assert "final_url_suffix" in op.update_mask.paths

    def test_update_multiple_fields(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(
            criterion_id="444",
            ad_group_id="333",
            cpc_bid=5.00,
            final_url_suffix="src=ads",
        )
        assert set(result["updated_fields"]) == {"cpc_bid_micros", "final_url_suffix"}
        # Verify both proto fields
        op = _get_criterion_operation(mock_ads_client)
        assert op.update.cpc_bid_micros == 5_000_000
        assert op.update.final_url_suffix == "src=ads"
        assert set(op.update_mask.paths) == {"cpc_bid_micros", "final_url_suffix"}

    def test_no_fields_returns_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(criterion_id="444", ad_group_id="333")
        assert result["error"] is True
        assert "No fields" in result["message"]

    def test_uses_field_mask(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        fn(criterion_id="444", ad_group_id="333", cpc_bid=2.00)
        op = _get_criterion_operation(mock_ads_client)
        assert op.update_mask.paths == ["cpc_bid_micros"]

    def test_no_customer_id(self):
        fn = _register_tool("update_keyword")
        result = fn(criterion_id="444", ad_group_id="333", cpc_bid=2.00)
        assert result["error"] is True

    def test_invalid_ad_group_id(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(criterion_id="444", ad_group_id="bad-id", cpc_bid=2.00)
        assert result["error"] is True

    def test_invalid_criterion_id(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(criterion_id="bad-id", ad_group_id="333", cpc_bid=2.00)
        assert result["error"] is True

    def test_update_cpc_bid_zero(self, mock_ads_client):
        """cpc_bid=0.0 is valid — must not be skipped by falsy check."""
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(criterion_id="444", ad_group_id="333", cpc_bid=0.0)
        assert "cpc_bid_micros" in result["updated_fields"]
        op = _get_criterion_operation(mock_ads_client)
        assert op.update.cpc_bid_micros == 0

    def test_clear_final_url_suffix(self, mock_ads_client):
        """Empty string clears the field (per CLAUDE.md convention)."""
        set_active_account("1234567890")
        fn = _register_tool("update_keyword")
        result = fn(criterion_id="444", ad_group_id="333", final_url_suffix="")
        assert "final_url_suffix" in result["updated_fields"]
        op = _get_criterion_operation(mock_ads_client)
        assert op.update.final_url_suffix == ""
        assert "final_url_suffix" in op.update_mask.paths


# ---------------------------------------------------------------------------
# Conflict detection in list_negative_keywords
# ---------------------------------------------------------------------------


def _register_neg_tool(name):
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


class TestConflictDetection:
    def test_conflicts_detected_when_positive_matches_negative(self, mock_ads_client):
        """When a positive keyword text matches a negative keyword text, a conflict is reported."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_criterion": [
                    _campaign_neg_row(criterion_id="601", text="running shoes", match_type="EXACT"),
                ],
                "FROM keyword_view": [
                    _keyword_row(text="running shoes", match_type="BROAD", campaign_id="222"),
                ],
            }
        )

        tool = _register_neg_tool("list_negative_keywords")
        result = tool(customer_id="1234567890")

        assert "conflicts" in result, f"Expected conflicts key in result: {result}"
        assert len(result["conflicts"]) == 1
        conflict = result["conflicts"][0]
        assert conflict["positive_keyword"] == "running shoes"
        assert conflict["negative_keyword"] == "running shoes"
        assert conflict["negative_level"] == "CAMPAIGN"
        assert result["summary"]["conflict_count"] == 1

    def test_conflict_case_insensitive(self, mock_ads_client):
        """Conflict detection is case-insensitive — 'Running Shoes' matches 'running shoes'."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_criterion": [
                    _campaign_neg_row(criterion_id="601", text="Running Shoes", match_type="EXACT"),
                ],
                "FROM keyword_view": [
                    _keyword_row(text="running shoes", match_type="BROAD", campaign_id="222"),
                ],
            }
        )

        tool = _register_neg_tool("list_negative_keywords")
        result = tool(customer_id="1234567890")

        assert "conflicts" in result
        assert len(result["conflicts"]) == 1

    def test_no_conflicts_when_no_overlap(self, mock_ads_client):
        """When positive and negative keywords don't share text, no conflicts are reported."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign_criterion": [
                    _campaign_neg_row(criterion_id="601", text="free stuff", match_type="BROAD"),
                ],
                "FROM keyword_view": [
                    _keyword_row(text="running shoes", match_type="BROAD", campaign_id="222"),
                ],
            }
        )

        tool = _register_neg_tool("list_negative_keywords")
        result = tool(customer_id="1234567890")

        assert "conflicts" not in result, f"Unexpected conflicts: {result.get('conflicts')}"
        assert "conflict_count" not in result.get("summary", {})
