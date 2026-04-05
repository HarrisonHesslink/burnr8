"""Shared test fixtures — mock Google Ads client and run_gaql helper."""

from unittest.mock import MagicMock, patch

import pytest

import burnr8.session as _session


class MockGoogleAdsClient:
    """A fake GoogleAdsClient that provides mock services, types, and enums.

    Services return MagicMock objects whose mutate methods produce fake
    resource names so that tools like launch_campaign can run end-to-end
    without real credentials.
    """

    def __init__(self):
        self._services: dict[str, MagicMock] = {}
        self._enums = _build_enums()

    # -- services ----------------------------------------------------------

    def get_service(self, name: str) -> MagicMock:
        if name not in self._services:
            self._services[name] = _build_service(name)
        return self._services[name]

    # -- types -------------------------------------------------------------

    def get_type(self, name: str) -> MagicMock:
        """Return a MagicMock whose `create` attribute is itself a MagicMock.

        This mirrors the proto-plus pattern where you do:
            op = client.get_type("CampaignBudgetOperation")
            budget = op.create
            budget.name = "..."
        """
        mock = MagicMock(name=f"Type:{name}")
        # For operations, `create` must be a nested mock with arbitrary attr
        # setting and sub-objects like `ad.responsive_search_ad.headlines`.
        mock.create = MagicMock(name=f"Type:{name}.create")
        # Support `ad.final_urls.append(...)` — make final_urls a real list
        if name == "AdGroupAdOperation":
            mock.create.ad.final_urls = []
            mock.create.ad.responsive_search_ad.headlines = []
            mock.create.ad.responsive_search_ad.descriptions = []
        return mock

    # -- enums -------------------------------------------------------------

    @property
    def enums(self):
        return self._enums


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_enums() -> MagicMock:
    """Create a namespace of enum-like attributes the tools reference."""
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
    """Build a fake mutate response whose .results contain resource_name attrs."""
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

    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_run_gaql(query_map: dict[str, list[dict]]):
    """Return a function that behaves like run_gaql but returns canned data.

    ``query_map`` maps a GAQL substring to the list[dict] that should be
    returned when a query containing that substring is executed.  The first
    matching substring wins.  If nothing matches, an empty list is returned.
    """

    def _mock_run_gaql(_client, _customer_id, query, limit=0):  # noqa: ARG001
        for substring, rows in query_map.items():
            if substring in query:
                return rows
        return []

    return _mock_run_gaql


@pytest.fixture()
def mock_ads_client():
    """Patch ``get_client`` and ``run_gaql`` for credential-free testing.

    Yields a dict with three keys:

    * ``client``    – the ``MockGoogleAdsClient`` instance
    * ``set_gaql``  – call ``set_gaql({"FROM campaign": [...]})`` to set
                      query-substring -> result mappings **before** invoking a
                      tool
    * ``run_gaql``  – reference to the mock callable (useful for assertions)

    Example::

        def test_something(mock_ads_client):
            mock_ads_client["set_gaql"]({"FROM campaign": [row1, row2]})
            result = some_tool(customer_id="1234567890")
            assert ...
    """
    client = MockGoogleAdsClient()
    # Start with empty query map — caller sets it via set_gaql
    query_map: dict[str, list[dict]] = {}
    mock_gaql = _make_mock_run_gaql(query_map)

    def set_gaql(new_map: dict[str, list[dict]]):
        query_map.clear()
        query_map.update(new_map)

    with (
        patch("burnr8.tools.compound.get_client", return_value=client),
        patch("burnr8.tools.compound.run_gaql", side_effect=mock_gaql),
        patch("burnr8.errors.log_tool_call"),
    ):
        yield {
            "client": client,
            "set_gaql": set_gaql,
            "run_gaql": mock_gaql,
        }


@pytest.fixture(autouse=True)
def _reset_session():
    """Reset active account between tests to prevent state leakage."""
    _session._active_account = None
    yield
    _session._active_account = None
