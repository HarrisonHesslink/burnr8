"""Shared test fixtures — mock Google Ads client reusable across all tool modules."""

from unittest.mock import MagicMock, patch

import pytest

import burnr8.session as _session

# Every tool module that does `from burnr8.client import get_client`
# and `from burnr8.helpers import run_gaql` binds those names into its
# own namespace.  We must patch each module's local binding.
_TOOL_MODULES = [
    "burnr8.tools.accounts",
    "burnr8.tools.ad_groups",
    "burnr8.tools.adjustments",
    "burnr8.tools.ads",
    "burnr8.tools.budgets",
    "burnr8.tools.campaigns",
    "burnr8.tools.competitive",
    "burnr8.tools.compound",
    "burnr8.tools.conversions",
    "burnr8.tools.extensions",
    "burnr8.tools.goals",
    "burnr8.tools.keywords",
    "burnr8.tools.negative_keywords",
    "burnr8.tools.reporting",
]

# Modules that also import save_report
_REPORT_MODULES = [
    "burnr8.tools.ads",
    "burnr8.tools.competitive",
    "burnr8.tools.compound",
    "burnr8.tools.extensions",
    "burnr8.tools.keywords",
    "burnr8.tools.negative_keywords",
    "burnr8.tools.reporting",
]


class MockGoogleAdsClient:
    """A fake GoogleAdsClient that works without credentials.

    Provides mock services with pre-configured mutate responses,
    proto-plus-style get_type(), and enum namespaces.  Covers all
    14 tool modules.
    """

    def __init__(self):
        self._services: dict[str, MagicMock] = {}
        self._enums = _build_enums()

    def get_service(self, name: str) -> MagicMock:
        if name not in self._services:
            self._services[name] = _build_service(name)
        return self._services[name]

    def get_type(self, name: str) -> MagicMock:
        """Return a mock operation type with real lists for append-based fields."""
        # Mutate request types: return instance with real operations list (v30 pattern)
        # build_mutate_request() sets fields via attribute assignment and appends to operations
        if name.startswith("Mutate") and name.endswith("Request"):
            mock = MagicMock(name=f"Type:{name}")
            mock.operations = []
            return mock

        mock = MagicMock(name=f"Type:{name}")
        mock.create = MagicMock(name=f"Type:{name}.create")

        # Operations that use update_mask.paths need a real list
        if name.endswith("Operation"):
            mock.update_mask.paths = []
            mock.update = MagicMock(name=f"Type:{name}.update")

        # CampaignOperation needs real list for url_custom_parameters
        if name == "CampaignOperation":
            mock.create.url_custom_parameters = []

        # AdGroupOperation needs real list for url_custom_parameters
        if name == "AdGroupOperation":
            mock.create.url_custom_parameters = []

        # AdGroupAdOperation needs real lists for append-based RSA fields
        if name == "AdGroupAdOperation":
            mock.create.ad.final_urls = []
            mock.create.ad.responsive_search_ad.headlines = []
            mock.create.ad.responsive_search_ad.descriptions = []
            mock.create.ad.url_custom_parameters = []

        # AssetOperation needs real lists for sitelink/snippet fields
        if name == "AssetOperation":
            mock.create.final_urls = []

        # Keyword plan request needs real lists
        if name == "GenerateKeywordIdeasRequest":
            mock.geo_target_constants = []
            mock.keyword_seed.keywords = []

        # Custom conversion goal needs real list
        if name == "CustomConversionGoalOperation":
            mock.create.conversion_actions = []

        return mock

    @property
    def enums(self):
        return self._enums


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_enums() -> MagicMock:
    """All enum values referenced across 14 tool modules."""
    enums = MagicMock(name="Enums")

    # Budget
    enums.BudgetDeliveryMethodEnum.STANDARD = "STANDARD"

    # Campaign
    enums.CampaignStatusEnum.PAUSED = "PAUSED"
    enums.CampaignStatusEnum.ENABLED = "ENABLED"
    enums.CampaignStatusEnum.REMOVED = "REMOVED"
    enums.AdvertisingChannelTypeEnum.SEARCH = "SEARCH"
    enums.AdvertisingChannelTypeEnum.DISPLAY = "DISPLAY"
    enums.AdvertisingChannelTypeEnum.SHOPPING = "SHOPPING"
    enums.AdvertisingChannelTypeEnum.VIDEO = "VIDEO"
    enums.TargetImpressionShareLocationEnum.ANYWHERE_ON_PAGE = "ANYWHERE_ON_PAGE"
    enums.TargetImpressionShareLocationEnum.TOP_OF_PAGE = "TOP_OF_PAGE"
    enums.TargetImpressionShareLocationEnum.ABSOLUTE_TOP_OF_PAGE = "ABSOLUTE_TOP_OF_PAGE"

    # Ad group
    enums.AdGroupStatusEnum.ENABLED = "ENABLED"
    enums.AdGroupStatusEnum.PAUSED = "PAUSED"
    enums.AdGroupStatusEnum.REMOVED = "REMOVED"
    enums.AdGroupTypeEnum.SEARCH_STANDARD = "SEARCH_STANDARD"

    # Ad group criterion / keywords
    enums.AdGroupCriterionStatusEnum.ENABLED = "ENABLED"
    enums.AdGroupCriterionStatusEnum.PAUSED = "PAUSED"
    enums.KeywordMatchTypeEnum.BROAD = "BROAD"
    enums.KeywordMatchTypeEnum.EXACT = "EXACT"
    enums.KeywordMatchTypeEnum.PHRASE = "PHRASE"

    # Ads
    enums.AdGroupAdStatusEnum.ENABLED = "ENABLED"
    enums.AdGroupAdStatusEnum.PAUSED = "PAUSED"
    enums.AdGroupAdStatusEnum.REMOVED = "REMOVED"

    # RSA pinning — ServedAssetFieldTypeEnum
    enums.ServedAssetFieldTypeEnum.HEADLINE_1 = "HEADLINE_1"
    enums.ServedAssetFieldTypeEnum.HEADLINE_2 = "HEADLINE_2"
    enums.ServedAssetFieldTypeEnum.HEADLINE_3 = "HEADLINE_3"
    enums.ServedAssetFieldTypeEnum.DESCRIPTION_1 = "DESCRIPTION_1"
    enums.ServedAssetFieldTypeEnum.DESCRIPTION_2 = "DESCRIPTION_2"

    # EU political advertising
    enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING = (
        "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"
    )
    enums.EuPoliticalAdvertisingStatusEnum.CONTAINS_EU_POLITICAL_ADVERTISING = "CONTAINS_EU_POLITICAL_ADVERTISING"

    # Adjustments — devices, schedules, geo
    enums.DeviceEnum.MOBILE = 30001
    enums.DeviceEnum.DESKTOP = 30000
    enums.DeviceEnum.TABLET = 30002
    enums.DayOfWeekEnum.MONDAY = "MONDAY"
    enums.DayOfWeekEnum.TUESDAY = "TUESDAY"
    enums.DayOfWeekEnum.WEDNESDAY = "WEDNESDAY"
    enums.DayOfWeekEnum.THURSDAY = "THURSDAY"
    enums.DayOfWeekEnum.FRIDAY = "FRIDAY"
    enums.DayOfWeekEnum.SATURDAY = "SATURDAY"
    enums.DayOfWeekEnum.SUNDAY = "SUNDAY"
    enums.MinuteOfHourEnum.ZERO = "ZERO"
    enums.PositiveGeoTargetTypeEnum.PRESENCE = "PRESENCE"
    enums.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST = "PRESENCE_OR_INTEREST"
    enums.NegativeGeoTargetTypeEnum.PRESENCE = "PRESENCE"
    enums.NegativeGeoTargetTypeEnum.PRESENCE_OR_INTEREST = "PRESENCE_OR_INTEREST"

    # Conversions
    enums.ConversionActionStatusEnum.ENABLED = "ENABLED"
    enums.ConversionActionStatusEnum.REMOVED = "REMOVED"
    enums.ConversionActionStatusEnum.HIDDEN = "HIDDEN"
    enums.ConversionActionTypeEnum.WEBPAGE = "WEBPAGE"
    enums.ConversionActionTypeEnum.UPLOAD_CLICKS = "UPLOAD_CLICKS"
    enums.ConversionActionCategoryEnum.PURCHASE = "PURCHASE"
    enums.ConversionActionCategoryEnum.LEAD = "LEAD"
    enums.ConversionActionCategoryEnum.SIGNUP = "SIGNUP"
    enums.ConversionActionCountingTypeEnum.ONE_PER_CLICK = "ONE_PER_CLICK"
    enums.ConversionActionCountingTypeEnum.MANY_PER_CLICK = "MANY_PER_CLICK"

    # Extensions
    enums.AssetFieldTypeEnum.SITELINK = "SITELINK"
    enums.AssetFieldTypeEnum.CALLOUT = "CALLOUT"
    enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET = "STRUCTURED_SNIPPET"
    enums.AssetFieldTypeEnum.SQUARE_MARKETING_IMAGE = "SQUARE_MARKETING_IMAGE"
    enums.AssetTypeEnum.IMAGE = "IMAGE"
    enums.MimeTypeEnum.IMAGE_JPEG = "IMAGE_JPEG"
    enums.MimeTypeEnum.IMAGE_PNG = "IMAGE_PNG"

    # Goals
    enums.CustomConversionGoalStatusEnum.ENABLED = "ENABLED"
    enums.GoalConfigLevelEnum.CAMPAIGN = "CAMPAIGN"

    # Keywords (research)
    enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH = "GOOGLE_SEARCH"

    return enums


def _make_mutate_response(*resource_names: str) -> MagicMock:
    resp = MagicMock()
    results = []
    for rn in resource_names:
        r = MagicMock()
        r.resource_name = rn
        results.append(r)
    resp.results = results
    return resp


def _build_service(name: str) -> MagicMock:
    """Return a service mock with sensible default mutate responses."""
    svc = MagicMock(name=f"Service:{name}")

    defaults = {
        "CampaignBudgetService": ("mutate_campaign_budgets", ["customers/1234567890/campaignBudgets/111"]),
        "CampaignService": ("mutate_campaigns", ["customers/1234567890/campaigns/222"]),
        "AdGroupService": ("mutate_ad_groups", ["customers/1234567890/adGroups/333"]),
        "AdGroupCriterionService": (
            "mutate_ad_group_criteria",
            ["customers/1234567890/adGroupCriteria/333~444", "customers/1234567890/adGroupCriteria/333~445"],
        ),
        "AdGroupAdService": ("mutate_ad_group_ads", ["customers/1234567890/adGroupAds/333~555"]),
        "CampaignCriterionService": (
            "mutate_campaign_criteria",
            ["customers/1234567890/campaignCriteria/222~600"],
        ),
        "ConversionActionService": (
            "mutate_conversion_actions",
            ["customers/1234567890/conversionActions/700"],
        ),
        "AssetService": ("mutate_assets", ["customers/1234567890/assets/800"]),
        "CampaignAssetService": (
            "mutate_campaign_assets",
            ["customers/1234567890/campaignAssets/222~800"],
        ),
        "AdGroupAssetService": (
            "mutate_ad_group_assets",
            ["customers/1234567890/adGroupAssets/333~800"],
        ),
        "CustomerConversionGoalService": (
            "mutate_customer_conversion_goals",
            ["customers/1234567890/customerConversionGoals/700"],
        ),
        "CustomConversionGoalService": (
            "mutate_custom_conversion_goals",
            ["customers/1234567890/customConversionGoals/900"],
        ),
        "ConversionGoalCampaignConfigService": (
            "mutate_conversion_goal_campaign_configs",
            ["customers/1234567890/conversionGoalCampaignConfigs/222"],
        ),
    }

    if name in defaults:
        method_name, resource_names = defaults[name]
        getattr(svc, method_name).return_value = _make_mutate_response(*resource_names)
    elif name == "CustomerService":
        svc.list_accessible_customers.return_value = MagicMock(
            resource_names=["customers/1234567890", "customers/9876543210"]
        )
    elif name == "KeywordPlanIdeaService":
        # research_keywords iterates response.results as proto objects
        svc.generate_keyword_ideas.return_value = MagicMock(results=[])

    return svc


def _make_mock_run_gaql(query_map: dict[str, list[dict]]):
    """Return a callable matching run_gaql's signature.

    query_map maps GAQL substring -> rows.  First match wins.
    Unmatched queries return [].
    """

    def _mock(_client, _customer_id, query, limit=0):  # noqa: ARG001
        for substring, rows in query_map.items():
            if substring in query:
                return rows
        return []

    return _mock


def _mock_save_report(rows, report_name, top_n=10):
    """Mock save_report that returns the same shape without writing files."""
    if not rows:
        return {
            "file": None,
            "url": None,
            "rows": 0,
            "top": [],
            "message": "No data returned.",
        }
    fieldnames = list(rows[0].keys())
    return {
        "file": f"/tmp/mock_reports/{report_name}.csv",
        "rows": len(rows),
        "columns": fieldnames,
        "top": rows[:top_n],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_ads_client():
    """Patch get_client, run_gaql, save_report, and log_tool_call across ALL tool modules.

    Yields a dict:
        client   -- MockGoogleAdsClient instance (access services, types, enums)
        set_gaql -- call with {"FROM campaign": [...]} to set query results
        run_gaql -- the mock callable (for call count assertions)

    Works for any tool module — no per-module setup needed.
    """
    client = MockGoogleAdsClient()
    query_map: dict[str, list[dict]] = {}
    mock_gaql = _make_mock_run_gaql(query_map)

    def set_gaql(new_map: dict[str, list[dict]]):
        query_map.clear()
        query_map.update(new_map)

    patches = []

    # Patch get_client and run_gaql in every tool module
    for mod in _TOOL_MODULES:
        patches.append(patch(f"{mod}.get_client", return_value=client))
        patches.append(patch(f"{mod}.run_gaql", side_effect=mock_gaql))

    # Patch save_report in modules that use it
    for mod in _REPORT_MODULES:
        patches.append(patch(f"{mod}.save_report", side_effect=_mock_save_report))

    # Suppress logging and usage stat side-effects
    patches.append(patch("burnr8.errors.log_tool_call"))
    patches.append(
        patch(
            "burnr8.tools.accounts.get_usage_stats",
            return_value={"operations_today": 0, "errors_today": 0, "last_tool": None},
        )
    )
    patches.append(patch("burnr8.tools.accounts.get_recent_errors", return_value=[]))

    for p in patches:
        p.start()

    yield {
        "client": client,
        "set_gaql": set_gaql,
        "run_gaql": mock_gaql,
    }

    for p in patches:
        p.stop()


@pytest.fixture(autouse=True)
def _reset_session():
    """Reset active account and client singleton between tests to prevent state leakage."""
    import burnr8.client as _client_mod

    _session._active_account.set(None)
    _client_mod._client = None
    yield
    _session._active_account.set(None)
    _client_mod._client = None
