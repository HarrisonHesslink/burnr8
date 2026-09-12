"""Behavior tests for the Search Console and SEO MCP tool surface."""

from datetime import date
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest

from burnr8.seo.crawler import PageSignals
from burnr8.tools.seo import SearchConsoleFilter, register


class _Capture:
    def __init__(self):
        self.tools = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


class _FakeGscClient:
    def __init__(self):
        self.calls = []
        self.analytics_payloads = []

    def list_properties(self):
        self.calls.append(("list_properties",))
        return {"siteEntry": [{"siteUrl": "sc-domain:studywithlily.com", "permissionLevel": "siteOwner"}]}

    def get_property(self, property_url):
        self.calls.append(("get_property", property_url))
        return {"siteUrl": property_url, "permissionLevel": "siteOwner"}

    def query_search_analytics(self, property_url, body):
        self.calls.append(("analytics", property_url, body))
        if self.analytics_payloads:
            return self.analytics_payloads.pop(0)
        return {"rows": []}

    def inspect_url(self, property_url, url, language_code):
        self.calls.append(("inspect", property_url, url, language_code))
        return {
            "inspectionResult": {
                "indexStatusResult": {
                    "verdict": "PASS",
                    "coverageState": "Submitted and indexed",
                    "googleCanonical": url,
                }
            }
        }

    def list_sitemaps(self, property_url):
        self.calls.append(("list_sitemaps", property_url))
        return {"sitemap": [{"path": f"https://{property_url.removeprefix('sc-domain:')}/sitemap.xml"}]}

    def submit_sitemap(self, property_url, sitemap_url):
        self.calls.append(("submit_sitemap", property_url, sitemap_url))
        return {}


class _FakePerformanceClient:
    crux_configured = True

    def __init__(self):
        self.calls = []

    def pagespeed(self, url, *, strategy, categories, locale="en_US"):
        self.calls.append(("pagespeed", url, strategy, categories, locale))
        return {
            "id": url,
            "lighthouseResult": {
                "finalUrl": url,
                "lighthouseVersion": "13.0.0",
                "categories": {"performance": {"score": 0.91}, "seo": {"score": 0.84}},
                "audits": {"document-title": {"title": "Document has a title", "score": 1}},
            },
        }

    def crux(self, url, *, form_factor=None, origin=False):
        self.calls.append(("crux", url, form_factor, origin))
        return {
            "record": {"key": {"url": url}, "metrics": {"largest_contentful_paint": {"percentiles": {"p75": 2100}}}}
        }


@pytest.fixture
def tools():
    capture = _Capture()
    register(capture)
    return capture.tools


@pytest.fixture(autouse=True)
def _quiet_logging():
    with patch("burnr8.seo.errors.log_tool_call"):
        yield


def _report(rows, name, top_n=10):
    return {"file": f"/tmp/{name}.csv" if rows else None, "rows": len(rows), "top": rows[:top_n]}


def _gsc_row(keys, clicks, impressions, ctr, position):
    return {"keys": keys, "clicks": clicks, "impressions": impressions, "ctr": ctr, "position": position}


def test_registers_complete_twelve_tool_surface(tools):
    assert set(tools) == {
        "gsc_list_properties",
        "gsc_set_active_property",
        "gsc_search_performance",
        "gsc_compare_periods",
        "gsc_find_opportunities",
        "gsc_inspect_url",
        "gsc_list_sitemaps",
        "gsc_submit_sitemap",
        "pagespeed_analyze",
        "seo_audit_url",
        "seo_crawl_site",
        "search_demand_gap",
    }


def test_lists_and_selects_verified_property(tools):
    client = _FakeGscClient()
    with patch("burnr8.tools.seo.get_search_console_client", return_value=client):
        listed = tools["gsc_list_properties"]()
        selected = tools["gsc_set_active_property"]("sc-domain:StudyWithLily.com")

    assert listed["count"] == 1
    assert selected["active_property"] == "sc-domain:studywithlily.com"
    assert client.calls[-1] == ("get_property", "sc-domain:studywithlily.com")


def test_search_performance_builds_filtered_api_body_and_transforms_rows(tools):
    client = _FakeGscClient()
    client.analytics_payloads = [{"rows": [_gsc_row(["study app", "mobile"], 12, 300, 0.04, 7.2)]}]
    filter_value = SearchConsoleFilter(dimension="query", operator="contains", expression="study")
    with (
        patch("burnr8.tools.seo.get_search_console_client", return_value=client),
        patch("burnr8.tools.seo.save_report", side_effect=_report),
    ):
        result = tools["gsc_search_performance"](
            "2026-06-01",
            "2026-06-30",
            ["query", "device"],
            [filter_value],
            property_url="sc-domain:studywithlily.com",
        )

    body = client.calls[0][2]
    assert body["startDate"] == "2026-06-01"
    assert body["dimensionFilterGroups"][0]["filters"][0]["expression"] == "study"
    assert result["top"][0]["ctr_percent"] == 4.0
    assert result["summary"]["weighted_average_position"] == 7.2


def test_search_performance_coerces_raw_filter_dicts_and_guards_hour_dimension(tools):
    client = _FakeGscClient()
    with (
        patch("burnr8.tools.seo.get_search_console_client", return_value=client),
        patch("burnr8.tools.seo.save_report", side_effect=_report),
    ):
        result = tools["gsc_search_performance"](
            "2026-06-01",
            "2026-06-30",
            ["query"],
            [{"dimension": "query", "operator": "contains", "expression": "study"}],
            property_url="sc-domain:studywithlily.com",
        )
        rejected = tools["gsc_search_performance"](
            "2026-06-01",
            "2026-06-30",
            ["hour"],
            property_url="sc-domain:studywithlily.com",
        )

    assert result["rows"] == 0
    assert client.calls[0][2]["dimensionFilterGroups"][0]["filters"][0]["expression"] == "study"
    assert rejected["error"] is True
    assert "hourly_all" in rejected["message"]


def test_period_comparison_calculates_metric_deltas(tools):
    client = _FakeGscClient()
    client.analytics_payloads = [
        {"rows": [_gsc_row(["study app"], 20, 400, 0.05, 4)]},
        {"rows": [_gsc_row(["study app"], 10, 250, 0.04, 7)]},
    ]
    with (
        patch("burnr8.tools.seo.get_search_console_client", return_value=client),
        patch("burnr8.tools.seo.save_report", side_effect=_report),
    ):
        result = tools["gsc_compare_periods"](
            "2026-06-01",
            "2026-06-28",
            "2026-05-04",
            "2026-05-31",
            property_url="sc-domain:studywithlily.com",
        )

    assert result["top"][0]["delta_clicks"] == 10
    assert result["top"][0]["delta_position"] == -3


def test_opportunities_flags_striking_distance_and_cannibalization(tools):
    client = _FakeGscClient()
    client.analytics_payloads = [
        {"rows": [_gsc_row(["revision app"], 5, 1000, 0.005, 8)]},
        {
            "rows": [
                _gsc_row(["revision app", "https://studywithlily.com/a"], 3, 600, 0.005, 7),
                _gsc_row(["revision app", "https://studywithlily.com/b"], 2, 400, 0.005, 9),
            ]
        },
    ]
    with (
        patch("burnr8.tools.seo.get_search_console_client", return_value=client),
        patch("burnr8.tools.seo.save_report", side_effect=_report),
    ):
        result = tools["gsc_find_opportunities"]("2026-06-01", "2026-06-30", property_url="sc-domain:studywithlily.com")

    kinds = result["top"][0]["opportunity_types"]
    assert "striking_distance" in kinds
    assert "low_ctr" in kinds
    assert "possible_cannibalization" in kinds
    assert "not traffic forecasts" in result["scoring_note"]


def test_url_inspection_enforces_property_ownership(tools):
    client = _FakeGscClient()
    with patch("burnr8.tools.seo.get_search_console_client", return_value=client):
        result = tools["gsc_inspect_url"]("https://studywithlily.com/daily", property_url="sc-domain:studywithlily.com")
        rejected = tools["gsc_inspect_url"]("https://evil.test/daily", property_url="sc-domain:studywithlily.com")

    assert result["summary"]["verdict"] == "PASS"
    assert rejected["error"] is True
    assert not any(call[0] == "inspect" and "evil.test" in call[2] for call in client.calls)


def test_sitemap_dry_run_makes_no_client_call_and_confirmed_submit_does(tools):
    client = _FakeGscClient()
    with patch("burnr8.tools.seo.get_search_console_client", return_value=client) as factory:
        dry_run = tools["gsc_submit_sitemap"](
            "https://studywithlily.com/sitemap.xml", property_url="sc-domain:studywithlily.com"
        )
        factory.assert_not_called()
        submitted = tools["gsc_submit_sitemap"](
            "https://studywithlily.com/sitemap.xml",
            confirm=True,
            property_url="sc-domain:studywithlily.com",
        )

    assert dry_run["warning"] is True
    assert submitted["submitted"] is True
    assert client.calls == [("submit_sitemap", "sc-domain:studywithlily.com", "https://studywithlily.com/sitemap.xml")]


def test_pagespeed_returns_lab_and_crux_without_search_console_credentials(tools):
    client = _FakePerformanceClient()
    with (
        patch("burnr8.tools.seo.validate_public_url", return_value=urlsplit("https://studywithlily.com/daily")),
        patch("burnr8.tools.seo.get_performance_client", return_value=client),
    ):
        result = tools["pagespeed_analyze"]("https://studywithlily.com/daily")

    assert result["lab"]["category_scores"] == {"performance": 91, "seo": 84}
    assert result["field"]["metrics"]["largest_contentful_paint"]["p75"] == 2100
    assert client.calls[1][2] == "PHONE"


def test_single_page_and_site_crawl_tools_label_static_html_limit(tools):
    page = PageSignals(
        url="https://studywithlily.com/",
        final_url="https://studywithlily.com/",
        status_code=200,
        content_type="text/html",
        title="Study With Lily",
        meta_description="Study smarter",
        meta_robots=None,
        canonical="https://studywithlily.com/",
        language="en",
        viewport="width=device-width",
        h1=["Study With Lily"],
        h2_count=0,
        h3_count=0,
        word_count=100,
        internal_links=[],
        external_links_count=0,
        images_count=0,
        images_missing_alt=0,
        static_json_ld_blocks=0,
    )
    crawl_result = {
        "summary": {"pages_processed": 1},
        "scope": {},
        "duplicates": {},
        "fetch_errors": [],
        "pages": [page.as_dict()],
        "schema_detection": "static_html_only",
        "schema_note": "static",
    }
    with (
        patch("burnr8.tools.seo.audit_url", return_value=page),
        patch("burnr8.tools.seo.crawl_site", return_value=crawl_result),
        patch("burnr8.tools.seo.save_report", side_effect=_report),
    ):
        audited = tools["seo_audit_url"]("https://studywithlily.com/")
        crawled = tools["seo_crawl_site"]("https://studywithlily.com/")

    assert audited["schema_detection"] == "static_html_only"
    assert crawled["report"]["rows"] == 1


def test_demand_gap_joins_paid_conversions_to_weak_organic_query(tools):
    client = _FakeGscClient()
    client.analytics_payloads = [{"rows": [_gsc_row(["revision timetable"], 2, 200, 0.01, 18)]}]
    ads_rows = [
        {
            "search_term_view": {"search_term": " Revision   Timetable "},
            "metrics": {
                "impressions": 100,
                "clicks": 10,
                "cost_micros": 5000000,
                "conversions": 2,
                "conversions_value": 40,
            },
        }
    ]
    with (
        patch("burnr8.tools.seo.get_search_console_client", return_value=client),
        patch("burnr8.tools.seo.get_client", return_value=MagicMock()),
        patch("burnr8.tools.seo.require_customer_id", return_value=("1234567890", None)),
        patch("burnr8.tools.seo.run_gaql", return_value=ads_rows),
        patch("burnr8.tools.seo.save_report", side_effect=_report),
    ):
        result = tools["search_demand_gap"]("2026-06-01", "2026-06-30", property_url="sc-domain:studywithlily.com")

    row = result["top"][0]
    assert row["query"] == "revision timetable"
    assert row["classification"] == "seo_content_priority"
    assert row["paid_cost_dollars"] == 5
    assert "never pauses ads automatically" in result["safety_note"]


def test_default_period_ends_three_days_before_today(tools):
    client = _FakeGscClient()
    with (
        patch("burnr8.tools.seo.get_search_console_client", return_value=client),
        patch("burnr8.tools.seo.save_report", side_effect=_report),
    ):
        tools["gsc_search_performance"](property_url="sc-domain:studywithlily.com")

    assert client.calls[0][2]["endDate"] == (date.today().fromordinal(date.today().toordinal() - 3)).isoformat()
