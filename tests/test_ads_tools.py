"""Tests for burnr8.tools.ads — list_ads, create_responsive_search_ad, set_ad_status."""

from burnr8.session import set_active_account
from burnr8.tools.ads import _DESCRIPTION_PIN_MAP, _HEADLINE_PIN_MAP

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_tool(name):
    """Register ads tools and return the one matching *name*."""
    from burnr8.tools.ads import register

    captured = {}

    class _Capture:
        def tool(self, fn):
            if fn.__name__ == name:
                captured["func"] = fn
            return fn

    cap = _Capture()
    register(cap)
    return captured["func"]


def _ad_row(
    ad_id="555",
    ad_type="RESPONSIVE_SEARCH_AD",
    headlines=None,
    descriptions=None,
    path1=None,
    path2=None,
    ad_strength="GOOD",
    status="ENABLED",
    approval_status="APPROVED",
    policy_topic_entries=None,
    ad_group_id="333",
    ad_group_name="My Ad Group",
    campaign_id="222",
    campaign_name="My Campaign",
    impressions=1000,
    clicks=50,
    cost_micros=25_000_000,
    conversions=5.0,
):
    if headlines is None:
        headlines = [{"text": "Headline 1"}, {"text": "Headline 2"}, {"text": "Headline 3"}]
    if descriptions is None:
        descriptions = [{"text": "Description 1"}, {"text": "Description 2"}]
    if policy_topic_entries is None:
        policy_topic_entries = []

    rsa = {
        "headlines": headlines,
        "descriptions": descriptions,
    }
    if path1 is not None:
        rsa["path1"] = path1
    if path2 is not None:
        rsa["path2"] = path2

    policy_summary = {"approval_status": approval_status}
    if policy_topic_entries:
        policy_summary["policy_topic_entries"] = policy_topic_entries

    return {
        "ad_group_ad": {
            "ad": {
                "id": ad_id,
                "type": ad_type,
                "final_urls": ["https://example.com"],
                "responsive_search_ad": rsa,
            },
            "ad_strength": ad_strength,
            "status": status,
            "policy_summary": policy_summary,
        },
        "ad_group": {"id": ad_group_id, "name": ad_group_name},
        "campaign": {"id": campaign_id, "name": campaign_name},
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "conversions": conversions,
        },
    }


# ---------------------------------------------------------------------------
# Pin maps
# ---------------------------------------------------------------------------


class TestPinMaps:
    def test_headline_pin_map_values(self):
        assert _HEADLINE_PIN_MAP == {1: "HEADLINE_1", 2: "HEADLINE_2", 3: "HEADLINE_3"}

    def test_description_pin_map_values(self):
        assert _DESCRIPTION_PIN_MAP == {1: "DESCRIPTION_1", 2: "DESCRIPTION_2"}


# ---------------------------------------------------------------------------
# list_ads
# ---------------------------------------------------------------------------


class TestListAds:
    def test_returns_structured_headlines(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM ad_group_ad": [
                    _ad_row(
                        headlines=[
                            {"text": "H1", "pinned_field": "HEADLINE_1"},
                            {"text": "H2"},
                            {"text": "H3", "pinned_field": "HEADLINE_3"},
                        ],
                        descriptions=[
                            {"text": "D1", "pinned_field": "DESCRIPTION_1"},
                            {"text": "D2"},
                        ],
                    ),
                ],
            }
        )

        tool = _register_tool("list_ads")
        result = tool(customer_id="1234567890")

        top = result["top"]
        assert len(top) == 1
        ad = top[0]
        # Structured headline data
        assert ad["headlines"] == [
            {"text": "H1", "pinned": "HEADLINE_1"},
            {"text": "H2", "pinned": None},
            {"text": "H3", "pinned": "HEADLINE_3"},
        ]
        assert ad["descriptions"] == [
            {"text": "D1", "pinned": "DESCRIPTION_1"},
            {"text": "D2", "pinned": None},
        ]

    def test_returns_display_paths(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM ad_group_ad": [
                    _ad_row(path1="shoes", path2="running"),
                ],
            }
        )

        tool = _register_tool("list_ads")
        result = tool(customer_id="1234567890")

        ad = result["top"][0]
        assert ad["path1"] == "shoes"
        assert ad["path2"] == "running"

    def test_returns_policy_topics(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM ad_group_ad": [
                    _ad_row(
                        policy_topic_entries=[
                            {"topic": "HEALTHCARE", "type": "RESTRICTED"},
                            {"topic": "ALCOHOL", "type": "PROHIBITED"},
                        ],
                    ),
                ],
            }
        )

        tool = _register_tool("list_ads")
        result = tool(customer_id="1234567890")

        ad = result["top"][0]
        assert ad["policy_topics"] == [
            {"topic": "HEALTHCARE", "type": "RESTRICTED"},
            {"topic": "ALCOHOL", "type": "PROHIBITED"},
        ]

    def test_empty_policy_topics(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM ad_group_ad": [_ad_row()],
            }
        )

        tool = _register_tool("list_ads")
        result = tool(customer_id="1234567890")

        ad = result["top"][0]
        assert ad["policy_topics"] == []

    def test_summary_counts(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM ad_group_ad": [
                    _ad_row(ad_strength="GOOD", approval_status="APPROVED"),
                    _ad_row(ad_id="556", ad_strength="POOR", approval_status="APPROVED_LIMITED"),
                ],
            }
        )

        tool = _register_tool("list_ads")
        result = tool(customer_id="1234567890")

        assert result["summary"]["total_ads"] == 2
        assert result["summary"]["ad_strength_distribution"]["GOOD"] == 1
        assert result["summary"]["ad_strength_distribution"]["POOR"] == 1
        assert result["summary"]["approval_status_counts"]["APPROVED"] == 1
        assert result["summary"]["approval_status_counts"]["APPROVED_LIMITED"] == 1

    def test_no_ads_returns_empty(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"]({})

        tool = _register_tool("list_ads")
        result = tool(customer_id="1234567890")

        assert result["rows"] == 0

    def test_null_paths(self, mock_ads_client):
        set_active_account("1234567890")
        mock_ads_client["set_gaql"](
            {
                "FROM ad_group_ad": [_ad_row()],
            }
        )

        tool = _register_tool("list_ads")
        result = tool(customer_id="1234567890")

        ad = result["top"][0]
        assert ad["path1"] is None
        assert ad["path2"] is None


# ---------------------------------------------------------------------------
# create_responsive_search_ad
# ---------------------------------------------------------------------------


class TestCreateResponsiveSearchAd:
    def test_basic_creation(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["headlines_count"] == 3
        assert result["descriptions_count"] == 2
        assert "resource_name" in result
        # No pinning or paths in basic creation
        assert "pinned_headlines" not in result
        assert "path1" not in result

    def test_creation_with_pinning(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            pinned_headlines=[1, None, 3],
            pinned_descriptions=[1, None],
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["pinned_headlines"] == [1, None, 3]
        assert result["pinned_descriptions"] == [1, None]

    def test_creation_with_paths(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            path1="shoes",
            path2="running",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["path1"] == "shoes"
        assert result["path2"] == "running"

    def test_creation_with_all_options(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            pinned_headlines=[1, None, 2],
            pinned_descriptions=[None, 2],
            path1="deals",
            path2="sale",
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["pinned_headlines"] == [1, None, 2]
        assert result["pinned_descriptions"] == [None, 2]
        assert result["path1"] == "deals"
        assert result["path2"] == "sale"

    def test_pinned_headlines_length_mismatch(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            pinned_headlines=[1, None],  # only 2 but 3 headlines
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "pinned_headlines length" in result["message"]

    def test_pinned_descriptions_length_mismatch(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            pinned_descriptions=[1],  # only 1 but 2 descriptions
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "pinned_descriptions length" in result["message"]

    def test_invalid_headline_pin_value(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            pinned_headlines=[1, 5, None],  # 5 is invalid
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "pinned_headlines[1] = 5" in result["message"]

    def test_invalid_description_pin_value(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            pinned_descriptions=[None, 3],  # 3 is invalid for descriptions
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "pinned_descriptions[1] = 3" in result["message"]

    def test_path1_too_long(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            path1="a" * 16,
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "path1 exceeds 15" in result["message"]

    def test_path2_too_long(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            path2="b" * 16,
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "path2 exceeds 15" in result["message"]

    def test_invalid_ad_group_id(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="abc",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
            customer_id="1234567890",
        )

        assert result["error"] is True
        assert "ad_group_id" in result["message"]


# ---------------------------------------------------------------------------
# set_ad_status
# ---------------------------------------------------------------------------


class TestSetAdStatus:
    def test_without_confirm_returns_warning(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("set_ad_status")
        result = tool(
            ad_group_id="333",
            ad_id="555",
            status="PAUSED",
            customer_id="1234567890",
        )

        assert result["warning"] is True

    def test_with_confirm_succeeds(self, mock_ads_client):
        set_active_account("1234567890")

        tool = _register_tool("set_ad_status")
        result = tool(
            ad_group_id="333",
            ad_id="555",
            status="PAUSED",
            confirm=True,
            customer_id="1234567890",
        )

        assert "error" not in result
        assert result["new_status"] == "PAUSED"


# ---------------------------------------------------------------------------
# No active account
# ---------------------------------------------------------------------------


class TestNoActiveAccount:
    def test_list_ads_no_account(self, mock_ads_client):
        tool = _register_tool("list_ads")
        result = tool()

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_create_ad_no_account(self, mock_ads_client):
        tool = _register_tool("create_responsive_search_ad")
        result = tool(
            ad_group_id="333",
            headlines=["H1", "H2", "H3"],
            descriptions=["D1", "D2"],
            final_url="https://example.com",
        )

        assert result["error"] is True
        assert "No customer_id" in result["message"]

    def test_set_ad_status_no_account(self, mock_ads_client):
        tool = _register_tool("set_ad_status")
        result = tool(ad_group_id="333", ad_id="555", status="PAUSED", confirm=True)

        assert result["error"] is True
        assert "No customer_id" in result["message"]
