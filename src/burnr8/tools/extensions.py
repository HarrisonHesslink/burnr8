from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import require_customer_id, run_gaql, validate_id
from burnr8.reports import save_report


def register(mcp: FastMCP) -> None:
    def _validate_link_target(campaign_id, ad_group_id):
        """Validate exactly one of campaign_id/ad_group_id is provided."""
        if campaign_id is not None and ad_group_id is not None:
            return "Provide either campaign_id or ad_group_id, not both."
        if campaign_id is None and ad_group_id is None:
            return "Either campaign_id or ad_group_id is required."
        return None

    def _link_asset(client, customer_id, asset_resource_name, field_type_enum, campaign_id=None, ad_group_id=None):
        """Link an asset to a campaign or ad group. Returns the resource name."""
        if campaign_id is None and ad_group_id is None:
            raise ValueError("_link_asset requires either campaign_id or ad_group_id")
        if campaign_id is not None:
            op = client.get_type("CampaignAssetOperation")
            link = op.create
            link.campaign = client.get_service("CampaignService").campaign_path(customer_id, campaign_id)
            link.asset = asset_resource_name
            link.field_type = field_type_enum
            svc = client.get_service("CampaignAssetService")
            resp = svc.mutate_campaign_assets(customer_id=customer_id, operations=[op])
        else:
            op = client.get_type("AdGroupAssetOperation")
            link = op.create
            link.ad_group = client.get_service("AdGroupService").ad_group_path(customer_id, ad_group_id)
            link.asset = asset_resource_name
            link.field_type = field_type_enum
            svc = client.get_service("AdGroupAssetService")
            resp = svc.mutate_ad_group_assets(customer_id=customer_id, operations=[op])
        return resp.results[0].resource_name

    @mcp.tool
    @handle_google_ads_errors
    def list_extensions(
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
        campaign_id: Annotated[
            str | None,
            Field(
                description="Campaign ID to filter by. If omitted with no ad_group_id, lists all extensions in the account."
            ),
        ] = None,
        ad_group_id: Annotated[
            str | None,
            Field(
                description="Ad group ID to filter by. If omitted with no campaign_id, lists all extensions in the account."
            ),
        ] = None,
        field_type: Annotated[
            str | None,
            Field(
                description="Filter by extension type: SITELINK, CALLOUT, STRUCTURED_SNIPPET, or SQUARE_MARKETING_IMAGE"
            ),
        ] = None,
    ) -> dict:
        """List all asset-based extensions (sitelinks, callouts, structured snippets, images) linked to campaigns and/or ad groups. Saves full results to CSV, returns summary + top rows."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if ad_group_id is not None and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}

        valid_field_types = {"SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "SQUARE_MARKETING_IMAGE"}
        if field_type is not None and field_type.upper() not in valid_field_types:
            return {
                "error": True,
                "message": f"Invalid field_type '{field_type}'. Must be one of: {', '.join(sorted(valid_field_types))}",
            }

        client = get_client()

        # Determine which queries to run based on parameters
        no_filter = campaign_id is None and ad_group_id is None
        run_campaign_query = campaign_id is not None or no_filter
        run_ad_group_query = ad_group_id is not None or no_filter

        results = []

        if run_campaign_query:
            campaign_query = """
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
                campaign_query += " WHERE " + " AND ".join(conditions)

            for row in run_gaql(client, customer_id, campaign_query):
                ca = row.get("campaign_asset", {})
                asset = row.get("asset", {})
                campaign = row.get("campaign", {})
                entry = {
                    "level": "campaign",
                    "resource_name": ca.get("resource_name"),
                    "field_type": ca.get("field_type"),
                    "status": ca.get("status"),
                    "asset_id": asset.get("id"),
                    "asset_name": asset.get("name"),
                    "asset_type": asset.get("type"),
                    "campaign_id": campaign.get("id"),
                    "campaign_name": campaign.get("name"),
                }
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

        if run_ad_group_query:
            ad_group_query = """
                SELECT
                    ad_group_asset.resource_name,
                    ad_group_asset.field_type,
                    ad_group_asset.status,
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
                    ad_group.id,
                    ad_group.name
                FROM ad_group_asset
            """
            ag_conditions = []
            if ad_group_id is not None:
                ag_conditions.append(f"ad_group.id = {ad_group_id}")
            if field_type is not None:
                ag_conditions.append(f"ad_group_asset.field_type = '{field_type.upper()}'")
            if ag_conditions:
                ad_group_query += " WHERE " + " AND ".join(ag_conditions)

            for row in run_gaql(client, customer_id, ad_group_query):
                aga = row.get("ad_group_asset", {})
                asset = row.get("asset", {})
                ad_group = row.get("ad_group", {})
                entry = {
                    "level": "ad_group",
                    "resource_name": aga.get("resource_name"),
                    "field_type": aga.get("field_type"),
                    "status": aga.get("status"),
                    "asset_id": asset.get("id"),
                    "asset_name": asset.get("name"),
                    "asset_type": asset.get("type"),
                    "ad_group_id": ad_group.get("id"),
                    "ad_group_name": ad_group.get("name"),
                }
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
        link_text: Annotated[str, Field(description="Sitelink display text (max 25 characters)")],
        final_url: Annotated[str, Field(description="Landing page URL for the sitelink")],
        description1: Annotated[str | None, Field(description="First description line (max 35 characters)")] = None,
        description2: Annotated[str | None, Field(description="Second description line (max 35 characters)")] = None,
        campaign_id: Annotated[
            str | None, Field(description="Campaign ID to link to. Provide either this or ad_group_id.")
        ] = None,
        ad_group_id: Annotated[
            str | None, Field(description="Ad group ID to link to. Provide either this or campaign_id.")
        ] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create a sitelink extension asset and link it to a campaign or ad group."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := _validate_link_target(campaign_id, ad_group_id):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if ad_group_id is not None and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}

        client = get_client()
        asset_service = client.get_service("AssetService")

        # Step 1: Create the sitelink asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.sitelink_asset.link_text = link_text
        asset.final_urls.append(final_url)
        if description1 is not None:
            asset.sitelink_asset.description1 = description1
        if description2 is not None:
            asset.sitelink_asset.description2 = description2

        asset_response = asset_service.mutate_assets(customer_id=customer_id, operations=[asset_operation])
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign or ad group
        link_resource_name = _link_asset(
            client,
            customer_id,
            asset_resource_name,
            client.enums.AssetFieldTypeEnum.SITELINK,
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
        )

        result = {
            "asset_resource_name": asset_resource_name,
            "asset_link_resource_name": link_resource_name,
            "link_text": link_text,
            "final_url": final_url,
        }
        if campaign_id is not None:
            result["campaign_id"] = campaign_id
            result["campaign_asset_resource_name"] = link_resource_name
        if ad_group_id is not None:
            result["ad_group_id"] = ad_group_id
        return result

    @mcp.tool
    @handle_google_ads_errors
    def create_callout(
        callout_text: Annotated[str, Field(description="Callout text (max 25 characters, e.g. 'Free Shipping')")],
        campaign_id: Annotated[
            str | None, Field(description="Campaign ID to link to. Provide either this or ad_group_id.")
        ] = None,
        ad_group_id: Annotated[
            str | None, Field(description="Ad group ID to link to. Provide either this or campaign_id.")
        ] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create a callout extension asset and link it to a campaign or ad group."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := _validate_link_target(campaign_id, ad_group_id):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if ad_group_id is not None and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}

        client = get_client()
        asset_service = client.get_service("AssetService")

        # Step 1: Create the callout asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.callout_asset.callout_text = callout_text

        asset_response = asset_service.mutate_assets(customer_id=customer_id, operations=[asset_operation])
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign or ad group
        link_resource_name = _link_asset(
            client,
            customer_id,
            asset_resource_name,
            client.enums.AssetFieldTypeEnum.CALLOUT,
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
        )

        result = {
            "asset_resource_name": asset_resource_name,
            "asset_link_resource_name": link_resource_name,
            "callout_text": callout_text,
        }
        if campaign_id is not None:
            result["campaign_id"] = campaign_id
            result["campaign_asset_resource_name"] = link_resource_name
        if ad_group_id is not None:
            result["ad_group_id"] = ad_group_id
        return result

    @mcp.tool
    @handle_google_ads_errors
    def create_structured_snippet(
        header: Annotated[
            str,
            Field(
                description="Snippet header (e.g. 'Types', 'Brands', 'Styles'). Must be a predefined Google Ads header value."
            ),
        ],
        values: Annotated[
            list[str], Field(description="List of snippet values (3-10 recommended, e.g. ['Type A', 'Type B'])")
        ],
        campaign_id: Annotated[
            str | None, Field(description="Campaign ID to link to. Provide either this or ad_group_id.")
        ] = None,
        ad_group_id: Annotated[
            str | None, Field(description="Ad group ID to link to. Provide either this or campaign_id.")
        ] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create a structured snippet extension asset and link it to a campaign or ad group."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := _validate_link_target(campaign_id, ad_group_id):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if ad_group_id is not None and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}
        if not values:
            return {"error": True, "message": "At least one snippet value is required"}

        client = get_client()
        asset_service = client.get_service("AssetService")

        # Step 1: Create the structured snippet asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.structured_snippet_asset.header = header
        for value in values:
            asset.structured_snippet_asset.values.append(value)

        asset_response = asset_service.mutate_assets(customer_id=customer_id, operations=[asset_operation])
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign or ad group
        link_resource_name = _link_asset(
            client,
            customer_id,
            asset_resource_name,
            client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET,
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
        )

        result = {
            "asset_resource_name": asset_resource_name,
            "asset_link_resource_name": link_resource_name,
            "header": header,
            "values": values,
        }
        if campaign_id is not None:
            result["campaign_id"] = campaign_id
            result["campaign_asset_resource_name"] = link_resource_name
        if ad_group_id is not None:
            result["ad_group_id"] = ad_group_id
        return result

    @mcp.tool
    @handle_google_ads_errors
    def create_image_extension(
        image_url: Annotated[
            str, Field(description="Public URL of the image to upload (must be square 1:1 ratio, min 300x300px)")
        ],
        asset_name: Annotated[str | None, Field(description="Optional name for the image asset")] = None,
        campaign_id: Annotated[
            str | None, Field(description="Campaign ID to link to. Provide either this or ad_group_id.")
        ] = None,
        ad_group_id: Annotated[
            str | None, Field(description="Ad group ID to link to. Provide either this or campaign_id.")
        ] = None,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Create an image extension asset from a URL and link it to a campaign or ad group. Image must be square (1:1 ratio), minimum 300x300 pixels."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := _validate_link_target(campaign_id, ad_group_id):
            return {"error": True, "message": err}
        if campaign_id is not None and (err := validate_id(campaign_id, "campaign_id")):
            return {"error": True, "message": err}
        if ad_group_id is not None and (err := validate_id(ad_group_id, "ad_group_id")):
            return {"error": True, "message": err}

        import ipaddress
        import socket
        from urllib.parse import urlparse

        import requests

        MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

        # Validate image_url to prevent SSRF
        parsed = urlparse(image_url)
        if parsed.scheme not in ("http", "https"):
            return {"error": True, "message": f"image_url must use http or https, got: {parsed.scheme!r}"}
        hostname = parsed.hostname
        if not hostname:
            return {"error": True, "message": "image_url has no hostname"}
        try:
            resolved_ip = socket.gethostbyname(hostname)
        except (socket.gaierror, ValueError):
            return {"error": True, "message": "image_url hostname could not be resolved"}
        if ipaddress.ip_address(resolved_ip).is_private:
            return {"error": True, "message": f"URL resolves to private IP ({resolved_ip})"}

        # Download the image (no redirects — prevent redirect-based SSRF bypass)
        # Note: DNS rebinding TOCTOU window is narrow and mitigated by allow_redirects=False.
        # We don't replace the hostname with the IP because that breaks HTTPS (TLS/SNI mismatch).
        try:
            resp = requests.get(image_url, timeout=30, allow_redirects=False, stream=True)
            resp.raise_for_status()

            # Check Content-Length header first
            content_length = resp.headers.get("Content-Length")
            try:
                cl = int(content_length) if content_length else 0
            except ValueError:
                cl = 0  # Malformed header; stream cap will enforce limit
            if cl > MAX_IMAGE_SIZE:
                resp.close()
                return {
                    "error": True,
                    "message": f"Image too large ({cl} bytes, max {MAX_IMAGE_SIZE})",
                }

            # Stream with hard cap
            chunks = []
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded > MAX_IMAGE_SIZE:
                    resp.close()
                    return {
                        "error": True,
                        "message": f"Image too large (>{MAX_IMAGE_SIZE // 1024 // 1024} MB)",
                    }
                chunks.append(chunk)
            image_data = b"".join(chunks)
        except requests.exceptions.HTTPError as e:
            return {"error": True, "message": f"Failed to download image: HTTP {e.response.status_code}"}
        except (requests.RequestException, OSError):
            return {"error": True, "message": "Failed to download image (network error)"}

        client = get_client()
        asset_service = client.get_service("AssetService")

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

        asset_response = asset_service.mutate_assets(customer_id=customer_id, operations=[asset_operation])
        asset_resource_name = asset_response.results[0].resource_name

        # Step 2: Link the asset to the campaign or ad group
        link_resource_name = _link_asset(
            client,
            customer_id,
            asset_resource_name,
            client.enums.AssetFieldTypeEnum.SQUARE_MARKETING_IMAGE,
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
        )

        result = {
            "asset_resource_name": asset_resource_name,
            "asset_link_resource_name": link_resource_name,
            "image_size_bytes": len(image_data),
        }
        if campaign_id is not None:
            result["campaign_id"] = campaign_id
            result["campaign_asset_resource_name"] = link_resource_name
        if ad_group_id is not None:
            result["ad_group_id"] = ad_group_id
        return result

    @mcp.tool
    @handle_google_ads_errors
    def remove_extension(
        asset_resource_name: Annotated[
            str,
            Field(
                description="Full resource name of the asset link to remove (e.g. 'customers/123/campaignAssets/456~789~SITELINK' or 'customers/123/adGroupAssets/456~789~SITELINK')"
            ),
        ],
        confirm: Annotated[bool, Field(description="Must be true to execute the removal.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Remove an extension link from a campaign or ad group. Requires confirm=true for safety. This removes the link between the asset and the campaign/ad group, not the asset itself."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if not confirm:
            return {
                "warning": True,
                "message": f"This will remove the extension link '{asset_resource_name}'. "
                "The underlying asset will not be deleted. "
                "Set confirm=true to execute.",
            }

        client = get_client()

        # Auto-detect whether this is a campaign or ad group asset link
        if "adGroupAssets" in asset_resource_name:
            operation = client.get_type("AdGroupAssetOperation")
            operation.remove = asset_resource_name
            svc = client.get_service("AdGroupAssetService")
            response = svc.mutate_ad_group_assets(customer_id=customer_id, operations=[operation])
        elif "campaignAssets" in asset_resource_name:
            operation = client.get_type("CampaignAssetOperation")
            operation.remove = asset_resource_name
            svc = client.get_service("CampaignAssetService")
            response = svc.mutate_campaign_assets(customer_id=customer_id, operations=[operation])
        else:
            return {
                "error": True,
                "message": f"Unrecognized asset link resource name: '{asset_resource_name}'. "
                "Expected format: 'customers/{{id}}/campaignAssets/...' or 'customers/{{id}}/adGroupAssets/...'",
            }

        return {
            "removed_resource_name": response.results[0].resource_name,
        }
