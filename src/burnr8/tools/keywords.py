from typing import Annotated

from pydantic import BaseModel, Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id
from burnr8.reports import save_report
from burnr8.session import resolve_customer_id


class KeywordInput(BaseModel):
    text: str = Field(description="The keyword text")
    match_type: str = Field(default="BROAD", description="Match type: EXACT, PHRASE, or BROAD")


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_keywords(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        ad_group_id: Annotated[str | None, Field(description="Filter by ad group ID")] = None,
    ) -> dict:
        """List keyword inventory — what keywords exist, their config, bids, match types, and quality scores. Filter by ad group."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if ad_group_id and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}
        client = get_client()
        query = """
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group_criterion.cpc_bid_micros,
                ad_group_criterion.quality_info.quality_score,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM keyword_view
        """
        conditions = []
        if ad_group_id:
            conditions.append(f"ad_group.id = {ad_group_id}")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY ad_group_criterion.keyword.text"

        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            cr = row.get("ad_group_criterion", {})
            kw = cr.get("keyword", {})
            qi = cr.get("quality_info", {})
            ag = row.get("ad_group", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            results.append(
                {
                    "criterion_id": cr.get("criterion_id"),
                    "text": kw.get("text"),
                    "match_type": kw.get("match_type"),
                    "status": cr.get("status"),
                    "cpc_bid_dollars": int(cr.get("cpc_bid_micros", 0)) / 1_000_000,
                    "quality_score": qi.get("quality_score"),
                    "ad_group_id": ag.get("id"),
                    "ad_group_name": ag.get("name"),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost_dollars": int(m.get("cost_micros", 0)) / 1_000_000,
                    "conversions": float(m.get("conversions", 0)),
                }
            )

        report = save_report(results, "keywords")
        if report.get("error"):
            return report
        quality_scores = [r["quality_score"] for r in results if r["quality_score"]]
        match_types: dict[str, int] = {}
        for r in results:
            mt = r.get("match_type", "UNKNOWN")
            match_types[mt] = match_types.get(mt, 0) + 1
        report["summary"] = {
            "keyword_count": len(results),
            "avg_quality_score": round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else None,
            "match_type_distribution": match_types,
        }
        return report

    @mcp.tool
    @handle_google_ads_errors
    def add_keywords(
        ad_group_id: Annotated[str, Field(description="Ad group ID to add keywords to")],
        keywords: Annotated[list[KeywordInput], Field(description="List of keywords with text and match_type")],
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Add one or more keywords to an ad group."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(ad_group_id, "ad_group_id"):
            return {"error": True, "message": err}
        client = get_client()
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        ad_group_service = client.get_service("AdGroupService")

        operations = []
        for kw in keywords:
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create
            criterion.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
            criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED

            match_map = {
                "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
                "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
                "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
            }
            criterion.keyword.text = kw.text
            criterion.keyword.match_type = match_map.get(
                kw.match_type.upper(),
                client.enums.KeywordMatchTypeEnum.BROAD,
            )
            operations.append(operation)

        response = ad_group_criterion_service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
        return {
            "added": len(response.results),
            "resource_names": [r.resource_name for r in response.results],
            "keywords": [{"text": kw.text, "match_type": kw.match_type} for kw in keywords],
        }

    @mcp.tool
    @handle_google_ads_errors
    def remove_keyword(
        ad_group_id: Annotated[str, Field(description="Ad group ID containing the keyword")],
        criterion_id: Annotated[str, Field(description="Keyword criterion ID to remove")],
        confirm: Annotated[bool, Field(description="Must be true to execute removal.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Remove a keyword from an ad group. Requires confirm=true."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if not confirm:
            return {
                "warning": True,
                "criterion_id": criterion_id,
                "ad_group_id": ad_group_id,
                "message": f"This will remove keyword criterion {criterion_id} from ad group {ad_group_id}. "
                f"Set confirm=true to execute.",
            }

        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(ad_group_id, "ad_group_id"):
            return {"error": True, "message": err}
        if err := validate_id(criterion_id, "criterion_id"):
            return {"error": True, "message": err}
        client = get_client()
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")

        resource_name = ad_group_criterion_service.ad_group_criterion_path(customer_id, ad_group_id, criterion_id)
        operation = client.get_type("AdGroupCriterionOperation")
        operation.remove = resource_name

        response = ad_group_criterion_service.mutate_ad_group_criteria(customer_id=customer_id, operations=[operation])
        return {"removed": response.results[0].resource_name}

    @mcp.tool
    @handle_google_ads_errors
    def research_keywords(
        keywords: Annotated[list[str], Field(description="Seed keywords to research")],
        url: Annotated[str | None, Field(description="URL to extract keyword ideas from")] = None,
        language_id: Annotated[str, Field(description="Language criterion ID (1000=English)")] = "1000",
        geo_target_ids: Annotated[list[str] | None, Field(description="Geo target criterion IDs (2840=US)")] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get keyword ideas with search volume, competition, and CPC estimates. Saves full report to CSV, returns summary + top rows + file path."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {
                "error": True,
                "message": "No customer_id provided and no active account set. Call set_active_account first.",
            }
        if geo_target_ids is None:
            geo_target_ids = ["2840"]
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        client = get_client()
        keyword_plan_idea_service = client.get_service("KeywordPlanIdeaService")
        keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

        request = client.get_type("GenerateKeywordIdeasRequest")
        request.customer_id = customer_id
        request.language = f"languageConstants/{language_id}"
        request.keyword_plan_network = keyword_plan_network

        for geo_id in geo_target_ids:
            request.geo_target_constants.append(f"geoTargetConstants/{geo_id}")

        # Use the correct oneof seed field
        if url and keywords:
            request.keyword_and_url_seed.url = url
            request.keyword_and_url_seed.keywords.extend(keywords)
        elif url:
            request.url_seed.url = url
        elif keywords:
            request.keyword_seed.keywords.extend(keywords)

        response = keyword_plan_idea_service.generate_keyword_ideas(request=request)

        results = []
        for idea in response.results:
            metrics = idea.keyword_idea_metrics
            results.append(
                {
                    "keyword": idea.text,
                    "avg_monthly_searches": metrics.avg_monthly_searches if metrics else 0,
                    "competition": metrics.competition.name if metrics else "UNKNOWN",
                    "low_top_of_page_bid_dollars": (metrics.low_top_of_page_bid_micros or 0) / 1_000_000
                    if metrics
                    else 0,
                    "high_top_of_page_bid_dollars": (metrics.high_top_of_page_bid_micros or 0) / 1_000_000
                    if metrics
                    else 0,
                }
            )

        report = save_report(results, "keyword_research")
        if report.get("error"):
            return report
        searches = [r["avg_monthly_searches"] for r in results if r["avg_monthly_searches"]]
        cpcs = [r["high_top_of_page_bid_dollars"] for r in results if r["high_top_of_page_bid_dollars"]]
        report["summary"] = {
            "keyword_count": len(results),
            "avg_monthly_searches": round(sum(searches) / len(searches), 1) if searches else 0,
            "avg_cpc_dollars": round(sum(cpcs) / len(cpcs), 2) if cpcs else 0,
        }
        return report
