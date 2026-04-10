from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import build_mutate_request, require_customer_id, run_gaql, validate_id
from burnr8.reports import save_report


class NegativeKeyword(BaseModel):
    """A negative keyword with text and match type to exclude from serving."""

    text: str = Field(description="The keyword text")
    match_type: str = Field(default="BROAD", description="Match type: EXACT, PHRASE, or BROAD")


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def list_negative_keywords(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        campaign_id: Annotated[str | None, Field(description="Filter by campaign ID")] = None,
        ad_group_id: Annotated[
            str | None, Field(description="Include ad-group-level negatives for this ad group ID")
        ] = None,
    ) -> dict:
        """List negative keywords at campaign level, and optionally at ad group level.

        Conflict detection uses exact text matching only; BROAD/PHRASE match type overlaps are not detected.
        """
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if ad_group_id is not None and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}

        client = get_client()

        # --- Campaign-level negatives ---
        campaign_query = """
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.keyword.text,
                campaign_criterion.keyword.match_type,
                campaign_criterion.negative,
                campaign.id,
                campaign.name
            FROM campaign_criterion
            WHERE campaign_criterion.type = 'KEYWORD'
                AND campaign_criterion.negative = true
        """
        if campaign_id:
            campaign_query += f" AND campaign.id = {campaign_id}"
        campaign_query += " ORDER BY campaign_criterion.keyword.text"

        rows = run_gaql(client, customer_id, campaign_query)
        campaign_negatives = []
        for row in rows:
            cc = row.get("campaign_criterion", {})
            kw = cc.get("keyword", {})
            c = row.get("campaign", {})
            campaign_negatives.append(
                {
                    "criterion_id": cc.get("criterion_id"),
                    "text": kw.get("text"),
                    "match_type": kw.get("match_type"),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                    "level": "CAMPAIGN",
                }
            )

        # --- Ad-group-level negatives (only when ad_group_id supplied) ---
        ad_group_negatives = []
        if ad_group_id:
            ag_query = f"""
                SELECT
                    ad_group_criterion.criterion_id,
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    ad_group_criterion.negative,
                    ad_group.id,
                    ad_group.name,
                    campaign.id,
                    campaign.name
                FROM ad_group_criterion
                WHERE ad_group_criterion.type = 'KEYWORD'
                    AND ad_group_criterion.negative = true
                    AND ad_group.id = {ad_group_id}
            """
            ag_query += " ORDER BY ad_group_criterion.keyword.text"

            ag_rows = run_gaql(client, customer_id, ag_query)
            for row in ag_rows:
                ac = row.get("ad_group_criterion", {})
                kw = ac.get("keyword", {})
                ag = row.get("ad_group", {})
                c = row.get("campaign", {})
                ad_group_negatives.append(
                    {
                        "criterion_id": ac.get("criterion_id"),
                        "text": kw.get("text"),
                        "match_type": kw.get("match_type"),
                        "ad_group_id": ag.get("id"),
                        "ad_group_name": ag.get("name"),
                        "campaign_id": c.get("id"),
                        "campaign_name": c.get("name"),
                        "level": "AD_GROUP",
                    }
                )

        # Combine into flat list with normalized schema (all rows get all 8 keys)
        all_negatives = []
        for item in campaign_negatives:
            all_negatives.append({**item, "ad_group_id": None, "ad_group_name": None})
        for item in ad_group_negatives:
            all_negatives.append(item)

        # --- Conflict detection: find positives blocked by negatives ---
        conflicts = []
        if all_negatives:
            # Collect campaign IDs that have negatives
            neg_campaign_ids = {neg["campaign_id"] for neg in all_negatives if neg.get("campaign_id")}
            if neg_campaign_ids:
                # Build a single query for positive keywords in those campaigns
                cid_filter = ", ".join(str(cid) for cid in neg_campaign_ids)
                pos_query = f"""
                    SELECT
                        ad_group_criterion.keyword.text,
                        ad_group_criterion.keyword.match_type,
                        ad_group_criterion.status,
                        ad_group.id,
                        ad_group.name,
                        campaign.id,
                        campaign.name
                    FROM keyword_view
                    WHERE campaign.id IN ({cid_filter})
                """
                pos_rows = run_gaql(client, customer_id, pos_query)

                # Build negative lookup: (campaign_id, lowercase text) -> negative info
                neg_lookup: dict[tuple[str, str], dict[str, Any]] = {}
                for neg in all_negatives:
                    key = (str(neg["campaign_id"]), (neg["text"] or "").lower())
                    neg_lookup[key] = neg

                for row in pos_rows:
                    cr = row.get("ad_group_criterion", {})
                    kw = cr.get("keyword", {})
                    ag = row.get("ad_group", {})
                    c = row.get("campaign", {})
                    pos_text = (kw.get("text") or "").lower()
                    cid = str(c.get("id"))

                    # Check exact text match between negative and positive
                    neg_match = neg_lookup.get((cid, pos_text))
                    if neg_match is not None:
                        conflicts.append(
                            {
                                "positive_keyword": kw.get("text"),
                                "positive_match_type": kw.get("match_type"),
                                "positive_ad_group_id": ag.get("id"),
                                "positive_ad_group_name": ag.get("name"),
                                "negative_keyword": neg_match["text"],
                                "negative_match_type": neg_match["match_type"],
                                "negative_level": neg_match["level"],
                                "campaign_id": cid,
                                "campaign_name": c.get("name"),
                            }
                        )

        report = save_report(all_negatives, "negative_keywords")
        if report.get("error"):
            return report

        # Count by level
        campaign_count = len(campaign_negatives)
        ad_group_count = len(ad_group_negatives)

        # Count by match type
        match_type_counts: dict[str, int] = {}
        for neg in all_negatives:
            mt = neg.get("match_type", "UNKNOWN")
            match_type_counts[mt] = match_type_counts.get(mt, 0) + 1

        report["summary"] = {
            "total": len(all_negatives),
            "by_level": {
                "CAMPAIGN": campaign_count,
                "AD_GROUP": ad_group_count,
            },
            "by_match_type": match_type_counts,
        }
        if conflicts:
            report["conflicts"] = conflicts
            report["summary"]["conflict_count"] = len(conflicts)
        return report

    @mcp.tool
    @handle_google_ads_errors
    def add_negative_keywords(
        campaign_id: Annotated[str, Field(description="Campaign ID to add negative keywords to")],
        keywords: Annotated[
            list[NegativeKeyword], Field(description="List of negative keywords with text and match_type")
        ],
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Add one or more negative keywords at campaign level via CampaignCriterionService."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        campaign_service = client.get_service("CampaignService")

        match_map = {
            "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
            "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
            "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
        }

        operations = []
        for kw in keywords:
            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
            criterion.negative = True

            criterion.keyword.text = kw.text
            criterion.keyword.match_type = match_map.get(
                kw.match_type.upper(),
                client.enums.KeywordMatchTypeEnum.BROAD,
            )
            operations.append(operation)

        response = campaign_criterion_service.mutate_campaign_criteria(
            request=build_mutate_request(client, "MutateCampaignCriteriaRequest", customer_id, operations, validate_only=not confirm)
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": f"Validation succeeded. This will add {len(keywords)} negative keyword(s). Set confirm=true to execute."}

        return {
            "added": len(response.results),
            "resource_names": [r.resource_name for r in response.results],
            "keywords": [{"text": kw.text, "match_type": kw.match_type} for kw in keywords],
        }

    @mcp.tool
    @handle_google_ads_errors
    def add_ad_group_negative_keywords(
        ad_group_id: Annotated[str, Field(description="Ad group ID to add negative keywords to")],
        keywords: Annotated[
            list[NegativeKeyword], Field(description="List of negative keywords with text and match_type")
        ],
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Add one or more negative keywords at ad group level via AdGroupCriterionService."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(ad_group_id, "ad_group_id"):
            return {"error": True, "message": err}

        client = get_client()
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        ad_group_service = client.get_service("AdGroupService")

        match_map = {
            "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
            "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
            "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
        }

        operations = []
        for kw in keywords:
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create
            criterion.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
            criterion.negative = True

            criterion.keyword.text = kw.text
            criterion.keyword.match_type = match_map.get(
                kw.match_type.upper(),
                client.enums.KeywordMatchTypeEnum.BROAD,
            )
            operations.append(operation)

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            request=build_mutate_request(client, "MutateAdGroupCriteriaRequest", customer_id, operations, validate_only=not confirm)
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": f"Validation succeeded. This will add {len(keywords)} ad group negative keyword(s). Set confirm=true to execute."}
        return {
            "added": len(response.results),
            "resource_names": [r.resource_name for r in response.results],
            "keywords": [{"text": kw.text, "match_type": kw.match_type} for kw in keywords],
        }

    @mcp.tool
    @handle_google_ads_errors
    def remove_negative_keyword(
        criterion_id: Annotated[str, Field(description="Negative keyword criterion ID to remove")],
        campaign_id: Annotated[
            str | None, Field(description="Campaign ID (required for campaign-level negatives)")
        ] = None,
        ad_group_id: Annotated[
            str | None, Field(description="Ad group ID (required for ad-group-level negatives)")
        ] = None,
        confirm: Annotated[bool, Field(description="Must be true to execute removal.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Remove a negative keyword. Provide campaign_id for campaign-level or ad_group_id for ad-group-level. Requires confirm=true."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(criterion_id, "criterion_id"):
            return {"error": True, "message": err}

        if not campaign_id and not ad_group_id:
            return {
                "error": True,
                "message": "Provide either campaign_id (campaign-level) or ad_group_id (ad-group-level).",
            }

        if campaign_id and ad_group_id:
            return {"error": True, "message": "Provide only one of campaign_id or ad_group_id, not both."}

        client = get_client()

        if campaign_id:
            if err := validate_id(campaign_id, "campaign_id"):
                return {"error": True, "message": err}
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            resource_name = campaign_criterion_service.campaign_criterion_path(customer_id, campaign_id, criterion_id)
            operation = client.get_type("CampaignCriterionOperation")
            operation.remove = resource_name
            response = campaign_criterion_service.mutate_campaign_criteria(
                request=build_mutate_request(client, "MutateCampaignCriteriaRequest", customer_id, [operation], validate_only=not confirm)
            )
        else:
            assert ad_group_id is not None
            if err := validate_id(ad_group_id, "ad_group_id"):
                return {"error": True, "message": err}
            ad_group_criterion_service = client.get_service("AdGroupCriterionService")
            resource_name = ad_group_criterion_service.ad_group_criterion_path(customer_id, ad_group_id, criterion_id)
            operation = client.get_type("AdGroupCriterionOperation")
            operation.remove = resource_name
            response = ad_group_criterion_service.mutate_ad_group_criteria(
                request=build_mutate_request(client, "MutateAdGroupCriteriaRequest", customer_id, [operation], validate_only=not confirm)
            )

        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "criterion_id": criterion_id,
                "level": "CAMPAIGN" if campaign_id else "AD_GROUP" if ad_group_id else "UNKNOWN",
                "message": f"Validation succeeded. This will remove negative keyword criterion {criterion_id}. Set confirm=true to execute.",
            }

        return {"removed": response.results[0].resource_name}
