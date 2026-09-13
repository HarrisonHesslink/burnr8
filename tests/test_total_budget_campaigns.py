"""Total budgets and finite campaign dates use real Google Ads request protos."""

import importlib
import json

import pytest
from google.ads.googleads.client import GoogleAdsClient


def tool(module, name):
    captured = {}

    class Capture:
        def tool(self, fn):
            captured[fn.__name__] = fn
            return fn

    importlib.import_module(f"burnr8.tools.{module}").register(Capture())
    return captured[name]


@pytest.fixture
def client(mock_ads_client):
    client = mock_ads_client["client"]
    # Only message types and enums are used; all service calls remain mocked.
    real = GoogleAdsClient(credentials=None, developer_token="test-only", use_proto_plus=True, version="v23")  # noqa: S106
    client.get_type = real.get_type
    client._enums = real.enums
    client.get_service("CampaignBudgetService").campaign_budget_path.side_effect = (
        lambda cid, bid: f"customers/{cid}/campaignBudgets/{bid}"
    )
    client.get_service("CampaignService").campaign_path.side_effect = lambda cid, cid2: f"customers/{cid}/campaigns/{cid2}"
    return client


@pytest.mark.parametrize("period,amount_field", [("DAILY", "amount_micros"), ("CUSTOM_PERIOD", "total_amount_micros")])
@pytest.mark.parametrize("confirm", [False, True])
def test_budget_creation_uses_one_amount_field_and_validate_only(client, period, amount_field, confirm):
    result = tool("budgets", "create_budget")(
        name="Bounded pilot",
        amount_dollars=50,
        period=period,
        customer_id="1234567890",
        confirm=confirm,
    )
    assert not result.get("error"), result
    request = client.get_service("CampaignBudgetService").mutate_campaign_budgets.call_args.kwargs["request"]
    assert request.validate_only is not confirm
    budget = request.operations[0].create
    assert budget.period.name == period
    assert not budget.explicitly_shared
    assert getattr(budget, amount_field) == 50_000_000
    other_field = "amount_micros" if period == "CUSTOM_PERIOD" else "total_amount_micros"
    assert not budget._pb.HasField(other_field)


@pytest.mark.parametrize("confirm", [False, True])
def test_total_budget_update_does_not_write_daily_amount_or_change_type(client, confirm):
    result = tool("budgets", "update_budget")(
        budget_id="501",
        amount_dollars=50,
        period="CUSTOM_PERIOD",
        customer_id="1234567890",
        confirm=confirm,
    )
    assert not result.get("error"), result
    request = client.get_service("CampaignBudgetService").mutate_campaign_budgets.call_args.kwargs["request"]
    assert request.validate_only is not confirm
    op = request.operations[0]
    assert list(op.update_mask.paths) == ["total_amount_micros"]
    assert op.update.total_amount_micros == 50_000_000
    assert not op.update._pb.HasField("amount_micros")
    assert op.update.period.name == "UNSPECIFIED"
    if not confirm:
        assert "$50.00 total" in result["message"]


def test_total_budget_listing_distinguishes_total_from_daily(mock_ads_client):
    mock_ads_client["set_gaql"](
        {
            "FROM campaign_budget": [
                {
                    "campaign_budget": {
                        "id": "501",
                        "period": "CUSTOM_PERIOD",
                        "amount_micros": "0",
                        "total_amount_micros": "50000000",
                    }
                }
            ]
        }
    )
    result = tool("budgets", "list_budgets")(customer_id="1234567890")
    assert result[0]["amount_dollars"] == 50
    assert result[0]["period"] == "CUSTOM_PERIOD"


@pytest.mark.parametrize("period", ["CUSTOM_PERIOD", "DAILY", "INVALID"])
def test_invalid_or_over_limit_budget_never_mutates(client, period):
    result = tool("budgets", "create_budget")(
        name="Rejected",
        amount_dollars=float("inf") if period != "INVALID" else 50,
        period=period,
        customer_id="1234567890",
        confirm=True,
    )
    assert result.get("error"), result
    client.get_service("CampaignBudgetService").mutate_campaign_budgets.assert_not_called()


@pytest.mark.parametrize("period", ["DAILY", "CUSTOM_PERIOD"])
@pytest.mark.parametrize("name", ["create_budget", "update_budget"])
def test_finite_budget_above_configured_cap_never_mutates(client, monkeypatch, period, name):
    monkeypatch.setattr("burnr8.helpers.get_max_daily_budget", lambda: 50)
    arguments = {"name": "Rejected"} if name == "create_budget" else {"budget_id": "501"}
    result = tool("budgets", name)(
        **arguments, amount_dollars=51, period=period, customer_id="1234567890", confirm=True
    )
    assert result.get("error"), result
    client.get_service("CampaignBudgetService").mutate_campaign_budgets.assert_not_called()


@pytest.fixture
def campaign_budget_rows():
    return [
        {
            "campaign": {"id": "1", "name": "Daily campaign"},
            "campaign_budget": {"period": "DAILY", "amount_micros": "8000000"},
            "metrics": {"cost_micros": "1000000"},
        },
        {
            "campaign": {"id": "2", "name": "Total campaign"},
            "campaign_budget": {
                "period": "CUSTOM_PERIOD", "amount_micros": "0", "total_amount_micros": "50000000"
            },
            "metrics": {"cost_micros": "1000000"},
        },
    ]


def test_quick_audit_reports_daily_and_total_budgets(mock_ads_client, campaign_budget_rows):
    mock_ads_client["set_gaql"]({"FROM campaign_budget": campaign_budget_rows})
    result = tool("compound", "quick_audit")(customer_id="1234567890")
    assert not result.get("error"), result
    budgets = result["top_budgets"]
    assert [(b["amount_dollars"], b["period"]) for b in budgets] == [(8, "DAILY"), (50, "CUSTOM_PERIOD")]


def test_structure_distinguishes_total_from_daily_budget(monkeypatch, campaign_budget_rows):
    from burnr8.server import account_structure

    def query(client, cid, sql):
        if "FROM campaign" in sql:
            assert "campaign_budget.total_amount_micros" in sql
            assert "campaign_budget.period" in sql
            return campaign_budget_rows
        return []

    monkeypatch.setattr("burnr8.client.get_client", lambda: object())
    monkeypatch.setattr("burnr8.helpers.run_gaql", query)
    result = json.loads(account_structure("1234567890"))
    assert "error" not in result, result
    daily, total = result["campaigns"]
    assert (daily["daily_budget"], daily["total_budget"], daily["budget_period"]) == (8, None, "DAILY")
    assert (total["daily_budget"], total["total_budget"], total["budget_period"]) == (None, 50, "CUSTOM_PERIOD")


def test_dashboard_labels_total_and_daily_budgets(monkeypatch, capsys, campaign_budget_rows):
    from burnr8.dashboard import print_dashboard

    stats = {"ops_pct": 0, "ops_today": 0, "ops_limit": 15000, "errors_today": 0, "recent_calls": []}

    def query(client, cid, sql):
        if "FROM campaign_budget" in sql:
            assert "campaign_budget.total_amount_micros" in sql
            assert "campaign_budget.period" in sql
        return campaign_budget_rows

    monkeypatch.setattr("burnr8.dashboard.load_dotenv", lambda: None)
    monkeypatch.setattr("burnr8.logging.get_usage_stats", lambda: stats)
    monkeypatch.setattr("burnr8.reports.get_storage_stats", lambda: {})
    monkeypatch.setattr("burnr8.client.get_client", lambda: object())
    monkeypatch.setattr("burnr8.dashboard._get_customer_id", lambda: "1234567890")
    monkeypatch.setattr("burnr8.helpers.run_gaql", query)
    print_dashboard()
    output = capsys.readouterr().out
    assert "$8.00 daily budget" in output
    assert "$50.00 campaign total budget" in output
    assert "Could not load campaign data" not in output


@pytest.mark.parametrize("confirm", [False, True])
def test_finite_campaign_stays_paused_and_preserves_account_timezone_dates(client, confirm):
    result = tool("campaigns", "create_campaign")(
        name="Bounded pilot",
        budget_id="501",
        bidding_strategy="MAXIMIZE_CLICKS",
        start_date_time="2030-01-01 00:00:00",
        end_date_time="2030-01-05 23:59:59",
        customer_id="1234567890",
        confirm=confirm,
    )
    assert not result.get("error"), result
    request = client.get_service("CampaignService").mutate_campaigns.call_args.kwargs["request"]
    assert request.validate_only is not confirm
    campaign = request.operations[0].create
    assert campaign.status.name == "PAUSED"
    assert campaign.start_date_time == "2030-01-01 00:00:00"
    assert campaign.end_date_time == "2030-01-05 23:59:59"
    assert campaign._pb.HasField("target_spend")


def test_campaign_end_update_only_changes_requested_date(client):
    result = tool("campaigns", "update_campaign")(
        campaign_id="111",
        end_date_time="2030-01-05 23:59:59",
        customer_id="1234567890",
        confirm=False,
    )
    assert not result.get("error"), result
    request = client.get_service("CampaignService").mutate_campaigns.call_args.kwargs["request"]
    assert request.validate_only
    assert list(request.operations[0].update_mask.paths) == ["end_date_time"]
    assert request.operations[0].update.end_date_time == "2030-01-05 23:59:59"


@pytest.mark.parametrize(
    "start,end",
    [
        ("2030-02-30 00:00:00", "2030-03-05 23:59:59"),
        ("2030-01-05 00:00:00", "2030-01-01 23:59:59"),
        ("2030-01-01 00:00:00", "2030-01-01 00:00:00"),
        ("2030-01-01T00:00:00Z", "2030-01-05 23:59:59"),
    ],
)
def test_invalid_campaign_dates_never_mutate(client, start, end):
    result = tool("campaigns", "create_campaign")(
        name="Rejected",
        budget_id="501",
        start_date_time=start,
        end_date_time=end,
        customer_id="1234567890",
        confirm=True,
    )
    assert result.get("error"), result
    client.get_service("CampaignService").mutate_campaigns.assert_not_called()
