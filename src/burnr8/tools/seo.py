"""Search Console, PageSpeed, CrUX, crawler, and paid/organic SEO tools."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.helpers import micros_to_dollars, require_customer_id, run_gaql
from burnr8.reports import save_report
from burnr8.seo.analysis import (
    compare_rows,
    crux_summary,
    demand_gap_rows,
    opportunity_rows,
    pagespeed_summary,
    search_analytics_rows,
)
from burnr8.seo.client import get_performance_client, get_search_console_client
from burnr8.seo.crawler import audit_url, crawl_site, validate_public_url
from burnr8.seo.errors import handle_seo_errors
from burnr8.seo.session import (
    require_search_console_property,
    set_active_search_console_property,
    validate_url_for_property,
)

_DIMENSIONS = {"date", "query", "page", "country", "device", "searchAppearance", "hour"}
_FILTER_DIMENSIONS = {"query", "page", "country", "device", "searchAppearance"}
_FILTER_OPERATORS = {"equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex"}
_SEARCH_TYPES = {"web", "image", "video", "news", "discover", "googleNews"}
_AGGREGATIONS = {"auto", "byPage", "byProperty"}


class SearchConsoleFilter(BaseModel):
    """One Search Console dimension filter."""

    dimension: str = Field(description="query, page, country, device, or searchAppearance")
    operator: str = Field(
        default="contains", description="equals, notEquals, contains, notContains, includingRegex, or excludingRegex"
    )
    expression: str = Field(min_length=1, max_length=500)

    @field_validator("dimension")
    @classmethod
    def validate_dimension(cls, value: str) -> str:
        if value not in _FILTER_DIMENSIONS:
            raise ValueError(f"Filter dimension must be one of: {', '.join(sorted(_FILTER_DIMENSIONS))}.")
        return value

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, value: str) -> str:
        if value not in _FILTER_OPERATORS:
            raise ValueError(f"Filter operator must be one of: {', '.join(sorted(_FILTER_OPERATORS))}.")
        return value


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_seo_errors
    def gsc_list_properties() -> dict[str, Any]:
        """List Search Console properties accessible to the configured OAuth user, including permission levels."""
        payload = get_search_console_client().list_properties()
        entries = payload.get("siteEntry", [])
        properties = entries if isinstance(entries, list) else []
        return {
            "properties": properties,
            "count": len(properties),
            "hint": "Call gsc_set_active_property once to use a property by default.",
        }

    @mcp.tool
    @handle_seo_errors
    def gsc_set_active_property(
        property_url: Annotated[
            str,
            Field(
                description="Exact Search Console property, such as sc-domain:studywithlily.com or https://studywithlily.com/"
            ),
        ],
    ) -> dict[str, Any]:
        """Verify and select a Search Console domain or URL-prefix property for subsequent SEO tools."""
        normalized = require_search_console_property(property_url)
        verified = get_search_console_client().get_property(normalized)
        set_active_search_console_property(normalized)
        return {
            "active_property": normalized,
            "permission_level": verified.get("permissionLevel"),
            "property": verified,
        }

    @mcp.tool
    @handle_seo_errors
    def gsc_search_performance(
        start_date: Annotated[
            str | None, Field(description="ISO start date; defaults to the last 28 complete-ish days")
        ] = None,
        end_date: Annotated[
            str | None, Field(description="ISO end date; defaults to three days ago for settled data")
        ] = None,
        dimensions: Annotated[
            list[str] | None, Field(description="Any of date, query, page, country, device, searchAppearance, hour")
        ] = None,
        filters: Annotated[
            list[SearchConsoleFilter] | None, Field(description="Optional AND-combined dimension filters")
        ] = None,
        search_type: Annotated[str, Field(description="web, image, video, news, discover, or googleNews")] = "web",
        aggregation_type: Annotated[str, Field(description="auto, byPage, or byProperty")] = "auto",
        data_state: Annotated[
            Literal["final", "all", "hourly_all"],
            Field(description="final settled data, all available data, or hourly_all for hourly dimension data"),
        ] = "final",
        row_limit: Annotated[int, Field(description="Maximum rows (1-25000)", ge=1, le=25000)] = 1000,
        start_row: Annotated[int, Field(description="Pagination offset", ge=0)] = 0,
        property_url: Annotated[
            str | None, Field(description="Search Console property; uses active/default property when omitted")
        ] = None,
    ) -> dict[str, Any]:
        """Query first-party organic clicks, impressions, CTR, and average position from Google Search Console and save the full report."""
        property_value = require_search_console_property(property_url)
        start, end = _date_window(start_date, end_date)
        selected_dimensions = _validate_dimensions(dimensions or ["query"], allow_hour=data_state == "hourly_all")
        body = _search_body(
            start,
            end,
            selected_dimensions,
            filters,
            search_type,
            aggregation_type,
            data_state,
            row_limit,
            start_row,
        )
        payload = get_search_console_client().query_search_analytics(property_value, body)
        rows = search_analytics_rows(payload, selected_dimensions)
        report = save_report(rows, "gsc_search_performance")
        report["summary"] = _performance_summary(rows, start, end, property_value)
        report["metadata"] = {
            "dimensions": selected_dimensions,
            "search_type": search_type,
            "aggregation_type": aggregation_type,
            "data_state": data_state,
            "start_row": start_row,
            "requested_row_limit": row_limit,
            "more_rows_may_exist": len(rows) == row_limit,
        }
        if "query" in selected_dimensions:
            report["metadata"]["privacy_note"] = (
                "Search Console queries can contain user-entered or sensitive text; handle exported reports accordingly."
            )
        return report

    @mcp.tool
    @handle_seo_errors
    def gsc_compare_periods(
        current_start_date: Annotated[
            str | None, Field(description="Current ISO start date; defaults to a recent 28-day window")
        ] = None,
        current_end_date: Annotated[
            str | None, Field(description="Current ISO end date; defaults to three days ago")
        ] = None,
        previous_start_date: Annotated[
            str | None, Field(description="Comparison ISO start date; defaults to preceding equal-length period")
        ] = None,
        previous_end_date: Annotated[
            str | None, Field(description="Comparison ISO end date; defaults to preceding equal-length period")
        ] = None,
        dimensions: Annotated[list[str] | None, Field(description="Comparison keys; defaults to query")] = None,
        search_type: Annotated[str, Field(description="Search type, normally web")] = "web",
        row_limit: Annotated[int, Field(description="Rows per period (1-25000)", ge=1, le=25000)] = 5000,
        property_url: Annotated[
            str | None, Field(description="Search Console property; uses active/default when omitted")
        ] = None,
    ) -> dict[str, Any]:
        """Compare organic search metrics across two equal or explicit periods and save metric deltas by query, page, or other dimensions."""
        property_value = require_search_console_property(property_url)
        current_start, current_end = _date_window(current_start_date, current_end_date)
        duration = current_end - current_start
        if previous_start_date is None and previous_end_date is None:
            previous_end = current_start - timedelta(days=1)
            previous_start = previous_end - duration
        elif previous_start_date and previous_end_date:
            previous_start, previous_end = _date_window(previous_start_date, previous_end_date, use_defaults=False)
        else:
            raise ValueError("Provide both previous_start_date and previous_end_date, or omit both.")
        selected_dimensions = _validate_dimensions(dimensions or ["query"])
        client = get_search_console_client()
        common = (selected_dimensions, None, search_type, "auto", "final", row_limit, 0)
        current_payload = client.query_search_analytics(
            property_value, _search_body(current_start, current_end, *common)
        )
        previous_payload = client.query_search_analytics(
            property_value, _search_body(previous_start, previous_end, *common)
        )
        current_rows = search_analytics_rows(current_payload, selected_dimensions)
        previous_rows = search_analytics_rows(previous_payload, selected_dimensions)
        rows = compare_rows(current_rows, previous_rows, selected_dimensions)
        report = save_report(rows, "gsc_period_comparison")
        report["summary"] = {
            "property": property_value,
            "current_period": {"start": current_start.isoformat(), "end": current_end.isoformat()},
            "previous_period": {"start": previous_start.isoformat(), "end": previous_end.isoformat()},
            "dimensions": selected_dimensions,
            "current_totals": _totals(current_rows),
            "previous_totals": _totals(previous_rows),
            "rows_compared": len(rows),
        }
        return report

    @mcp.tool
    @handle_seo_errors
    def gsc_find_opportunities(
        start_date: Annotated[str | None, Field(description="ISO start date; defaults to recent 28-day window")] = None,
        end_date: Annotated[str | None, Field(description="ISO end date; defaults to three days ago")] = None,
        min_impressions: Annotated[int, Field(description="Minimum query impressions", ge=1)] = 100,
        max_ctr_percent: Annotated[
            float, Field(description="CTR threshold used for low-CTR flags", ge=0, le=100)
        ] = 2.0,
        row_limit: Annotated[int, Field(description="Queries and query-page rows to inspect", ge=1, le=25000)] = 10000,
        property_url: Annotated[
            str | None, Field(description="Search Console property; uses active/default when omitted")
        ] = None,
    ) -> dict[str, Any]:
        """Rank transparent SEO opportunities: striking-distance queries, low CTR, content gaps, and possible query cannibalization."""
        property_value = require_search_console_property(property_url)
        start, end = _date_window(start_date, end_date)
        client = get_search_console_client()
        query_payload = client.query_search_analytics(
            property_value, _search_body(start, end, ["query"], None, "web", "auto", "final", row_limit, 0)
        )
        page_payload = client.query_search_analytics(
            property_value, _search_body(start, end, ["query", "page"], None, "web", "auto", "final", row_limit, 0)
        )
        rows = opportunity_rows(
            search_analytics_rows(query_payload, ["query"]),
            search_analytics_rows(page_payload, ["query", "page"]),
            min_impressions=min_impressions,
            max_ctr_percent=max_ctr_percent,
        )
        report = save_report(rows, "gsc_seo_opportunities")
        report["summary"] = {
            "property": property_value,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "opportunities": len(rows),
            "by_type": dict(Counter(kind for row in rows for kind in str(row["opportunity_types"]).split(","))),
        }
        report["scoring_note"] = (
            "Scores are prioritization heuristics based on impressions, position, CTR, and page overlap—not traffic forecasts."
        )
        report["coverage_note"] = (
            "Search Analytics can return a sampled/top-row view; paginate or narrow the query if either source hit row_limit."
        )
        return report

    @mcp.tool
    @handle_seo_errors
    def gsc_inspect_url(
        url: Annotated[str, Field(description="Exact URL to inspect in Google's index")],
        language_code: Annotated[str, Field(description="BCP-47 response language code")] = "en-US",
        property_url: Annotated[
            str | None, Field(description="Owning Search Console property; uses active/default when omitted")
        ] = None,
    ) -> dict[str, Any]:
        """Inspect a property's URL for Google index status, crawl state, canonicals, mobile usability, and rich-result findings."""
        property_value = require_search_console_property(property_url)
        inspected_url = validate_url_for_property(url, property_value)
        payload = get_search_console_client().inspect_url(property_value, inspected_url, language_code)
        result = payload.get("inspectionResult", {})
        index = result.get("indexStatusResult", {}) if isinstance(result, dict) else {}
        return {
            "property": property_value,
            "url": inspected_url,
            "summary": {
                "verdict": index.get("verdict"),
                "coverage_state": index.get("coverageState"),
                "indexing_state": index.get("indexingState"),
                "robots_txt_state": index.get("robotsTxtState"),
                "last_crawl_time": index.get("lastCrawlTime"),
                "google_canonical": index.get("googleCanonical"),
                "user_canonical": index.get("userCanonical"),
                "page_fetch_state": index.get("pageFetchState"),
            },
            "inspection_result": result,
            "note": "URL Inspection reports Google's indexed view; it does not request general-purpose indexing.",
        }

    @mcp.tool
    @handle_seo_errors
    def gsc_list_sitemaps(
        property_url: Annotated[
            str | None, Field(description="Search Console property; uses active/default when omitted")
        ] = None,
    ) -> dict[str, Any]:
        """List submitted Search Console sitemaps and their processing, warning, error, and content counts."""
        property_value = require_search_console_property(property_url)
        payload = get_search_console_client().list_sitemaps(property_value)
        sitemaps = payload.get("sitemap", [])
        values = sitemaps if isinstance(sitemaps, list) else []
        return {"property": property_value, "sitemaps": values, "count": len(values)}

    @mcp.tool
    @handle_seo_errors
    def gsc_submit_sitemap(
        sitemap_url: Annotated[str, Field(description="Absolute sitemap URL owned by the selected property")],
        confirm: Annotated[bool, Field(description="Must be true to submit the sitemap to Search Console")] = False,
        property_url: Annotated[
            str | None, Field(description="Owning Search Console property; uses active/default when omitted")
        ] = None,
    ) -> dict[str, Any]:
        """Validate and optionally submit a sitemap to Search Console. No API mutation occurs until confirm=true."""
        property_value = require_search_console_property(property_url)
        validated_url = validate_url_for_property(sitemap_url, property_value)
        if not confirm:
            return {
                "warning": True,
                "validated": "client_side",
                "property": property_value,
                "sitemap_url": validated_url,
                "message": "Nothing was submitted. Set confirm=true to submit this sitemap to Search Console.",
            }
        get_search_console_client().submit_sitemap(property_value, validated_url)
        return {"submitted": True, "property": property_value, "sitemap_url": validated_url}

    @mcp.tool
    @handle_seo_errors
    def pagespeed_analyze(
        url: Annotated[str, Field(description="Public page URL to analyze")],
        strategy: Annotated[
            Literal["mobile", "desktop"], Field(description="Lighthouse emulation strategy")
        ] = "mobile",
        include_crux: Annotated[
            bool, Field(description="Also query CrUX field data when an API key is configured")
        ] = True,
        crux_origin_fallback: Annotated[
            bool, Field(description="If exact URL field data is unavailable, query its origin")
        ] = True,
    ) -> dict[str, Any]:
        """Analyze a public URL with PageSpeed Insights Lighthouse scores and optional standalone CrUX field data."""
        parsed = validate_public_url(url)
        client = get_performance_client()
        payload = client.pagespeed(
            url,
            strategy=strategy,
            categories=["PERFORMANCE", "ACCESSIBILITY", "BEST_PRACTICES", "SEO"],
        )
        result: dict[str, Any] = {
            "url": url,
            "strategy": strategy,
            "lab": pagespeed_summary(payload),
            "field": None,
            "field_status": "not_requested",
        }
        if include_crux:
            if not client.crux_configured:
                result["field_status"] = "not_configured"
                result["field_note"] = "Set GOOGLE_CRUX_API_KEY (or GOOGLE_PAGESPEED_API_KEY) for CrUX field data."
            else:
                try:
                    form_factor = "PHONE" if strategy == "mobile" else "DESKTOP"
                    result["field"] = crux_summary(client.crux(url, form_factor=form_factor))
                    result["field_status"] = "url"
                except Exception as ex:
                    if not crux_origin_fallback:
                        raise
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                    form_factor = "PHONE" if strategy == "mobile" else "DESKTOP"
                    result["field"] = crux_summary(client.crux(origin, form_factor=form_factor, origin=True))
                    result["field_status"] = "origin_fallback"
                    result["field_note"] = (
                        f"Exact URL CrUX data was unavailable ({type(ex).__name__}); returned origin-level field data."
                    )
        return result

    @mcp.tool
    @handle_seo_errors
    def seo_audit_url(
        url: Annotated[str, Field(description="Public page URL for a bounded static-HTML on-page audit")],
    ) -> dict[str, Any]:
        """Audit one public page for status, title, description, headings, canonical, robots, images, links, and static JSON-LD."""
        page = audit_url(url)
        result = page.as_dict()
        result["schema_detection"] = "static_html_only"
        result["schema_note"] = (
            "Client-rendered schema is not executed; use rendered testing or Search Console rich results for confirmation."
        )
        return result

    @mcp.tool
    @handle_seo_errors
    def seo_crawl_site(
        start_url: Annotated[str, Field(description="Public starting URL; crawl remains on its exact host")],
        max_pages: Annotated[int, Field(description="Maximum pages; server hard cap defaults to 100", ge=1)] = 25,
        max_depth: Annotated[int, Field(description="Maximum link depth (0-10)", ge=0, le=10)] = 3,
        respect_robots: Annotated[bool, Field(description="Respect robots.txt for the Burnr8 crawler")] = True,
    ) -> dict[str, Any]:
        """Crawl a bounded same-host site sample with SSRF guards, robots handling, duplicate metadata checks, and technical SEO findings."""
        result = crawl_site(start_url, max_pages=max_pages, max_depth=max_depth, respect_robots=respect_robots)
        raw_pages = result.pop("pages")
        if not isinstance(raw_pages, list):
            raise TypeError("SEO crawler returned an invalid pages collection.")
        pages: list[Any] = raw_pages
        report_rows = [_crawl_report_row(page) for page in pages if isinstance(page, dict)]
        report = save_report(report_rows, "seo_site_crawl")
        result["report"] = report
        result["sample_pages"] = pages[:5]
        return result

    @mcp.tool
    @handle_seo_errors
    def search_demand_gap(
        start_date: Annotated[
            str | None, Field(description="ISO start date shared by Search Console and Google Ads")
        ] = None,
        end_date: Annotated[
            str | None, Field(description="ISO end date shared by Search Console and Google Ads")
        ] = None,
        row_limit: Annotated[int, Field(description="Maximum Search Console query rows", ge=1, le=25000)] = 10000,
        property_url: Annotated[
            str | None, Field(description="Search Console property; uses active/default when omitted")
        ] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID; uses active account when omitted")
        ] = None,
    ) -> dict[str, Any]:
        """Join Search Console queries with Google Ads search terms to find SEO content priorities and paid incrementality test candidates."""
        property_value = require_search_console_property(property_url)
        ads_customer_id, cid_error = require_customer_id(customer_id)
        if cid_error:
            return cid_error
        start, end = _date_window(start_date, end_date)
        organic_payload = get_search_console_client().query_search_analytics(
            property_value, _search_body(start, end, ["query"], None, "web", "auto", "final", row_limit, 0)
        )
        organic = search_analytics_rows(organic_payload, ["query"])
        ads_query = f"""
            SELECT
                search_term_view.search_term,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
            FROM search_term_view
            WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
            ORDER BY metrics.cost_micros DESC
        """
        ads_rows = run_gaql(get_client(), ads_customer_id, ads_query)
        paid: list[dict[str, Any]] = []
        for row in ads_rows:
            search_term = row.get("search_term_view", {})
            metrics = row.get("metrics", {})
            paid.append(
                {
                    "query": search_term.get("search_term"),
                    "impressions": metrics.get("impressions", 0),
                    "clicks": metrics.get("clicks", 0),
                    "cost": micros_to_dollars(int(metrics.get("cost_micros", 0))),
                    "conversions": metrics.get("conversions", 0),
                    "value": metrics.get("conversions_value", 0),
                }
            )
        rows = demand_gap_rows(organic, paid)
        report = save_report(rows, "paid_organic_demand_gap")
        report["summary"] = {
            "property": property_value,
            "google_ads_customer_id": ads_customer_id,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "queries": len(rows),
            "by_classification": dict(Counter(str(row["classification"]) for row in rows)),
        }
        report["safety_note"] = (
            "A top-three organic position is only an incrementality test candidate; Burnr8 never pauses ads automatically."
        )
        report["privacy_note"] = (
            "This report contains user search queries from Search Console and Google Ads; treat the CSV as potentially sensitive."
        )
        return report


def _date_window(start_value: str | None, end_value: str | None, *, use_defaults: bool = True) -> tuple[date, date]:
    default_end = date.today() - timedelta(days=3)
    default_start = default_end - timedelta(days=27)
    if not use_defaults and (not start_value or not end_value):
        raise ValueError("Both start and end dates are required.")
    try:
        start = date.fromisoformat(start_value) if start_value else default_start
        end = date.fromisoformat(end_value) if end_value else default_end
    except ValueError:
        raise ValueError("Dates must use ISO format YYYY-MM-DD.") from None
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    if (end - start).days > 600:
        raise ValueError("Date range cannot exceed 601 days.")
    return start, end


def _validate_dimensions(dimensions: list[str], *, allow_hour: bool = False) -> list[str]:
    if not dimensions or len(dimensions) > 5:
        raise ValueError("Provide between one and five Search Console dimensions.")
    if len(dimensions) != len(set(dimensions)):
        raise ValueError("Search Console dimensions must be unique.")
    invalid = set(dimensions) - _DIMENSIONS
    if invalid:
        raise ValueError(f"Unsupported Search Console dimensions: {', '.join(sorted(invalid))}.")
    if "hour" in dimensions and not allow_hour:
        raise ValueError(
            "The hour dimension requires data_state='hourly_all' and is only supported by gsc_search_performance."
        )
    return dimensions


def _search_body(
    start: date,
    end: date,
    dimensions: list[str],
    filters: list[SearchConsoleFilter] | None,
    search_type: str,
    aggregation_type: str,
    data_state: str,
    row_limit: int,
    start_row: int,
) -> dict[str, Any]:
    if search_type not in _SEARCH_TYPES:
        raise ValueError(f"search_type must be one of: {', '.join(sorted(_SEARCH_TYPES))}.")
    if aggregation_type not in _AGGREGATIONS:
        raise ValueError(f"aggregation_type must be one of: {', '.join(sorted(_AGGREGATIONS))}.")
    body: dict[str, Any] = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dimensions,
        "type": search_type,
        "aggregationType": aggregation_type,
        "dataState": data_state,
        "rowLimit": row_limit,
        "startRow": start_row,
    }
    if filters:
        parsed_filters = [
            item if isinstance(item, SearchConsoleFilter) else SearchConsoleFilter.model_validate(item)
            for item in filters
        ]
        body["dimensionFilterGroups"] = {
            "groupType": "and",
            "filters": [item.model_dump() for item in parsed_filters],
        }
        body["dimensionFilterGroups"] = [body["dimensionFilterGroups"]]
    return body


def _totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    clicks = sum(float(row.get("clicks", 0)) for row in rows)
    impressions = sum(float(row.get("impressions", 0)) for row in rows)
    return {
        "clicks": round(clicks, 2),
        "impressions": round(impressions, 2),
        "ctr_percent": round(clicks / impressions * 100, 2) if impressions else 0,
    }


def _performance_summary(rows: list[dict[str, Any]], start: date, end: date, property_value: str) -> dict[str, Any]:
    totals = _totals(rows)
    weighted_position = sum(float(row.get("position", 0)) * float(row.get("impressions", 0)) for row in rows)
    impressions = totals["impressions"]
    return {
        "property": property_value,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        **totals,
        "weighted_average_position": round(weighted_position / impressions, 2) if impressions else None,
        "rows": len(rows),
    }


def _crawl_report_row(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": page.get("url"),
        "final_url": page.get("final_url"),
        "status_code": page.get("status_code"),
        "crawl_depth": page.get("crawl_depth"),
        "title": page.get("title"),
        "meta_description": page.get("meta_description"),
        "canonical": page.get("canonical"),
        "meta_robots": page.get("meta_robots"),
        "h1": " | ".join(page.get("h1", [])),
        "word_count": page.get("word_count"),
        "internal_links_count": len(page.get("internal_links", [])),
        "images_count": page.get("images_count"),
        "images_missing_alt": page.get("images_missing_alt"),
        "static_json_ld_blocks": page.get("static_json_ld_blocks"),
        "blocked_by_robots": page.get("blocked_by_robots"),
        "findings": json.dumps(page.get("findings", []), separators=(",", ":")),
    }
