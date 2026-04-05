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
    proto-plus-style get_type(), and enum namespaces.
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
        mock = MagicMock(name=f"Type:{name}")
        mock.create = MagicMock(name=f"Type:{name}.create")
        if name == "AdGroupAdOperation":
            mock.create.ad.final_urls = []
            mock.create.ad.responsive_search_ad.headlines = []
            mock.create.ad.responsive_search_ad.descriptions = []
        return mock

    @property
    def enums(self):
        return self._enums


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_enums() -> MagicMock:
    enums = MagicMock(name="Enums")
    enums.BudgetDeliveryMethodEnum.STANDARD = "STANDARD"
    enums.CampaignStatusEnum.PAUSED = "PAUSED"
    enums.AdvertisingChannelTypeEnum.SEARCH = "SEARCH"
    enums.AdGroupStatusEnum.ENABLED = "ENABLED"
    enums.AdGroupTypeEnum.SEARCH_STANDARD = "SEARCH_STANDARD"
    enums.AdGroupCriterionStatusEnum.ENABLED = "ENABLED"
    enums.KeywordMatchTypeEnum.BROAD = "BROAD"
    enums.AdGroupAdStatusEnum.ENABLED = "ENABLED"
    enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING = (
        "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"
    )
    enums.EuPoliticalAdvertisingStatusEnum.CONTAINS_EU_POLITICAL_ADVERTISING = "CONTAINS_EU_POLITICAL_ADVERTISING"
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
    svc = MagicMock(name=f"Service:{name}")
    if name == "CampaignBudgetService":
        svc.mutate_campaign_budgets.return_value = _make_mutate_response("customers/1234567890/campaignBudgets/111")
    elif name == "CampaignService":
        svc.mutate_campaigns.return_value = _make_mutate_response("customers/1234567890/campaigns/222")
    elif name == "AdGroupService":
        svc.mutate_ad_groups.return_value = _make_mutate_response("customers/1234567890/adGroups/333")
    elif name == "AdGroupCriterionService":
        svc.mutate_ad_group_criteria.return_value = _make_mutate_response(
            "customers/1234567890/adGroupCriteria/333~444",
            "customers/1234567890/adGroupCriteria/333~445",
        )
    elif name == "AdGroupAdService":
        svc.mutate_ad_group_ads.return_value = _make_mutate_response("customers/1234567890/adGroupAds/333~555")
    elif name == "CustomerService":
        svc.list_accessible_customers.return_value = MagicMock(
            resource_names=["customers/1234567890", "customers/9876543210"]
        )
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
    top = rows[:top_n] if rows else []
    return {
        "file": f"/tmp/mock_reports/{report_name}.csv",
        "rows": len(rows),
        "top": top,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_ads_client():
    """Patch get_client, run_gaql, save_report, and log_tool_call across ALL tool modules.

    Yields a dict:
        client   — MockGoogleAdsClient instance (access services, types, enums)
        set_gaql — call with {"FROM campaign": [...]} to set query results
        run_gaql — the mock callable (for call count assertions)

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

    # Suppress logging side-effects
    patches.append(patch("burnr8.errors.log_tool_call"))

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
    """Reset active account between tests to prevent state leakage."""
    _session._active_account = None
    yield
    _session._active_account = None
