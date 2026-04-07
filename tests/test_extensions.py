"""Tests for burnr8.tools.extensions — campaign and ad group level asset linking."""

from burnr8.session import set_active_account

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_tool(name):
    """Register extension tools and return the one matching *name*."""
    from burnr8.tools.extensions import register

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    register(cap)
    return captured["func"]


def _campaign_asset_row(field_type="SITELINK", asset_id="800", campaign_id="222"):
    return {
        "campaign_asset": {
            "resource_name": f"customers/1234567890/campaignAssets/{campaign_id}~{asset_id}~{field_type}",
            "field_type": field_type,
            "status": "ENABLED",
        },
        "asset": {
            "id": asset_id,
            "name": "Test Asset",
            "type": field_type,
            "final_urls": ["https://example.com"],
            "sitelink_asset": {"link_text": "Click", "description1": "Desc1", "description2": "Desc2"},
            "callout_asset": {"callout_text": "Free Shipping"},
            "structured_snippet_asset": {"header": "Types", "values": ["A", "B"]},
        },
        "campaign": {"id": campaign_id, "name": "Campaign A"},
    }


def _ad_group_asset_row(field_type="SITELINK", asset_id="801", ad_group_id="333"):
    return {
        "ad_group_asset": {
            "resource_name": f"customers/1234567890/adGroupAssets/{ad_group_id}~{asset_id}~{field_type}",
            "field_type": field_type,
            "status": "ENABLED",
        },
        "asset": {
            "id": asset_id,
            "name": "AG Asset",
            "type": field_type,
            "final_urls": ["https://example.com"],
            "sitelink_asset": {"link_text": "AG Click", "description1": "D1", "description2": "D2"},
            "callout_asset": {"callout_text": "AG Callout"},
            "structured_snippet_asset": {"header": "Brands", "values": ["X"]},
        },
        "ad_group": {"id": ad_group_id, "name": "Ad Group A"},
    }


# ---------------------------------------------------------------------------
# _validate_link_target (via create tools)
# ---------------------------------------------------------------------------


class TestValidateLinkTarget:
    def test_both_ids_returns_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(link_text="Click", final_url="https://example.com", campaign_id="222", ad_group_id="333")
        assert result["error"] is True
        assert "not both" in result["message"]

    def test_neither_id_returns_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(link_text="Click", final_url="https://example.com")
        assert result["error"] is True
        assert "required" in result["message"]


# ---------------------------------------------------------------------------
# list_extensions
# ---------------------------------------------------------------------------


class TestListExtensions:
    def test_campaign_only(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM campaign_asset": [_campaign_asset_row()]})
        fn = _register_tool("list_extensions")
        result = fn(campaign_id="222")
        assert result["summary"]["total_extensions"] == 1
        assert result["top"][0]["level"] == "campaign"
        assert result["top"][0]["campaign_id"] == "222"

    def test_ad_group_only(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM ad_group_asset": [_ad_group_asset_row()]})
        fn = _register_tool("list_extensions")
        result = fn(ad_group_id="333")
        assert result["summary"]["total_extensions"] == 1
        assert result["top"][0]["level"] == "ad_group"
        assert result["top"][0]["ad_group_id"] == "333"

    def test_both_levels_when_no_filter(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({
            "FROM campaign_asset": [_campaign_asset_row()],
            "FROM ad_group_asset": [_ad_group_asset_row()],
        })
        fn = _register_tool("list_extensions")
        result = fn()
        assert result["summary"]["total_extensions"] == 2
        levels = {r["level"] for r in result["top"]}
        assert levels == {"campaign", "ad_group"}

    def test_field_type_filter(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM campaign_asset": [_campaign_asset_row(field_type="CALLOUT")]})
        fn = _register_tool("list_extensions")
        result = fn(campaign_id="222", field_type="CALLOUT")
        assert result["summary"]["total_extensions"] == 1

    def test_invalid_field_type(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("list_extensions")
        result = fn(field_type="BANANA")
        assert result["error"] is True
        assert "BANANA" in result["message"]

    def test_invalid_ad_group_id(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("list_extensions")
        result = fn(ad_group_id="bad-id")
        assert result["error"] is True

    def test_no_customer_id(self):
        fn = _register_tool("list_extensions")
        result = fn()
        assert result["error"] is True
        assert "No customer_id" in result["message"]


# ---------------------------------------------------------------------------
# create_sitelink
# ---------------------------------------------------------------------------


class TestCreateSitelink:
    def test_campaign_level(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(link_text="Shop Now", final_url="https://shop.com", campaign_id="222")
        assert "asset_resource_name" in result
        assert "campaign_asset_resource_name" in result
        assert result["campaign_id"] == "222"
        assert "ad_group_id" not in result

    def test_ad_group_level(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(link_text="Shop Now", final_url="https://shop.com", ad_group_id="333")
        assert "asset_resource_name" in result
        assert "asset_link_resource_name" in result
        assert result["ad_group_id"] == "333"
        assert "campaign_asset_resource_name" not in result

    def test_with_descriptions(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(
            link_text="Shop", final_url="https://shop.com",
            description1="Desc 1", description2="Desc 2",
            campaign_id="222",
        )
        assert result["link_text"] == "Shop"
        assert result["final_url"] == "https://shop.com"

    def test_no_customer_id(self):
        fn = _register_tool("create_sitelink")
        result = fn(link_text="X", final_url="https://x.com", campaign_id="222")
        assert result["error"] is True


# ---------------------------------------------------------------------------
# create_callout
# ---------------------------------------------------------------------------


class TestCreateCallout:
    def test_campaign_level(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_callout")
        result = fn(callout_text="Free Shipping", campaign_id="222")
        assert result["callout_text"] == "Free Shipping"
        assert result["campaign_id"] == "222"
        assert "campaign_asset_resource_name" in result

    def test_ad_group_level(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_callout")
        result = fn(callout_text="Free Shipping", ad_group_id="333")
        assert result["ad_group_id"] == "333"
        assert "campaign_asset_resource_name" not in result

    def test_both_ids_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_callout")
        result = fn(callout_text="X", campaign_id="222", ad_group_id="333")
        assert result["error"] is True


# ---------------------------------------------------------------------------
# create_structured_snippet
# ---------------------------------------------------------------------------


class TestCreateStructuredSnippet:
    def test_campaign_level(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_structured_snippet")
        result = fn(header="Types", values=["A", "B"], campaign_id="222")
        assert result["header"] == "Types"
        assert result["values"] == ["A", "B"]
        assert result["campaign_id"] == "222"

    def test_ad_group_level(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_structured_snippet")
        result = fn(header="Brands", values=["X"], ad_group_id="333")
        assert result["ad_group_id"] == "333"
        assert "campaign_asset_resource_name" not in result

    def test_empty_values_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_structured_snippet")
        result = fn(header="Types", values=[], campaign_id="222")
        assert result["error"] is True
        assert "value" in result["message"].lower()

    def test_neither_id_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_structured_snippet")
        result = fn(header="Types", values=["A"])
        assert result["error"] is True


# ---------------------------------------------------------------------------
# create_image_extension (just validation, no actual HTTP)
# ---------------------------------------------------------------------------


class TestCreateImageExtension:
    def test_both_ids_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_image_extension")
        result = fn(image_url="https://img.com/pic.jpg", campaign_id="222", ad_group_id="333")
        assert result["error"] is True
        assert "not both" in result["message"]

    def test_neither_id_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_image_extension")
        result = fn(image_url="https://img.com/pic.jpg")
        assert result["error"] is True
        assert "required" in result["message"]

    def test_invalid_scheme(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_image_extension")
        result = fn(image_url="ftp://img.com/pic.jpg", campaign_id="222")
        assert result["error"] is True
        assert "http" in result["message"].lower()

    def test_no_customer_id(self):
        fn = _register_tool("create_image_extension")
        result = fn(image_url="https://img.com/pic.jpg", campaign_id="222")
        assert result["error"] is True


# ---------------------------------------------------------------------------
# remove_extension
# ---------------------------------------------------------------------------


class TestRemoveExtension:
    def test_campaign_asset_removal(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("remove_extension")
        result = fn(
            asset_resource_name="customers/1234567890/campaignAssets/222~800~SITELINK",
            confirm=True,
        )
        assert "removed_resource_name" in result

    def test_ad_group_asset_removal(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("remove_extension")
        result = fn(
            asset_resource_name="customers/1234567890/adGroupAssets/333~800~SITELINK",
            confirm=True,
        )
        assert "removed_resource_name" in result

    def test_confirm_false_returns_warning(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("remove_extension")
        result = fn(
            asset_resource_name="customers/1234567890/campaignAssets/222~800~SITELINK",
            confirm=False,
        )
        assert result["warning"] is True
        assert "confirm" in result["message"].lower()

    def test_no_customer_id(self):
        fn = _register_tool("remove_extension")
        result = fn(
            asset_resource_name="customers/1234567890/campaignAssets/222~800~SITELINK",
            confirm=True,
        )
        assert result["error"] is True


# ---------------------------------------------------------------------------
# _link_asset helper (via service calls)
# ---------------------------------------------------------------------------


class TestLinkAssetHelper:
    """Verify the correct Google Ads service is called based on campaign_id vs ad_group_id."""

    def test_campaign_link_uses_campaign_service(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_callout")
        fn(callout_text="Test", campaign_id="222")
        svc = mock_ads_client["client"].get_service("CampaignAssetService")
        svc.mutate_campaign_assets.assert_called_once()

    def test_ad_group_link_uses_ad_group_service(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_callout")
        fn(callout_text="Test", ad_group_id="333")
        svc = mock_ads_client["client"].get_service("AdGroupAssetService")
        svc.mutate_ad_group_assets.assert_called_once()

    def test_ad_group_remove_uses_ad_group_service(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("remove_extension")
        fn(asset_resource_name="customers/1234567890/adGroupAssets/333~800~SITELINK", confirm=True)
        svc = mock_ads_client["client"].get_service("AdGroupAssetService")
        svc.mutate_ad_group_assets.assert_called_once()

    def test_campaign_remove_uses_campaign_service(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("remove_extension")
        fn(asset_resource_name="customers/1234567890/campaignAssets/222~800~SITELINK", confirm=True)
        svc = mock_ads_client["client"].get_service("CampaignAssetService")
        svc.mutate_campaign_assets.assert_called_once()


# ---------------------------------------------------------------------------
# Review fixes: additional edge cases
# ---------------------------------------------------------------------------


class TestListExtensionsEdgeCases:
    def test_campaign_filter_does_not_run_ad_group_query(self, mock_ads_client):
        """When campaign_id is specified, ad group query should NOT run."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({
            "FROM campaign_asset": [_campaign_asset_row()],
            "FROM ad_group_asset": [_ad_group_asset_row()],
        })
        fn = _register_tool("list_extensions")
        result = fn(campaign_id="222")
        assert result["summary"]["total_extensions"] == 1
        assert all(r["level"] == "campaign" for r in result["top"])

    def test_ad_group_filter_does_not_run_campaign_query(self, mock_ads_client):
        """When ad_group_id is specified, campaign query should NOT run."""
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({
            "FROM campaign_asset": [_campaign_asset_row()],
            "FROM ad_group_asset": [_ad_group_asset_row()],
        })
        fn = _register_tool("list_extensions")
        result = fn(ad_group_id="333")
        assert result["summary"]["total_extensions"] == 1
        assert all(r["level"] == "ad_group" for r in result["top"])

    def test_empty_results(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})
        fn = _register_tool("list_extensions")
        result = fn()
        assert result["summary"]["total_extensions"] == 0
        assert result["summary"]["count_by_field_type"] == {}

    def test_field_type_filter_on_ad_group(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({"FROM ad_group_asset": [_ad_group_asset_row(field_type="CALLOUT")]})
        fn = _register_tool("list_extensions")
        result = fn(ad_group_id="333", field_type="CALLOUT")
        assert result["summary"]["total_extensions"] == 1


class TestRemoveExtensionEdgeCases:
    def test_malformed_resource_name_returns_error(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("remove_extension")
        result = fn(asset_resource_name="customers/123/unknownType/456", confirm=True)
        assert result["error"] is True
        assert "Unrecognized" in result["message"]


class TestCreateToolValidation:
    def test_invalid_ad_group_id_on_create_sitelink(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(link_text="X", final_url="https://x.com", ad_group_id="not-numeric")
        assert result["error"] is True

    def test_ad_group_sitelink_resource_name_value(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(link_text="Shop", final_url="https://shop.com", ad_group_id="333")
        assert result["asset_link_resource_name"] == "customers/1234567890/adGroupAssets/333~800"

    def test_falsy_campaign_id_not_treated_as_missing(self, mock_ads_client):
        """campaign_id='0' is falsy but valid — must not trigger 'required' error."""
        set_active_account("1234567890")
        fn = _register_tool("create_sitelink")
        result = fn(link_text="X", final_url="https://x.com", campaign_id="0")
        # Should NOT get "Either campaign_id or ad_group_id is required"
        assert result.get("message", "") != "Either campaign_id or ad_group_id is required."
