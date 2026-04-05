from typing import Annotated

from pydantic import Field

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import run_gaql, validate_id
from burnr8.reports import save_report
from burnr8.session import resolve_customer_id


def register(mcp):
    @mcp.tool
    @handle_google_ads_errors
    def list_extensions(
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
        campaign_id: Annotated[str | None, Field(description="Campaign ID to filter by. If omitted, lists all campaign-level extensions in the account.")] = None,
        field_type: Annotated[str | None, Field(description="Filter by extension type: SITELINK, CALLOUT, STRUCTURED_SNIPPET, or SQUARE_MARKETING_IMAGE")] = None,
    ) -> dict:
        """List all asset-based extensions (sitelinks, callouts, structured snippets, images) linked to a campaign or account. Saves full results to CSV, returns summary + top rows."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}

        valid_field_types = {"SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "SQUARE_MARKETING_IMAGE"}
        if field_type is not None and field_type.upper() not in valid_field_types:
            return {
                "error": True,
                "message": f"Invalid field_type '{field_type}'. Must be one of: {', '.join(sorted(valid_field_types))}",
            }

        client = get_client()
        query = """
            SELECT
                campaign_asset.resource_name,
                campaign_asset.field_type,
                campaign_asset.status,
                asset.id,
                asset.name,
                asset.type,
                asset.final_urls,
                asset.sitelink_asset.description1,
                asset.sitelink_asset.description2,
                asset.sitelink_asset.link_text,
                asset.callout_asset.callout_text,
                asset.structured_snippet_asset.header,
                asset.structured_snippet_asset.values,
                campaign.id,
                campaign.name
            FROM campaign_asset
        """
        conditions = []
        if campaign_id is not None:
            conditions.append(f"campaign.id = {campaign_id}")
        if field_type is not None:
            conditions.append(f"campaign_asset.field_type = '{field_type.upper()}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            ca = row.get("campaign_asset", {})
            asset = row.get("asset", {})
            campaign = row.get("campaign", {})
            entry = {
                "resource_name": ca.get("resource_name"),
                "field_type": ca.get("field_type"),
                "status": ca.get("status"),
                "asset_id": asset.get("id"),
                "asset_name": asset.get("name"),
                "asset_type": asset.get("type"),
                "campaign_id": campaign.get("id"),
                "campaign_name": campaign.get("name"),
            }
            # Include type-specific fields (flattened for CSV)
            sitelink = asset.get("sitelink_asset", {})
            if sitelink:
                entry["sitelink_link_text"] = sitelink.get("link_text")
                entry["sitelink_description1"] = sitelink.get("description1")
                entry["sitelink_description2"] = sitelink.get("description2")
                entry["sitelink_final_urls"] = "|".join(asset.get("final_urls", []))
            callout = asset.get("callout_asset", {})
            if callout:
                entry["callout_text"] = callout.get("callout_text")
            snippet = asset.get("structured_snippet_asset", {})
            if snippet:
                entry["snippet_header"] = snippet.get("header")
                entry["snippet_values"] = "|".join(snippet.get("values", []))
            results.append(entry)

        # Normalize all rows to have the same keys (different extension types
        # produce different columns; DictWriter needs a consistent schema).
        if results:
            all_keys = list(dict.fromkeys(k for row in results for k in row))
            results = [{k: row.get(k) for k in all_keys} for row in results]

        # Build summary: count by field_type
        type_counts: dict[str, int] = {}
        for r in results:
            ft = r.get("field_type") or "UNKNOWN"
            type_counts[ft] = type_counts.get(ft, 0) + 1

        report = save_report(results, "extensions")
        if report.get("error"):
            return report
        report["summary"] = {
            "total_extensions": len(results),
            "count_by_field_type": type_counts,
        }
        return report

    @mcp.tool
    @handle_google_ads_errors
    def create_sitelink(
        campaign_id: Annotated[str, Field(description="Campaign ID to link the sitelink to")],
        link_text: Annotated[str, Field(description="Sitelink display text (max 25 characters)")],
        final_url: Annotated[str, Field(description="Landing page URL for the sitelink")],
        description1: Annotated[str | None, Field(description="First description line (max 35 characters)")] = None,
        description2: Annotated[str | None, Field(description="Second description line (max 35 characters)")] = None,
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Create a sitelink extension asset and link it to a campaign."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        asset_service = client.get_service("AssetService")
        campaign_asset_service = client.get_service("CampaignAssetService")

        # Step 1: Create the sitelink asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.sitelink_asset.link_text = link_text
        asset.final_urls.append(final_url)
        if description1 is not None:
            asset.sitelink_asset.description1 = description1
        if description2 is not None:
            asset.sitelink_asset.description2 = description2

        asset_response = asset_service.mutate_assets(
            customer_id=customer_id, operations=[asset_operation]
        )
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign
        campaign_asset_operation = client.get_type("CampaignAssetOperation")
        campaign_asset = campaign_asset_operation.create
        campaign_asset.campaign = client.get_service("CampaignService").campaign_path(
            customer_id, campaign_id
        )
        campaign_asset.asset = asset_resource_name
        campaign_asset.field_type = client.enums.AssetFieldTypeEnum.SITELINK

        campaign_asset_response = campaign_asset_service.mutate_campaign_assets(
            customer_id=customer_id, operations=[campaign_asset_operation]
        )
        campaign_asset_resource_name = campaign_asset_response.results[0].resource_name

        return {
            "asset_resource_name": asset_resource_name,
            "campaign_asset_resource_name": campaign_asset_resource_name,
            "link_text": link_text,
            "final_url": final_url,
            "campaign_id": campaign_id,
        }

    @mcp.tool
    @handle_google_ads_errors
    def create_callout(
        campaign_id: Annotated[str, Field(description="Campaign ID to link the callout to")],
        callout_text: Annotated[str, Field(description="Callout text (max 25 characters, e.g. 'Free Shipping')")],
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Create a callout extension asset and link it to a campaign."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        asset_service = client.get_service("AssetService")
        campaign_asset_service = client.get_service("CampaignAssetService")

        # Step 1: Create the callout asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.callout_asset.callout_text = callout_text

        asset_response = asset_service.mutate_assets(
            customer_id=customer_id, operations=[asset_operation]
        )
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign
        campaign_asset_operation = client.get_type("CampaignAssetOperation")
        campaign_asset = campaign_asset_operation.create
        campaign_asset.campaign = client.get_service("CampaignService").campaign_path(
            customer_id, campaign_id
        )
        campaign_asset.asset = asset_resource_name
        campaign_asset.field_type = client.enums.AssetFieldTypeEnum.CALLOUT

        campaign_asset_response = campaign_asset_service.mutate_campaign_assets(
            customer_id=customer_id, operations=[campaign_asset_operation]
        )
        campaign_asset_resource_name = campaign_asset_response.results[0].resource_name

        return {
            "asset_resource_name": asset_resource_name,
            "campaign_asset_resource_name": campaign_asset_resource_name,
            "callout_text": callout_text,
            "campaign_id": campaign_id,
        }

    @mcp.tool
    @handle_google_ads_errors
    def create_structured_snippet(
        campaign_id: Annotated[str, Field(description="Campaign ID to link the structured snippet to")],
        header: Annotated[str, Field(description="Snippet header (e.g. 'Types', 'Brands', 'Styles'). Must be a predefined Google Ads header value.")],
        values: Annotated[list[str], Field(description="List of snippet values (3-10 recommended, e.g. ['Type A', 'Type B'])")],
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Create a structured snippet extension asset and link it to a campaign."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        if not values:
            return {"error": True, "message": "At least one snippet value is required"}

        client = get_client()
        asset_service = client.get_service("AssetService")
        campaign_asset_service = client.get_service("CampaignAssetService")

        # Step 1: Create the structured snippet asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.structured_snippet_asset.header = header
        for value in values:
            asset.structured_snippet_asset.values.append(value)

        asset_response = asset_service.mutate_assets(
            customer_id=customer_id, operations=[asset_operation]
        )
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign
        campaign_asset_operation = client.get_type("CampaignAssetOperation")
        campaign_asset = campaign_asset_operation.create
        campaign_asset.campaign = client.get_service("CampaignService").campaign_path(
            customer_id, campaign_id
        )
        campaign_asset.asset = asset_resource_name
        campaign_asset.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET

        campaign_asset_response = campaign_asset_service.mutate_campaign_assets(
            customer_id=customer_id, operations=[campaign_asset_operation]
        )
        campaign_asset_resource_name = campaign_asset_response.results[0].resource_name

        return {
            "asset_resource_name": asset_resource_name,
            "campaign_asset_resource_name": campaign_asset_resource_name,
            "header": header,
            "values": values,
            "campaign_id": campaign_id,
        }

    @mcp.tool
    @handle_google_ads_errors
    def create_image_extension(
        campaign_id: Annotated[str, Field(description="Campaign ID to link the image extension to")],
        image_url: Annotated[str, Field(description="Public URL of the image to upload (must be square 1:1 ratio, min 300x300px)")],
        asset_name: Annotated[str | None, Field(description="Optional name for the image asset")] = None,
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Create an image extension asset from a URL and link it to a campaign. Image must be square (1:1 ratio), minimum 300x300 pixels."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        import requests

        # Download the image
        try:
            resp = requests.get(image_url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            image_data = resp.content
        except Exception as e:
            return {"error": True, "message": f"Failed to download image: {e}"}

        client = get_client()
        asset_service = client.get_service("AssetService")
        campaign_asset_service = client.get_service("CampaignAssetService")

        # Step 1: Create the image asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.type_ = client.enums.AssetTypeEnum.IMAGE
        asset.image_asset.data = image_data
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        mime_map = {
            "image/jpeg": client.enums.MimeTypeEnum.IMAGE_JPEG,
            "image/png": client.enums.MimeTypeEnum.IMAGE_PNG,
            "image/gif": client.enums.MimeTypeEnum.IMAGE_GIF,
        }
        asset.image_asset.mime_type = mime_map.get(content_type, client.enums.MimeTypeEnum.IMAGE_JPEG)
        if asset_name:
            asset.name = asset_name

        asset_response = asset_service.mutate_assets(
            customer_id=customer_id, operations=[asset_operation]
        )
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign as an image extension
        campaign_asset_operation = client.get_type("CampaignAssetOperation")
        campaign_asset = campaign_asset_operation.create
        campaign_asset.campaign = client.get_service("CampaignService").campaign_path(
            customer_id, campaign_id
        )
        campaign_asset.asset = asset_resource_name
        campaign_asset.field_type = client.enums.AssetFieldTypeEnum.SQUARE_MARKETING_IMAGE

        campaign_asset_response = campaign_asset_service.mutate_campaign_assets(
            customer_id=customer_id, operations=[campaign_asset_operation]
        )
        campaign_asset_resource_name = campaign_asset_response.results[0].resource_name

        return {
            "asset_resource_name": asset_resource_name,
            "campaign_asset_resource_name": campaign_asset_resource_name,
            "image_size_bytes": len(image_data),
            "campaign_id": campaign_id,
        }

    @mcp.tool
    @handle_google_ads_errors
    def remove_extension(
        campaign_asset_resource_name: Annotated[str, Field(description="Full resource name of the campaign asset link to remove (e.g. 'customers/123/campaignAssets/456~789~SITELINK')")],
        confirm: Annotated[bool, Field(description="Must be true to execute the removal.")] = False,
        customer_id: Annotated[str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")] = None,
    ) -> dict:
        """Remove an extension link from a campaign. Requires confirm=true for safety. This removes the link between the asset and campaign, not the asset itself."""
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            return {"error": True, "message": "No customer_id provided and no active account set. Call set_active_account first."}
        if err := validate_id(customer_id, "customer_id"):
            return {"error": True, "message": err}
        if not confirm:
            return {
                "warning": f"This will remove the extension link '{campaign_asset_resource_name}' from the campaign. "
                "The underlying asset will not be deleted. "
                "Set confirm=true to execute."
            }

        client = get_client()
        campaign_asset_service = client.get_service("CampaignAssetService")

        operation = client.get_type("CampaignAssetOperation")
        operation.remove = campaign_asset_resource_name

        response = campaign_asset_service.mutate_campaign_assets(
            customer_id=customer_id, operations=[operation]
        )
        return {
            "removed_resource_name": response.results[0].resource_name,
        }
