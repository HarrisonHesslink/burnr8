"""Tests for burnr8.tools.ads — list_ads, create_responsive_search_ad, set_ad_status."""

from burnr8.session import set_active_account

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_tool(name):
    """Register ad tools and return the one matching *name*."""
    from burnr8.tools.ads import register

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
# create_responsive_search_ad — tracking URL proto verification
# ---------------------------------------------------------------------------


class TestCreateResponsiveSearchAd:
    def test_basic_creation(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        fn = _register_tool("create_responsive_search_ad")
        result = fn(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["headlines_count"] == 3
        assert result["descriptions_count"] == 2
        client.get_service("AdGroupAdService").mutate_ad_group_ads.assert_called_once()

    def test_create_with_tracking_url_template(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        fn = _register_tool("create_responsive_search_ad")
        result = fn(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            tracking_url_template="{lpurl}?utm_source=google",
            final_url_suffix="utm_medium=cpc",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["tracking_url_template"] == "{lpurl}?utm_source=google"
        assert result["final_url_suffix"] == "utm_medium=cpc"
        # Verify proto fields were actually set
        call_args = client.get_service("AdGroupAdService").mutate_ad_group_ads.call_args
        operation = call_args.kwargs["request"].operations
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert op.create.ad.tracking_url_template == "{lpurl}?utm_source=google"
            assert op.create.ad.final_url_suffix == "utm_medium=cpc"

    def test_create_with_url_custom_parameters(self, mock_ads_client):
        set_active_account("1234567890")
        client = mock_ads_client["client"]

        fn = _register_tool("create_responsive_search_ad")
        result = fn(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            url_custom_parameters={"season": "winter", "promo": "sale"},
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["url_custom_parameters"] == {"season": "winter", "promo": "sale"}
        # Verify url_custom_parameters list was populated with 2 items (real list from conftest)
        call_args = client.get_service("AdGroupAdService").mutate_ad_group_ads.call_args
        operation = call_args.kwargs["request"].operations
        if operation and not isinstance(operation, list):
            operation = [operation]
        if operation:
            op = operation[0]
            assert len(op.create.ad.url_custom_parameters) == 2
            for param in op.create.ad.url_custom_parameters:
                assert hasattr(param, "key")
                assert hasattr(param, "value")

    def test_no_customer_id(self):
        fn = _register_tool("create_responsive_search_ad")
        result = fn(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
        )
        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_invalid_ad_group_id(self, mock_ads_client):
        set_active_account("1234567890")
        fn = _register_tool("create_responsive_search_ad")
        result = fn(
            ad_group_id="bad-id",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
        )
        assert result["error"] is True
