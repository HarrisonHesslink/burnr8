"""Tests for burnr8.tools.reporting — reporting tools."""

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
    ctr=0.05,
    average_cpc=500_000,
    cost_micros=25_000_000,
    conversions=5.0,
    conversions_value=100.0,
    cost_per_conversion=5_000_000,
):
    return {
        "campaign": {"id": cid, "name": name, "status": status},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
            "average_cpc": average_cpc,
            "cost_micros": cost_micros,
            "conversions": conversions,
            "conversions_value": conversions_value,
            "cost_per_conversion": cost_per_conversion,
        },
    }


def _keyword_row(
    text="buy shoes",
    match_type="BROAD",
    quality_score=7,
    impressions=500,
    clicks=30,
    ctr=0.06,
    average_cpc=500_000,
    cost_micros=15_000_000,
    conversions=3.0,
):
    return {
        "ad_group_criterion": {
            "criterion_id": "101",
            "keyword": {"text": text, "match_type": match_type},
            "quality_info": {"quality_score": quality_score},
        },
        "ad_group": {"id": "10", "name": "AG1"},
        "campaign": {"id": "1", "name": "Campaign A"},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
            "average_cpc": average_cpc,
            "cost_micros": cost_micros,
            "conversions": conversions,
        },
    }


def _search_term_row(
    search_term="buy shoes online",
    status="NONE",
    cost_micros=10_000_000,
    conversions=2.0,
    impressions=200,
    clicks=20,
):
    return {
        "search_term_view": {"search_term": search_term, "status": status},
        "campaign": {"id": "1", "name": "Campaign A"},
        "ad_group": {"id": "10", "name": "AG1"},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "conversions": conversions,
        },
    }


def _register_tool(name):
    """Register reporting tools and return the one matching *name*."""
    from burnr8.tools.reporting import register

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
# get_campaign_performance
# ---------------------------------------------------------------------------


class TestGetCampaignPerformance:
    def test_returns_summary_with_metrics(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign": [
                    _campaign_row(cid="1", cost_micros=25_000_000, conversions=5.0),
                    _campaign_row(
                        cid="2",
                        name="Campaign B",
                        cost_micros=15_000_000,
                        conversions=3.0,
                    ),
                ],
            }
        )

        tool = _register_tool("get_campaign_performance")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        summary = result["summary"]
        assert summary["total_spend"] == 40.0
        assert summary["total_conversions"] == 8.0
        assert summary["avg_cpa"] == 5.0
        assert summary["date_range"] == "LAST_30_DAYS"

    def test_cpa_is_none_when_zero_conversions(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM campaign": [
                    _campaign_row(cost_micros=10_000_000, conversions=0.0),
                ],
            }
        )

        tool = _register_tool("get_campaign_performance")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        summary = result["summary"]
        assert summary["total_conversions"] == 0.0
        assert summary["avg_cpa"] is None


# ---------------------------------------------------------------------------
# get_keyword_performance
# ---------------------------------------------------------------------------


class TestGetKeywordPerformance:
    def test_returns_summary_with_quality_scores(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM keyword_view": [
                    _keyword_row(text="buy shoes", quality_score=8),
                    _keyword_row(text="cheap shoes", quality_score=4),
                    _keyword_row(text="running shoes", quality_score=6),
                ],
            }
        )

        tool = _register_tool("get_keyword_performance")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        summary = result["summary"]
        assert summary["avg_quality_score"] == 6.0
        assert summary["low_qs_count"] == 1  # quality_score=4 < 5
        assert summary["keywords_with_qs"] == 3


# ---------------------------------------------------------------------------
# get_search_terms_report
# ---------------------------------------------------------------------------


class TestGetSearchTermsReport:
    def test_returns_summary_with_wasted_pct(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM search_term_view": [
                    _search_term_row(
                        search_term="buy shoes online",
                        cost_micros=20_000_000,
                        conversions=3.0,
                    ),
                    _search_term_row(
                        search_term="free shoe pics",
                        cost_micros=10_000_000,
                        conversions=0.0,
                    ),
                    _search_term_row(
                        search_term="shoe memes",
                        cost_micros=5_000_000,
                        conversions=0.0,
                    ),
                ],
            }
        )

        tool = _register_tool("get_search_terms_report")
        result = tool(customer_id="1234567890")

        assert "error" not in result, f"Unexpected error: {result}"
        summary = result["summary"]
        # total_spend = 20 + 10 + 5 = 35
        # zero_conv_spend = 10 + 5 = 15
        # wasted_pct = 15 / 35 * 100 = 42.9
        assert summary["total_spend"] == 35.0
        assert summary["zero_conversion_spend"] == 15.0
        assert summary["wasted_pct"] == 42.9
        assert summary["unique_terms"] == 3


# ---------------------------------------------------------------------------
# run_gaql_query
# ---------------------------------------------------------------------------


class TestRunGaqlQuery:
    def test_passes_query_through(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "SELECT campaign.id": [
                    {"campaign": {"id": "1"}},
                    {"campaign": {"id": "2"}},
                ],
            }
        )

        tool = _register_tool("run_gaql_query")
        result = tool(
            query="SELECT campaign.id FROM campaign",
            customer_id="1234567890",
        )

        assert "error" not in result, f"Unexpected error: {result}"
        assert result["file"].endswith(".csv")
        assert result["rows"] == 2


# ---------------------------------------------------------------------------
# Validation — invalid date range
# ---------------------------------------------------------------------------


class TestDateRangeValidation:
    def test_campaign_performance_invalid_date_range(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("get_campaign_performance")
        result = tool(customer_id="1234567890", date_range="LAST_999_DAYS")
        assert result["error"] is True

    def test_keyword_performance_invalid_date_range(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("get_keyword_performance")
        result = tool(customer_id="1234567890", date_range="INVALID")
        assert result["error"] is True

    def test_search_terms_invalid_date_range(self, mock_ads_client):
        set_active_account("1234567890")
        tool = _register_tool("get_search_terms_report")
        result = tool(customer_id="1234567890", date_range="NOPE")
        assert result["error"] is True


# ---------------------------------------------------------------------------
# Validation — no active account
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    def test_campaign_performance_no_account(self, mock_ads_client):
        tool = _register_tool("get_campaign_performance")
        result = tool()
        assert result["error"] is True

    def test_keyword_performance_no_account(self, mock_ads_client):
        tool = _register_tool("get_keyword_performance")
        result = tool()
        assert result["error"] is True

    def test_search_terms_no_account(self, mock_ads_client):
        tool = _register_tool("get_search_terms_report")
        result = tool()
        assert result["error"] is True

    def test_run_gaql_query_no_account(self, mock_ads_client):
        tool = _register_tool("run_gaql_query")
        result = tool(query="SELECT campaign.id FROM campaign")
        assert result["error"] is True
