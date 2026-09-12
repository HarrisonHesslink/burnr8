"""Behavior tests for Meta Ads reporting and management MCP tools."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from burnr8.tools.meta_management import register


class _Capture:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


class _FakeMetaClient:
    def __init__(
        self,
        *,
        account_id: str = "123",
        currency: str = "USD",
        has_daily_budget: bool = True,
        persist_updates: bool = True,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.account_id = account_id
        self.currency = currency
        self.has_daily_budget = has_daily_budget
        self.persist_updates = persist_updates
        self.campaign_status = "PAUSED"
        self.ad_set_status = "PAUSED"
        self.ad_status = "PAUSED"
        self.daily_budget = "2500"

    def request(self, method, path, *, params=None, files=None):  # noqa: ARG002
        self.calls.append({"method": method, "path": path, "params": params})
        params = params or {}
        if method == "GET" and path == "act_123/campaigns":
            if params.get("after") == "campaign-cursor":
                return {"data": [{"id": "1002", "account_id": "123", "name": "Second"}]}
            return {
                "data": [{"id": "1001", "account_id": "123", "name": "First"}],
                "paging": {
                    "cursors": {"after": "campaign-cursor"},
                    "next": "https://graph.facebook.com/page?access_token=must-not-leak",
                },
            }
        if method == "GET" and path == "act_123/adsets":
            return {"data": [self._ad_set()]}
        if method == "GET" and path == "1001/adsets":
            return {"data": [self._ad_set()]}
        if method == "GET" and path in {"act_123/ads", "1001/ads", "2001/ads"}:
            return {"data": [self._ad()]}
        if method == "GET" and path == "act_123/insights":
            return {
                "data": [
                    {
                        "campaign_id": "1001",
                        "campaign_name": "StudyWithLily Reels",
                        "spend": "12.50",
                        "actions": [
                            {"action_type": "landing_page_view", "value": "18"},
                            {"action_type": "offsite_conversion.fb_pixel_complete_registration", "value": "2"},
                        ],
                        "cost_per_action_type": [
                            {"action_type": "landing_page_view", "value": "0.694444"},
                        ],
                    }
                ],
                "summary": {"total_count": 1},
            }
        if method == "GET" and path == "3001/previews":
            return {"data": [{"body": "<iframe src='https://facebook.test/preview'></iframe>"}]}
        if method == "GET" and path == "act_123":
            return {
                "id": "act_123",
                "account_id": "123",
                "name": "StudyWithLily",
                "account_status": 1,
                "currency": self.currency,
            }
        if method == "GET" and path == "1001":
            return self._campaign()
        if method == "GET" and path == "2001":
            return self._ad_set()
        if method == "GET" and path == "3001":
            return self._ad()
        if method == "POST" and path == "1001":
            if self.persist_updates:
                self.campaign_status = str(params["status"])
            return {"success": True}
        if method == "POST" and path == "2001":
            if self.persist_updates and "status" in params:
                self.ad_set_status = str(params["status"])
            if self.persist_updates and "daily_budget" in params:
                self.daily_budget = str(params["daily_budget"])
            return {"success": True}
        if method == "POST" and path == "3001":
            if self.persist_updates:
                self.ad_status = str(params["status"])
            return {"success": True}
        raise AssertionError(f"Unexpected request: {method} {path} {params}")

    def _campaign(self) -> dict[str, object]:
        return {
            "id": "1001",
            "account_id": self.account_id,
            "name": "StudyWithLily Reels",
            "status": self.campaign_status,
            "effective_status": self.campaign_status,
        }

    def _ad_set(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": "2001",
            "account_id": self.account_id,
            "campaign_id": "1001",
            "name": "StudyWithLily Reels - Reels",
            "status": self.ad_set_status,
            "effective_status": self.ad_set_status,
        }
        if self.has_daily_budget:
            result["daily_budget"] = self.daily_budget
        return result

    def _ad(self) -> dict[str, object]:
        return {
            "id": "3001",
            "account_id": self.account_id,
            "campaign_id": "1001",
            "adset_id": "2001",
            "name": "StudyWithLily Photo 1",
            "status": self.ad_status,
            "effective_status": self.ad_status,
        }


@pytest.fixture
def tools():
    capture = _Capture()
    register(capture)
    return capture.tools


def _call(tools, name, **kwargs):
    return tools[name](**kwargs)


def test_registers_the_nine_meta_operations_tools(tools):
    assert set(tools) == {
        "meta_list_campaigns",
        "meta_list_ad_sets",
        "meta_list_ads",
        "meta_get_insights",
        "meta_get_ad_preview",
        "meta_set_campaign_status",
        "meta_set_ad_set_status",
        "meta_set_ad_status",
        "meta_update_ad_set_budget",
    }


def test_campaign_listing_paginates_without_returning_token_bearing_url(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_list_campaigns",
            account_id="123",
            effective_statuses=["active", "paused"],
            max_results=2,
        )

    assert [campaign["id"] for campaign in result["campaigns"]] == ["1001", "1002"]
    assert result["paging"] == {"pages_fetched": 2, "has_more": False, "next_after": None}
    assert "access_token" not in repr(result)
    first_call = client.calls[0]
    assert first_call["params"]["effective_status"] == ["ACTIVE", "PAUSED"]
    assert client.calls[1]["params"]["after"] == "campaign-cursor"


def test_campaign_listing_rejects_ad_only_effective_status(tools):
    with patch("burnr8.tools.meta_management.get_meta_client") as get_client:
        result = _call(
            tools,
            "meta_list_campaigns",
            account_id="123",
            effective_statuses=["PENDING_REVIEW"],
        )

    assert result["error"] is True
    assert "Unsupported effective status" in result["message"]
    get_client.assert_not_called()


def test_ad_set_listing_can_be_scoped_to_owned_campaign(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(tools, "meta_list_ad_sets", account_id="123", campaign_id="1001")

    assert result["ad_sets"][0]["id"] == "2001"
    assert [call["path"] for call in client.calls] == ["1001", "1001/adsets"]


def test_ad_listing_can_be_scoped_to_owned_ad_set(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(tools, "meta_list_ads", account_id="123", ad_set_id="2001")

    assert result["ads"][0]["id"] == "3001"
    assert [call["path"] for call in client.calls] == ["2001", "2001/ads"]


def test_ad_listing_rejects_two_parent_filters_without_api_call(tools):
    with patch("burnr8.tools.meta_management.get_meta_client") as get_client:
        result = _call(
            tools,
            "meta_list_ads",
            account_id="123",
            campaign_id="1001",
            ad_set_id="2001",
        )

    assert result["error"] is True
    assert "not both" in result["message"]
    get_client.assert_not_called()


def test_insights_send_custom_range_and_normalize_action_metrics(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_get_insights",
            account_id="123",
            level="campaign",
            since="2026-07-01",
            until="2026-07-17",
            breakdowns=["publisher_platform", "platform_position"],
            time_increment=1,
        )

    row = result["insights"][0]
    assert row["actions_by_type"]["landing_page_view"] == 18
    assert row["actions_by_type"]["offsite_conversion.fb_pixel_complete_registration"] == 2
    assert row["cost_per_action_type_by_type"]["landing_page_view"] == pytest.approx(0.694444)
    assert result["summary"] == {"total_count": 1}
    params = client.calls[0]["params"]
    assert params["time_range"] == {"since": "2026-07-01", "until": "2026-07-17"}
    assert params["breakdowns"] == ["publisher_platform", "platform_position"]
    assert params["time_increment"] == 1


def test_insights_reject_invalid_date_range_before_api_call(tools):
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=_FakeMetaClient()) as get_client:
        result = _call(
            tools,
            "meta_get_insights",
            account_id="123",
            since="2026-07-17",
            until="2026-07-01",
        )

    assert result["error"] is True
    assert "since cannot be later" in result["message"]
    assert get_client.return_value.calls == []


def test_preview_verifies_ad_ownership_and_requests_reels_format(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_get_ad_preview",
            account_id="123",
            ad_id="3001",
            ad_format="facebook_reels_mobile",
        )

    assert result["ad_format"] == "FACEBOOK_REELS_MOBILE"
    assert "iframe" in result["previews"][0]["body"]
    assert [call["path"] for call in client.calls] == ["3001", "3001/previews"]


@pytest.mark.parametrize(
    ("tool_name", "id_argument", "resource_id", "status_attribute"),
    [
        ("meta_set_campaign_status", "campaign_id", "1001", "campaign_status"),
        ("meta_set_ad_set_status", "ad_set_id", "2001", "ad_set_status"),
        ("meta_set_ad_status", "ad_id", "3001", "ad_status"),
    ],
)
def test_status_dry_runs_never_post(tools, tool_name, id_argument, resource_id, status_attribute):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            tool_name,
            account_id="123",
            status="ACTIVE",
            confirm=False,
            **{id_argument: resource_id},
        )

    assert result["warning"] is True
    assert result["plan"]["new_status"] == "ACTIVE"
    assert getattr(client, status_attribute) == "PAUSED"
    assert [call["method"] for call in client.calls] == ["GET"]


@pytest.mark.parametrize(
    ("tool_name", "id_argument", "resource_id", "status_attribute"),
    [
        ("meta_set_campaign_status", "campaign_id", "1001", "campaign_status"),
        ("meta_set_ad_set_status", "ad_set_id", "2001", "ad_set_status"),
        ("meta_set_ad_status", "ad_id", "3001", "ad_status"),
    ],
)
def test_confirmed_status_changes_are_read_back(tools, tool_name, id_argument, resource_id, status_attribute):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            tool_name,
            account_id="123",
            status="ACTIVE",
            confirm=True,
            **{id_argument: resource_id},
        )

    assert result["updated"] is True
    assert result["verified"] is True
    assert getattr(client, status_attribute) == "ACTIVE"
    assert [call["method"] for call in client.calls] == ["GET", "POST", "GET"]


def test_status_tools_do_not_expose_delete(tools):
    with patch("burnr8.tools.meta_management.get_meta_client") as get_client:
        result = _call(
            tools,
            "meta_set_campaign_status",
            account_id="123",
            campaign_id="1001",
            status="DELETED",
            confirm=True,
        )

    assert result["error"] is True
    assert "Deletion" in result["message"]
    get_client.assert_not_called()


def test_resource_ownership_mismatch_blocks_mutation(tools):
    client = _FakeMetaClient(account_id="999")
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_set_ad_status",
            account_id="123",
            ad_id="3001",
            status="ACTIVE",
            confirm=True,
        )

    assert result["error"] is True
    assert "belongs to Meta ad account 999" in result["message"]
    assert [call["method"] for call in client.calls] == ["GET"]


def test_status_update_does_not_claim_success_when_read_back_disagrees(tools):
    client = _FakeMetaClient(persist_updates=False)
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_set_campaign_status",
            account_id="123",
            campaign_id="1001",
            status="ACTIVE",
            confirm=True,
        )

    assert result["error"] is True
    assert "could not be verified" in result["message"]
    assert [call["method"] for call in client.calls] == ["GET", "POST", "GET"]


def test_budget_dry_run_reports_large_change_without_posting(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_update_ad_set_budget",
            account_id="123",
            ad_set_id="2001",
            daily_budget_dollars=50,
            confirm=False,
        )

    assert result["warning"] is True
    assert result["plan"]["current_daily_budget_dollars"] == 25
    assert result["plan"]["new_daily_budget_dollars"] == 50
    assert result["plan"]["large_change_warning"] is True
    assert [call["method"] for call in client.calls] == ["GET", "GET"]


def test_budget_hard_cap_failure_stops_before_loading_credentials(tools):
    with (
        patch("burnr8.tools.meta_management.validate_daily_budget", return_value="Daily budget exceeds safety cap"),
        patch("burnr8.tools.meta_management.get_meta_client") as get_client,
    ):
        result = _call(
            tools,
            "meta_update_ad_set_budget",
            account_id="123",
            ad_set_id="2001",
            daily_budget_dollars=500,
            confirm=True,
        )

    assert result["error"] is True
    assert "safety cap" in result["message"]
    get_client.assert_not_called()


def test_confirmed_budget_update_uses_minor_units_and_verifies_read_back(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_update_ad_set_budget",
            account_id="123",
            ad_set_id="2001",
            daily_budget_dollars=30.25,
            confirm=True,
        )

    assert result["updated"] is True
    assert result["verified"] is True
    assert result["effective_daily_budget_dollars"] == 30.25
    post = next(call for call in client.calls if call["method"] == "POST")
    assert post["params"] == {"daily_budget": 3025}
    assert [call["method"] for call in client.calls] == ["GET", "GET", "POST", "GET"]


def test_budget_uses_the_same_half_up_rounding_in_plan_and_mutation(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_update_ad_set_budget",
            account_id="123",
            ad_set_id="2001",
            daily_budget_dollars=30.255,
            confirm=False,
        )

    assert result["plan"]["new_daily_budget_dollars"] == 30.26


def test_budget_update_does_not_claim_success_when_read_back_disagrees(tools):
    client = _FakeMetaClient(persist_updates=False)
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_update_ad_set_budget",
            account_id="123",
            ad_set_id="2001",
            daily_budget_dollars=30,
            confirm=True,
        )

    assert result["error"] is True
    assert "could not be verified" in result["message"]
    assert [call["method"] for call in client.calls] == ["GET", "GET", "POST", "GET"]


def test_budget_update_rejects_campaign_or_lifetime_budget_mode(tools):
    client = _FakeMetaClient(has_daily_budget=False)
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_update_ad_set_budget",
            account_id="123",
            ad_set_id="2001",
            daily_budget_dollars=30,
            confirm=True,
        )

    assert result["error"] is True
    assert "campaign-level or lifetime budget" in result["message"]
    assert [call["method"] for call in client.calls] == ["GET"]


def test_budget_update_rejects_non_usd_account_before_post(tools):
    client = _FakeMetaClient(currency="GBP")
    with patch("burnr8.tools.meta_management.get_meta_client", return_value=client):
        result = _call(
            tools,
            "meta_update_ad_set_budget",
            account_id="123",
            ad_set_id="2001",
            daily_budget_dollars=30,
            confirm=True,
        )

    assert result["error"] is True
    assert "uses GBP" in result["message"]
    assert [call["method"] for call in client.calls] == ["GET", "GET"]
