# tests/integration/test_reporting.py
"""Integration tests for reporting tools — all read-only, validates GAQL and CSV export."""

import pytest

from tests.integration.conftest import INVALID_CUSTOMER_IDS, register_tool

INVALID_DATE_RANGES = [
    ("empty", ""),
    ("nonsense", "LAST_999_DAYS"),
    ("sql_injection", "LAST_7_DAYS; DROP TABLE"),
    # Note: lowercase like "last_7_days" is accepted — validate_date_range does .upper()
]


def _register(name: str):
    return register_tool(name, "reporting")


# ---------------------------------------------------------------------------
# run_gaql_query
# ---------------------------------------------------------------------------


class TestRunGaqlQuery:
    def test_basic_select(self, test_customer_id):
        tool = _register("run_gaql_query")
        result = tool(
            query="SELECT campaign.id, campaign.name FROM campaign LIMIT 5",
            customer_id=test_customer_id,
        )

        assert isinstance(result, dict)
        assert "error" not in result
        assert "rows" in result or "data" in result or "row_count" in result

    def test_with_limit(self, test_customer_id):
        tool = _register("run_gaql_query")
        result = tool(
            query="SELECT campaign.id FROM campaign",
            limit=2,
            customer_id=test_customer_id,
        )

        assert isinstance(result, dict)
        assert "error" not in result

    def test_rejects_mutating_query(self, test_customer_id):
        tool = _register("run_gaql_query")
        result = tool(
            query="UPDATE campaign SET campaign.name = 'hacked'",
            customer_id=test_customer_id,
        )

        assert result.get("error") is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("run_gaql_query")
        result = tool(
            query="SELECT campaign.id FROM campaign LIMIT 1",
            customer_id=customer_id,
        )

        assert result["error"] is True


# ---------------------------------------------------------------------------
# get_campaign_performance
# ---------------------------------------------------------------------------


class TestCampaignPerformance:
    def test_default_date_range(self, test_customer_id):
        tool = _register("get_campaign_performance")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert "error" not in result
        assert "summary" in result
        assert result["summary"]["date_range"] == "LAST_30_DAYS"
        assert "total_spend" in result["summary"]
        assert "total_conversions" in result["summary"]

    def test_explicit_date_range(self, test_customer_id):
        tool = _register("get_campaign_performance")
        result = tool(date_range="LAST_7_DAYS", customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert "error" not in result
        assert result["summary"]["date_range"] == "LAST_7_DAYS"

    def test_csv_export_fields(self, test_customer_id):
        """Verify the report includes CSV export metadata."""
        tool = _register("get_campaign_performance")
        result = tool(date_range="LAST_7_DAYS", customer_id=test_customer_id)

        assert "error" not in result
        assert "rows" in result
        if result["rows"] > 0:
            assert "file" in result
            assert "columns" in result

    @pytest.mark.parametrize("label,date_range", INVALID_DATE_RANGES)
    def test_invalid_date_range(self, label, date_range, test_customer_id):
        tool = _register("get_campaign_performance")
        result = tool(date_range=date_range, customer_id=test_customer_id)

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("get_campaign_performance")
        result = tool(customer_id=customer_id)

        assert result["error"] is True

    def test_filter_by_campaign_id(self, test_customer_id):
        """Filter to a non-existent campaign should return empty results, not an error."""
        tool = _register("get_campaign_performance")
        result = tool(
            campaign_id="9999999999",
            customer_id=test_customer_id,
        )

        assert "error" not in result
        assert result["rows"] == 0

    def test_invalid_campaign_id_format(self, test_customer_id):
        tool = _register("get_campaign_performance")
        result = tool(
            campaign_id="not-a-number",
            customer_id=test_customer_id,
        )

        assert result["error"] is True


# ---------------------------------------------------------------------------
# get_ad_group_performance
# ---------------------------------------------------------------------------


class TestAdGroupPerformance:
    def test_default(self, test_customer_id):
        tool = _register("get_ad_group_performance")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert "error" not in result
        assert "summary" in result
        assert result["summary"]["date_range"] == "LAST_30_DAYS"
        assert "total_spend" in result["summary"]
        assert "ad_groups_count" in result["summary"]

    def test_filter_by_campaign(self, test_customer_id):
        tool = _register("get_ad_group_performance")
        result = tool(
            campaign_id="9999999999",
            customer_id=test_customer_id,
        )

        assert "error" not in result
        assert result["summary"]["ad_groups_count"] == 0

    @pytest.mark.parametrize("label,date_range", INVALID_DATE_RANGES)
    def test_invalid_date_range(self, label, date_range, test_customer_id):
        tool = _register("get_ad_group_performance")
        result = tool(date_range=date_range, customer_id=test_customer_id)

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("get_ad_group_performance")
        result = tool(customer_id=customer_id)

        assert result["error"] is True


# ---------------------------------------------------------------------------
# get_keyword_performance
# ---------------------------------------------------------------------------


class TestKeywordPerformance:
    def test_default(self, test_customer_id):
        tool = _register("get_keyword_performance")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert "error" not in result
        assert "summary" in result
        assert "avg_quality_score" in result["summary"]
        assert "low_qs_count" in result["summary"]
        assert "keywords_with_qs" in result["summary"]

    @pytest.mark.parametrize("label,date_range", INVALID_DATE_RANGES)
    def test_invalid_date_range(self, label, date_range, test_customer_id):
        tool = _register("get_keyword_performance")
        result = tool(date_range=date_range, customer_id=test_customer_id)

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("get_keyword_performance")
        result = tool(customer_id=customer_id)

        assert result["error"] is True


# ---------------------------------------------------------------------------
# get_search_terms_report
# ---------------------------------------------------------------------------


class TestSearchTermsReport:
    def test_default(self, test_customer_id):
        tool = _register("get_search_terms_report")
        result = tool(customer_id=test_customer_id)

        assert isinstance(result, dict)
        assert "error" not in result
        assert "summary" in result
        summary = result["summary"]
        assert summary["date_range"] == "LAST_30_DAYS"
        assert "unique_terms" in summary
        assert "total_spend" in summary
        assert "zero_conversion_spend" in summary
        assert "wasted_pct" in summary

    def test_seven_day_range(self, test_customer_id):
        tool = _register("get_search_terms_report")
        result = tool(date_range="LAST_7_DAYS", customer_id=test_customer_id)

        assert "error" not in result
        assert result["summary"]["date_range"] == "LAST_7_DAYS"

    @pytest.mark.parametrize("label,date_range", INVALID_DATE_RANGES)
    def test_invalid_date_range(self, label, date_range, test_customer_id):
        tool = _register("get_search_terms_report")
        result = tool(date_range=date_range, customer_id=test_customer_id)

        assert result["error"] is True

    @pytest.mark.parametrize("label,customer_id", INVALID_CUSTOMER_IDS)
    def test_invalid_customer_id(self, label, customer_id):
        tool = _register("get_search_terms_report")
        result = tool(customer_id=customer_id)

        assert result["error"] is True
