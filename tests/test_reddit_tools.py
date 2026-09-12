"""Financial controls, reporting and actual MCP boundary tests for Reddit tools."""

import asyncio
import contextvars
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import requests
from fastmcp import Client, FastMCP

from burnr8.tools.reddit_ads import register


class Capture:
    def __init__(self):
        self.tools = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


class FakeReddit:
    def __init__(self):
        self.calls = []
        self.persist = True
        self.fail_readback = False
        self.fail_write = False
        self.wrote = False
        self.account = {
            "id": "a2_test",
            "currency": "USD",
            "time_zone_id": "America/Phoenix",
            "click_attribution_window": "WEEK",
            "view_attribution_window": "DAY",
        }
        self.resources = {
            "campaigns/123": {
                "id": "123",
                "ad_account_id": "a2_test",
                "configured_status": "PAUSED",
                "is_campaign_budget_optimization": False,
                "spend_cap": 100_000_000,
            },
            "ad_groups/234": {
                "id": "234",
                "ad_account_id": "a2_test",
                "campaign_id": "123",
                "configured_status": "PAUSED",
                "goal_type": "DAILY_SPEND",
                "goal_value": 5_000_000,
            },
            "ads/345": {"id": "345", "ad_account_id": "a2_test", "campaign_id": "123", "configured_status": "PAUSED"},
        }

    def request(self, method, path, *, params=None, body=None, next_url=None):
        self.calls.append(
            {"method": method, "path": path, "params": params, "body": deepcopy(body), "next_url": next_url}
        )
        if method == "GET":
            if path == "ad_accounts/a2_test":
                return {"data": deepcopy(self.account)}
            if path in self.resources:
                if self.wrote and self.fail_readback:
                    raise requests.Timeout("private provider detail")
                return {"data": deepcopy(self.resources[path])}
            return {
                "data": [{"id": "123"}],
                "pagination": {
                    "next_url": f"https://ads-api.reddit.com/api/v3/{path}?page.token=two" if next_url is None else None
                },
            }
        if path.endswith("/reports"):
            return {
                "data": {
                    "metrics": [
                        {"campaign_id": "123", "spend": 1_950_000, "clicks": 2},
                        {"campaign_id": "123", "spend": 0, "conversion_sign_up_clicks": 1},
                    ],
                    "metrics_updated_at": "2026-09-07T20:00:00Z",
                },
                "pagination": {
                    "next_url": f"https://ads-api.reddit.com/api/v3/{path}?page.token=two" if next_url is None else None
                },
            }
        if self.fail_write:
            raise requests.Timeout("private token in network error")
        self.wrote = True
        if method == "POST":
            self.resources["campaigns/456"] = {"id": "456", "ad_account_id": "a2_test", **body["data"]}
            return {"data": deepcopy(self.resources["campaigns/456"])}
        if self.persist:
            self.resources[path].update(body["data"])
        return {"data": deepcopy(self.resources[path])}


@pytest.fixture
def tools(monkeypatch):
    fake = FakeReddit()
    monkeypatch.setattr("burnr8.tools.reddit_ads.get_reddit_client", lambda: fake)
    monkeypatch.setattr("burnr8.reddit.errors.log_tool_call", MagicMock())
    monkeypatch.setenv("REDDIT_AD_ACCOUNT_ID", "a2_test")
    monkeypatch.delenv("BURNR8_REDDIT_MAX_SPEND_CAP_DOLLARS", raising=False)
    capture = Capture()
    register(capture)
    return capture.tools, fake


def writes(fake):
    return [
        call for call in fake.calls if call["method"] in {"POST", "PATCH"} and not call["path"].endswith("/reports")
    ]


def test_creation_preview_does_not_write_and_shows_real_request(tools):
    funcs, fake = tools
    result = funcs["reddit_create_campaign"]("Pilot", "CLICKS", 100)
    assert result["warning"]
    data = result["plan"]["request"]["data"]
    assert data["configured_status"] == "PAUSED"
    assert data["spend_cap"] == 100_000_000
    assert data["is_campaign_budget_optimization"] is False
    assert not writes(fake)


def test_creation_always_paused_and_read_back(tools):
    funcs, fake = tools
    result = funcs["reddit_create_campaign"]("Pilot", "CLICKS", 100, confirm=True)
    assert result["created"] and result["verified"]
    assert result["resource_id"] == "456"
    assert writes(fake)[0]["body"]["data"]["configured_status"] == "PAUSED"
    assert fake.calls[-1]["path"] == "campaigns/456"


@pytest.mark.parametrize("kind,ident", [("campaign", "123"), ("ad_group", "234"), ("ad", "345")])
def test_status_preview_and_confirmed_change(tools, kind, ident):
    funcs, fake = tools
    assert funcs["reddit_set_status"](kind, ident, "ACTIVE")["warning"]
    assert not writes(fake)
    result = funcs["reddit_set_status"](kind, ident, "ACTIVE", confirm=True)
    assert result["updated"] and result["verified"]
    assert writes(fake)[0]["body"] == {"data": {"configured_status": "ACTIVE"}}
    assert funcs["reddit_set_status"](kind, ident, "ACTIVE", confirm=True)["no_change"]
    assert len(writes(fake)) == 1


@pytest.mark.parametrize("status", ["DELETED", "ARCHIVED", "enabled"])
def test_destructive_states_are_unavailable(tools, status):
    funcs, fake = tools
    assert funcs["reddit_set_status"]("campaign", "123", status, confirm=True)["error"]
    assert not fake.calls


def test_ownership_mismatch_cannot_mutate(tools):
    funcs, fake = tools
    fake.resources["campaigns/123"]["ad_account_id"] = "a2_other"
    assert funcs["reddit_set_status"]("campaign", "123", "ACTIVE", confirm=True)["error"]
    assert not writes(fake)


def test_readback_mismatch_and_failure_preserve_write_outcome(tools):
    funcs, fake = tools
    fake.persist = False
    result = funcs["reddit_set_status"]("campaign", "123", "ACTIVE", confirm=True)
    assert result["updated"] and result["verified"] is False and result["warning"]
    fake.fail_readback = True
    fake.wrote = False
    result = funcs["reddit_update_campaign_spend_cap"]("123", 50, confirm=True)
    assert result["updated"] and result["verified"] is False
    assert result["resource_id"] == "123"


def test_timed_out_creation_reports_unknown_and_never_retries(tools):
    funcs, fake = tools
    fake.fail_write = True
    result = funcs["reddit_create_campaign"]("Pilot", "CLICKS", 100, confirm=True)
    assert result["mutation_outcome"] == "unknown"
    assert "private" not in str(result)
    assert len(writes(fake)) == 1


@pytest.mark.parametrize("amount", [-1, 0, 0.001, float("nan"), float("inf"), 1000.01])
def test_bad_spend_caps_stop_before_provider_request(tools, amount):
    funcs, fake = tools
    assert funcs["reddit_create_campaign"]("Pilot", "CLICKS", amount, confirm=True)["error"]
    assert not fake.calls


@pytest.mark.parametrize("setting", ["not-a-number", "NaN", "Infinity", "0", "-5"])
def test_invalid_cap_configuration_fails_closed(tools, monkeypatch, setting):
    funcs, fake = tools
    monkeypatch.setenv("BURNR8_REDDIT_MAX_SPEND_CAP_DOLLARS", setting)
    assert funcs["reddit_create_campaign"]("Pilot", "CLICKS", 100, confirm=True)["error"]
    assert not fake.calls


def test_daily_budget_uses_micros_and_preview(tools):
    funcs, fake = tools
    assert funcs["reddit_update_ad_group_budget"]("234", 7.1234565)["warning"]
    assert not writes(fake)
    result = funcs["reddit_update_ad_group_budget"]("234", 7.1234565, confirm=True)
    assert result["verified"]
    assert writes(fake)[0]["body"] == {"data": {"goal_value": 7_123_457}}


def test_daily_budget_honors_existing_global_circuit_breaker(tools):
    from burnr8.session import set_financial_limits

    funcs, fake = tools
    context = contextvars.copy_context()
    context.run(set_financial_limits, max_daily_budget=10)
    assert context.run(funcs["reddit_update_ad_group_budget"], "234", 10.01, confirm=True)["error"]
    assert not fake.calls


@pytest.mark.parametrize("mode", ["lifetime", "cbo", "unknown", "currency", "foreign_parent"])
def test_incompatible_budget_modes_or_currency_cannot_write(tools, mode):
    funcs, fake = tools
    if mode == "lifetime":
        fake.resources["ad_groups/234"]["goal_type"] = "LIFETIME_SPEND"
    elif mode == "cbo":
        fake.resources["campaigns/123"]["is_campaign_budget_optimization"] = True
    elif mode == "unknown":
        del fake.resources["campaigns/123"]["is_campaign_budget_optimization"]
    elif mode == "currency":
        fake.account["currency"] = "EUR"
    else:
        fake.resources["campaigns/123"]["ad_account_id"] = "a2_other"
    assert funcs["reddit_update_ad_group_budget"]("234", 10, confirm=True)["error"]
    assert not writes(fake)


def test_inventory_explicitly_returns_pagination(tools):
    funcs, fake = tools
    first = funcs["reddit_list_campaigns"]()
    assert first["has_more"]
    second = funcs["reddit_list_campaigns"](next_url=first["next_url"])
    assert second["has_more"] is False
    assert fake.calls[-1]["next_url"] == first["next_url"]


def test_report_csv_preserves_sparse_metrics_units_and_pagination(tools, tmp_path, monkeypatch):
    funcs, fake = tools
    monkeypatch.setattr("burnr8.reports.REPORTS_DIR", tmp_path)
    monkeypatch.setattr("burnr8.reports.REPORT_MODE", "disk")
    result = funcs["reddit_get_report"]("2026-09-01T00:00:00Z", "2026-09-07T00:00:00Z")
    assert result["has_more"]
    assert result["top"][0]["spend"] == 1_950_000
    assert result["top"][0]["spend_currency_units"] == 1.95
    assert result["top"][1]["conversion_sign_up_clicks"] == 1
    assert "conversion_sign_up_clicks" in result["columns"]
    assert result["currency"] == "USD" and result["time_zone"] == "UTC"
    assert result["metrics_updated_at"] == "2026-09-07T20:00:00Z"
    report_request = fake.calls[-1]
    assert report_request["method"] == "POST"
    assert report_request["body"]["data"]["breakdowns"] == ["CAMPAIGN_ID", "DATE"]
    assert "CONVERSION_PURCHASE_CLICKS" in report_request["body"]["data"]["fields"]


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-09-01", "2026-09-07"),
        ("2026-09-01T00:01:00Z", "2026-09-07T00:00:00Z"),
        ("2026-09-07T00:00:00Z", "2026-09-01T00:00:00Z"),
        ("2026-07-01T00:00:00Z", "2026-09-07T00:00:00Z"),
    ],
)
def test_invalid_report_windows_stop_before_credentials(tools, start, end):
    funcs, fake = tools
    assert funcs["reddit_get_report"](start, end)["error"]
    assert not fake.calls


def test_real_fastmcp_serializes_preview_with_no_mutation(tools):
    _, fake = tools
    mcp = FastMCP("reddit-test")
    register(mcp)

    async def run():
        async with Client(mcp) as client:
            return await client.call_tool(
                "reddit_create_campaign",
                {"name": "Pilot", "objective": "CLICKS", "spend_cap_dollars": 100, "account_id": "a2_test"},
            )

    result = asyncio.run(run())
    assert result.data["warning"]
    assert result.data["plan"]["request"]["data"]["configured_status"] == "PAUSED"
    assert not writes(fake)
