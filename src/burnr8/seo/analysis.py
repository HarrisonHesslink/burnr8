"""Pure transformations for Search Console, PageSpeed, and paid/organic analysis."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


def search_analytics_rows(payload: Mapping[str, Any], dimensions: Sequence[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    raw_rows = payload.get("rows", [])
    if not isinstance(raw_rows, list):
        return results
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            continue
        keys = raw.get("keys", [])
        keys = keys if isinstance(keys, list) else []
        row = {dimension: keys[index] if index < len(keys) else None for index, dimension in enumerate(dimensions)}
        clicks = _float(raw.get("clicks"))
        impressions = _float(raw.get("impressions"))
        ctr = _float(raw.get("ctr"))
        row.update(
            {
                "clicks": round(clicks, 2),
                "impressions": round(impressions, 2),
                "ctr": round(ctr, 6),
                "ctr_percent": round(ctr * 100, 2),
                "position": round(_float(raw.get("position")), 2),
            }
        )
        results.append(row)
    return results


def compare_rows(
    current: Sequence[Mapping[str, Any]],
    previous: Sequence[Mapping[str, Any]],
    dimensions: Sequence[str],
) -> list[dict[str, Any]]:
    def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, ...], Mapping[str, Any]]:
        return {tuple(str(row.get(dimension, "")) for dimension in dimensions): row for row in rows}

    current_map = keyed(current)
    previous_map = keyed(previous)
    merged: list[dict[str, Any]] = []
    for key in current_map.keys() | previous_map.keys():
        now = current_map.get(key, {})
        before = previous_map.get(key, {})
        row: dict[str, Any] = {dimension: key[index] for index, dimension in enumerate(dimensions)}
        for metric in ("clicks", "impressions", "ctr_percent", "position"):
            current_value = _float(now.get(metric))
            previous_value = _float(before.get(metric))
            row[f"current_{metric}"] = round(current_value, 2)
            row[f"previous_{metric}"] = round(previous_value, 2)
            row[f"delta_{metric}"] = round(current_value - previous_value, 2)
        merged.append(row)
    merged.sort(key=lambda row: (abs(_float(row["delta_clicks"])), _float(row["current_impressions"])), reverse=True)
    return merged


def opportunity_rows(
    query_rows: Sequence[Mapping[str, Any]],
    query_page_rows: Sequence[Mapping[str, Any]],
    *,
    min_impressions: int,
    max_ctr_percent: float,
) -> list[dict[str, Any]]:
    pages_by_query: defaultdict[str, set[str]] = defaultdict(set)
    for row in query_page_rows:
        query = normalize_query(row.get("query"))
        page = str(row.get("page") or "")
        if query and page and _float(row.get("impressions")) > 0:
            pages_by_query[query].add(page)

    opportunities: list[dict[str, Any]] = []
    for row in query_rows:
        query = normalize_query(row.get("query"))
        if not query:
            continue
        impressions = _float(row.get("impressions"))
        ctr_percent = _float(row.get("ctr_percent"))
        position = _float(row.get("position"))
        types: list[str] = []
        if impressions >= min_impressions and 4 <= position <= 20:
            types.append("striking_distance")
        if impressions >= min_impressions and position <= 10 and ctr_percent < max_ctr_percent:
            types.append("low_ctr")
        if impressions >= min_impressions and position > 20:
            types.append("content_gap")
        pages = sorted(pages_by_query.get(query, set()))
        if len(pages) > 1:
            types.append("possible_cannibalization")
        if not types:
            continue
        position_factor = max(0.25, 22 - min(position, 21)) / 18
        ctr_factor = 1 + max(0, max_ctr_percent - ctr_percent) / max(max_ctr_percent, 0.1)
        score = math.log10(max(10, impressions)) * position_factor * ctr_factor * 25
        if len(pages) > 1:
            score *= 1.15
        opportunities.append(
            {
                "query": query,
                "opportunity_types": ",".join(types),
                "opportunity_score": round(score, 1),
                "clicks": _float(row.get("clicks")),
                "impressions": impressions,
                "ctr_percent": ctr_percent,
                "position": position,
                "ranking_pages_count": len(pages),
                "ranking_pages": " | ".join(pages),
            }
        )
    opportunities.sort(key=lambda item: (_float(item["opportunity_score"]), _float(item["impressions"])), reverse=True)
    return opportunities


def pagespeed_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    lighthouse = payload.get("lighthouseResult")
    lighthouse = lighthouse if isinstance(lighthouse, Mapping) else {}
    categories = lighthouse.get("categories")
    categories = categories if isinstance(categories, Mapping) else {}
    scores: dict[str, float | None] = {}
    for name, category in categories.items():
        score = category.get("score") if isinstance(category, Mapping) else None
        scores[str(name)] = round(_float(score) * 100) if score is not None else None

    audits = lighthouse.get("audits")
    audits = audits if isinstance(audits, Mapping) else {}
    diagnostics: list[dict[str, Any]] = []
    for audit_id, raw in audits.items():
        if not isinstance(raw, Mapping):
            continue
        score = raw.get("score")
        if score is None or _float(score) >= 0.9 or raw.get("scoreDisplayMode") in {"notApplicable", "manual"}:
            continue
        diagnostics.append(
            {
                "audit": str(audit_id),
                "title": str(raw.get("title", ""))[:200],
                "score": round(_float(score), 3),
                "display_value": str(raw.get("displayValue", ""))[:200] or None,
            }
        )
    diagnostics.sort(key=lambda item: _float(item["score"]))
    return {
        "requested_url": payload.get("id") or lighthouse.get("requestedUrl"),
        "final_url": lighthouse.get("finalUrl"),
        "fetch_time": lighthouse.get("fetchTime"),
        "lighthouse_version": lighthouse.get("lighthouseVersion"),
        "category_scores": scores,
        "diagnostics": diagnostics[:20],
        "runtime_error": lighthouse.get("runtimeError"),
    }


def crux_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    record = payload.get("record")
    record = record if isinstance(record, Mapping) else {}
    metrics = record.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    result: dict[str, Any] = {
        "key": record.get("key"),
        "collection_period": record.get("collectionPeriod"),
        "metrics": {},
    }
    for name, raw in metrics.items():
        if not isinstance(raw, Mapping):
            continue
        percentiles = raw.get("percentiles")
        percentiles = percentiles if isinstance(percentiles, Mapping) else {}
        result["metrics"][str(name)] = {"p75": percentiles.get("p75"), "histogram": raw.get("histogram")}
    return result


def demand_gap_rows(
    organic_rows: Sequence[Mapping[str, Any]],
    paid_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    organic: defaultdict[str, dict[str, float]] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "weighted_position": 0}
    )
    for row in organic_rows:
        query = normalize_query(row.get("query"))
        if not query:
            continue
        impressions = _float(row.get("impressions"))
        bucket = organic[query]
        bucket["clicks"] += _float(row.get("clicks"))
        bucket["impressions"] += impressions
        bucket["weighted_position"] += _float(row.get("position")) * max(impressions, 1)

    paid: defaultdict[str, dict[str, float]] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "cost": 0, "conversions": 0, "value": 0}
    )
    for row in paid_rows:
        query = normalize_query(row.get("query") or row.get("search_term"))
        if not query:
            continue
        bucket = paid[query]
        for key in ("clicks", "impressions", "cost", "conversions", "value"):
            bucket[key] += _float(row.get(key))

    output: list[dict[str, Any]] = []
    for query in organic.keys() | paid.keys():
        org = organic.get(query, {})
        ad = paid.get(query, {})
        org_impressions = _float(org.get("impressions"))
        position = _float(org.get("weighted_position")) / max(org_impressions, 1)
        paid_cost = _float(ad.get("cost"))
        conversions = _float(ad.get("conversions"))
        if paid_cost > 0 and conversions > 0 and (org_impressions == 0 or position > 10):
            label = "seo_content_priority"
        elif paid_cost > 0 and org_impressions > 0 and position <= 3:
            label = "paid_incrementality_test_candidate"
        elif paid_cost > 0 and org_impressions > 0:
            label = "paid_and_organic"
        elif paid_cost > 0:
            label = "paid_only"
        else:
            label = "organic_only"
        score = paid_cost + conversions * 25 + math.log10(max(10, org_impressions)) * 5
        output.append(
            {
                "query": query,
                "classification": label,
                "priority_score": round(score, 2),
                "organic_clicks": round(_float(org.get("clicks")), 2),
                "organic_impressions": round(org_impressions, 2),
                "organic_position": round(position, 2) if org_impressions else None,
                "paid_clicks": round(_float(ad.get("clicks")), 2),
                "paid_impressions": round(_float(ad.get("impressions")), 2),
                "paid_cost_dollars": round(paid_cost, 2),
                "paid_conversions": round(conversions, 2),
                "paid_conversion_value": round(_float(ad.get("value")), 2),
            }
        )
    output.sort(key=lambda item: _float(item["priority_score"]), reverse=True)
    return output


def normalize_query(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _float(value: object) -> float:
    if not isinstance(value, (int, float, str)):
        return 0.0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
