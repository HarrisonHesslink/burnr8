"""Creation workflow, ownership, financial limits and interrupted-write recovery."""

import asyncio
import contextvars
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import requests
from fastmcp import Client, FastMCP

from burnr8.reddit.client import RedditAdsApiError, validate_page_url
from burnr8.reddit.helpers import requested_fields_match
from burnr8.tools.reddit_creation import register

PROFILE = "t2_profile"
IMAGE = "t2_profile-IMAGE-1"
VIDEO = "t2_profile-VIDEO-2"
DESTINATION = "https://example.com/nclex?utm_source=reddit&utm_medium=paid_social&utm_campaign=pilot"
GROUP_ARGS = {
    "name": "Nursing students",
    "campaign_id": "123",
    "daily_budget_dollars": 5,
    "conversion_pixel_id": "p2_pixel",
    "geolocations": ["US"],
    "starts_at": "2099-09-10T00:00:00Z",
    "ends_at": "2099-09-17T00:00:00Z",
    "communities": ["StudentNurse"],
}
UPLOAD_ARGS = {
    "profile_id": PROFILE,
    "name": "Pilot image",
    "media_type": "IMAGE",
    "media_url": "https://example.com/ad.png",
}
POST_ARGS = {
    "profile_id": PROFILE,
    "headline": "Practice for the NCLEX",
    "destination_url": DESTINATION,
    "media_asset_id": IMAGE,
}
AD_ARGS = {"name": "Pilot ad", "ad_group_id": "234", "profile_id": PROFILE, "post_id": "t3_post"}


class FakeCreation:
    def __init__(self):
        self.calls = []
        self.fail_write = None
        self.fail_readback = False
        self.malformed_ack = False
        self.wrote = False
        self.profiles = [{"id": PROFILE}]
        self.pixels = [{"id": "p2_pixel"}]
        self.account = {"id": "a2_test", "currency": "USD"}
        self.assets = {
            IMAGE: {
                "id": IMAGE,
                "type": "IMAGE",
                "status": "ACTIVE",
                "media": {"permanent_url": "https://i.redd.it/image.png"},
            },
            VIDEO: {
                "id": VIDEO,
                "type": "VIDEO",
                "status": "ACTIVE",
                "media": {"permanent_url": "https://v.redd.it/video.mp4"},
                "poster": {"permanent_url": "https://i.redd.it/poster.png"},
            },
        }
        self.resources = {
            "campaigns/123": {
                "id": "123",
                "ad_account_id": "a2_test",
                "type": "MANUAL",
                "objective": "CLICKS",
                "is_campaign_budget_optimization": False,
            },
            "ad_groups/234": {"id": "234", "ad_account_id": "a2_test", "campaign_id": "123", "type": "MANUAL"},
            "structured_posts/t3_post": {
                "id": "t3_post",
                "profile_id": PROFILE,
                "url": "https://www.reddit.com/comments/post",
                "allow_comments": False,
                "creative": {
                    "type": "IMAGE",
                    "headline": "Practice for the NCLEX",
                    "destination": {"type": "URL", "url": DESTINATION},
                },
            },
        }
        self.upload = {"id": "upload123", "status": "ACTIVE", "result": self.assets[IMAGE]}
        self.job = {"id": "job123", "status": "SUCCESS", "post_id": "t3_post", "error_message": None}

    def request(self, method, path, *, params=None, body=None, next_url=None):
        self.calls.append(
            {"method": method, "path": path, "params": params, "body": deepcopy(body), "next_url": next_url}
        )
        if method == "POST":
            if self.fail_write:
                raise self.fail_write
            self.wrote = True
            if self.malformed_ack:
                return {"data": {}}
            if path.endswith("/creative_assets/uploads"):
                return {"data": [{"id": "upload123", "reference_id": body["data"][0]["reference_id"]}]}
            if path.endswith("/structured_posts/jobs"):
                self.resources["structured_posts/t3_post"].update(deepcopy(body["data"]))
                return {"data": {"id": "job123", "status": "QUEUED"}}
            kind = path.rsplit("/", 1)[-1]
            data = {"id": "500", "ad_account_id": "a2_test", **deepcopy(body["data"])}
            if kind == "ad_groups":
                data["targeting"]["platforms"] = ["ALL"]
                data["start_time"] = data["start_time"].replace("Z", ".000000+00:00")
            if kind == "ads":
                data["preview_url"] = "https://www.reddit.com/?ad=preview"
                data["preview_expiry"] = data["preview_expiry"].replace("Z", "+00:00")
            self.resources[f"{kind}/500"] = data
            return {"data": deepcopy(data)}
        assert method == "GET"
        if self.wrote and self.fail_readback:
            raise requests.Timeout("private provider value")
        if path == "ad_accounts/a2_test":
            data = self.account
        elif path.endswith("/profiles"):
            data = self.profiles
        elif path.endswith("/pixels"):
            data = self.pixels
        elif path.endswith("/creative_assets/uploads"):
            data = [self.upload]
        elif path.endswith("/creative_assets"):
            data = [
                {"result": value}
                for key, value in self.assets.items()
                if not params.get("creative_asset_ids") or key in params["creative_asset_ids"]
            ]
        elif path == "structured_posts/jobs/job123":
            data = self.job
        elif path.endswith("/structured_posts"):
            data = [self.resources["structured_posts/t3_post"]]
        else:
            data = self.resources[path]
        return {"data": deepcopy(data), "pagination": {"next_url": None}}


@pytest.fixture
def creation(monkeypatch):
    fake = FakeCreation()
    monkeypatch.setenv("REDDIT_AD_ACCOUNT_ID", "a2_test")
    monkeypatch.setattr("burnr8.tools.reddit_creation.get_reddit_client", lambda: fake)
    monkeypatch.setattr("burnr8.tools.reddit_ads.get_reddit_client", lambda: fake)
    monkeypatch.setattr("burnr8.reddit.errors.log_tool_call", MagicMock())
    funcs = {}
    capture = MagicMock()
    capture.tool.side_effect = lambda fn: funcs.setdefault(fn.__name__, fn)
    register(capture)
    return funcs, fake


def writes(fake):
    return [call for call in fake.calls if call["method"] != "GET"]


@pytest.mark.parametrize(
    "tool,args",
    [
        ("reddit_create_ad_group", GROUP_ARGS),
        ("reddit_upload_media", UPLOAD_ARGS),
        ("reddit_create_ad_post", POST_ARGS),
        ("reddit_create_ad", AD_ARGS),
    ],
)
def test_all_creation_defaults_to_reviewable_preview_without_writes(creation, tool, args):
    funcs, fake = creation
    result = funcs[tool](**args)
    assert result["warning"] and result["validated"] == "local_and_account_read"
    assert result["plan"]["request"]["data"]
    assert not writes(fake)


def test_ad_group_saves_paused_targeting_budget_and_equivalent_readback(creation):
    funcs, fake = creation
    result = funcs["reddit_create_ad_group"](**GROUP_ARGS, confirm=True)
    assert result["created"] and result["verified"] and result["resource_id"] == "500"
    saved = writes(fake)[0]["body"]["data"]
    assert saved["configured_status"] == "PAUSED"
    assert saved["goal_value"] == 5_000_000 and saved["goal_type"] == "DAILY_SPEND"
    assert saved["bid_strategy"] == "BIDLESS" and saved["bid_type"] == "CPC"
    assert saved["conversion_pixel_id"] == "p2_pixel"
    assert saved["targeting"] == {
        "geolocations": ["US"],
        "locations": ["FEED"],
        "expand_targeting": False,
        "communities": ["StudentNurse"],
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"daily_budget_dollars": float("nan")},
        {"daily_budget_dollars": float("inf")},
        {"daily_budget_dollars": 0},
        {"daily_budget_dollars": -1},
        {"geolocations": []},
        {"communities": []},
        {"communities": ["r/StudentNurse"]},
        {"excluded_communities": ["studentnurse"]},
        {"placements": []},
        {"placements": ["CONVERSATION"]},
        {"placements": ["FEED", "FEED"]},
        {"starts_at": "2099-09-10"},
        {"starts_at": "2099-09-10T00:00:00-07:00"},
        {"ends_at": "2099-09-01T00:00:00Z"},
        {"ends_at": "2000-09-17T00:00:00Z"},
        {"name": ""},
    ],
)
def test_invalid_groups_fail_before_provider_calls(creation, changes):
    funcs, fake = creation
    assert funcs["reddit_create_ad_group"](**(GROUP_ARGS | changes), confirm=True)["error"]
    assert not fake.calls


@pytest.mark.parametrize("mode", ["foreign_campaign", "currency", "cbo", "unknown_budget", "pixel", "objective"])
def test_incompatible_or_unowned_ad_group_prerequisites_cannot_write(creation, mode):
    funcs, fake = creation
    campaign = fake.resources["campaigns/123"]
    if mode == "foreign_campaign":
        campaign["ad_account_id"] = "a2_other"
    elif mode == "currency":
        fake.account["currency"] = "EUR"
    elif mode == "cbo":
        campaign["is_campaign_budget_optimization"] = True
    elif mode == "unknown_budget":
        del campaign["is_campaign_budget_optimization"]
    elif mode == "pixel":
        fake.pixels = []
    else:
        campaign["objective"] = "APP_INSTALLS"
    assert funcs["reddit_create_ad_group"](**GROUP_ARGS, confirm=True)["error"]
    assert not writes(fake)


def test_budget_and_cpc_caps_apply_in_request_context(creation):
    from burnr8.session import set_financial_limits

    funcs, fake = creation
    context = contextvars.copy_context()
    context.run(set_financial_limits, max_daily_budget=4, max_cpc_bid=0.5)
    assert context.run(funcs["reddit_create_ad_group"], **GROUP_ARGS, confirm=True)["error"]
    context.run(set_financial_limits, max_daily_budget=10, max_cpc_bid=0.5)
    assert context.run(funcs["reddit_create_ad_group"], **GROUP_ARGS, bid_dollars=0.51, confirm=True)["error"]
    assert not writes(fake)


def test_conversion_goal_is_explicit_and_legacy_removed_goals_are_rejected(creation):
    funcs, fake = creation
    fake.resources["campaigns/123"]["objective"] = "CONVERSIONS"
    for goal in (None, "VIEW_CONTENT", "SEARCH", "ADD_TO_WISHLIST", "CLICKS"):
        assert funcs["reddit_create_ad_group"](**GROUP_ARGS, optimization_goal=goal, confirm=True)["error"]
    assert not writes(fake)
    result = funcs["reddit_create_ad_group"](**GROUP_ARGS, optimization_goal="SIGN_UP", confirm=True)
    assert result["verified"]
    assert writes(fake)[0]["body"]["data"]["optimization_goal"] == "SIGN_UP"


def test_manual_cpc_and_cpm_bid_units_and_limits(creation):
    funcs, fake = creation
    result = funcs["reddit_create_ad_group"](**GROUP_ARGS, bid_dollars=0.75)
    assert result["plan"]["request"]["data"]["bid_value"] == 750_000
    fake.resources["campaigns/123"]["objective"] = "IMPRESSIONS"
    for bid in (None, float("inf"), float("nan"), 0, 3.49, 100.01):
        assert funcs["reddit_create_ad_group"](**GROUP_ARGS, bid_dollars=bid, confirm=True)["error"]
    assert not writes(fake)
    result = funcs["reddit_create_ad_group"](**GROUP_ARGS, bid_dollars=3.5, confirm=True)
    assert result["verified"]
    saved = writes(fake)[0]["body"]["data"]
    assert saved["bid_type"] == "CPM" and saved["bid_strategy"] == "MANUAL_BIDDING" and saved["bid_value"] == 3_500_000


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/ad.png",
        "/tmp/ad.png",
        "file:///home/user/.env",
        "data:image/png;base64,abc",
        "https://user:secret@example.com/ad.png",
        "https://localhost/ad.png",
        "https://localhost./ad.png",
        "https://service.local/ad.png",
        "https://127.0.0.1/ad.png",
        "https://127.1/ad.png",
        "https://169.254.169.254/ad.png",
        "https://[::1]/ad.png",
        "https://example.com:8443/ad.png",
        "https://example.com:bad/ad.png",
        "https://example.com/ad.png#fragment",
        "https://example.com/ad.png\n",
        "https://example.com\\@evil.com/ad.png",
    ],
)
def test_media_url_rejects_local_files_and_unsafe_urls_without_requests(creation, url):
    funcs, fake = creation
    result = funcs["reddit_upload_media"](**(UPLOAD_ARGS | {"media_url": url}), confirm=True)
    assert result["error"] and "secret" not in str(result)
    assert not fake.calls


def test_upload_is_asynchronous_and_uses_json_url_import(creation):
    funcs, fake = creation
    result = funcs["reddit_upload_media"](**UPLOAD_ARGS, confirm=True)
    assert result["submitted"] and not result["verified"] and result["upload_id"] == "upload123"
    request = writes(fake)[0]
    assert request["path"] == f"profiles/{PROFILE}/creative_assets/uploads"
    assert request["body"]["data"][0]["media"] == {"type": "URL", "url": UPLOAD_ARGS["media_url"]}
    assert request["body"]["data"][0]["reference_id"] == result["reference_id"]
    fake.upload["status"] = "PROCESSING_MEDIA"
    pending = funcs["reddit_get_media_upload"](PROFILE, "upload123")
    assert pending["pending"] and not pending["ready"]
    fake.upload["status"] = "ACTIVE"
    ready = funcs["reddit_get_media_upload"](PROFILE, "upload123")
    assert ready["ready"] and ready["verified"] and ready["asset"]["id"] == IMAGE
    assert len(writes(fake)) == 1


@pytest.mark.parametrize(
    "changes", [{"media_type": "VIDEO"}, {"poster_url": "https://example.com/poster.png"}, {"media_type": "GIF"}]
)
def test_media_type_and_poster_must_match(creation, changes):
    funcs, fake = creation
    assert funcs["reddit_upload_media"](**(UPLOAD_ARGS | changes), confirm=True)["error"]
    assert not fake.calls


def test_video_import_requires_poster_and_post_uses_processed_poster(creation):
    funcs, fake = creation
    result = funcs["reddit_upload_media"](
        **(UPLOAD_ARGS | {"media_type": "VIDEO", "poster_url": "https://example.com/poster.png"}), confirm=True
    )
    assert result["submitted"]
    assert writes(fake)[0]["body"]["data"][0]["poster"]["type"] == "URL"
    result = funcs["reddit_create_ad_post"](**(POST_ARGS | {"media_asset_id": VIDEO}))
    creative = result["plan"]["request"]["data"]["creative"]
    assert creative["type"] == "VIDEO"
    assert creative["video"]["media"]["url"] == "https://v.redd.it/video.mp4"
    assert creative["thumbnail"]["media"]["url"] == "https://i.redd.it/poster.png"


@pytest.mark.parametrize(
    "mode", ["foreign_profile", "foreign_asset", "processing_asset", "wrong_thumbnail", "missing_media"]
)
def test_unowned_or_unusable_media_cannot_create_posts(creation, mode):
    funcs, fake = creation
    args = POST_ARGS.copy()
    if mode == "foreign_profile":
        fake.profiles = []
    elif mode == "foreign_asset":
        del fake.assets[IMAGE]
    elif mode == "processing_asset":
        fake.assets[IMAGE]["status"] = "PROCESSING_MEDIA"
    elif mode == "wrong_thumbnail":
        args["thumbnail_asset_id"] = VIDEO
    else:
        del fake.assets[IMAGE]["media"]
    assert funcs["reddit_create_ad_post"](**args, confirm=True)["error"]
    assert not writes(fake)


def test_post_creation_preserves_destination_comments_and_reviewed_creative(creation):
    funcs, fake = creation
    result = funcs["reddit_create_ad_post"](**POST_ARGS, call_to_action="Sign Up", confirm=True)
    assert result["submitted"] and result["job_id"] == "job123" and not result["verified"]
    data = writes(fake)[0]["body"]["data"]
    assert data["allow_comments"] is False
    assert data["creative"]["destination"] == {"type": "URL", "url": DESTINATION, "call_to_action": "Sign Up"}
    assert data["creative"]["enhancements"]["user_generated_content"]["enroll_status"] == "OPT_OUT"
    fake.job["status"] = "PROCESSING"
    assert funcs["reddit_get_ad_post_job"](PROFILE, "job123")["pending"]
    fake.job["status"] = "SUCCESS"
    result = funcs["reddit_get_ad_post_job"](PROFILE, "job123")
    assert result["verified"] and result["ready"] and result["post_id"] == "t3_post"
    assert len(writes(fake)) == 1


@pytest.mark.parametrize("status", ["CLIENT_ERROR", "SERVER_ERROR", "UNEXPECTED"])
def test_failed_jobs_do_not_leak_provider_errors_or_claim_ready(creation, status):
    funcs, fake = creation
    fake.job.update(status=status, error_message="private provider value")
    result = funcs["reddit_get_ad_post_job"](PROFILE, "job123")
    assert result["warning"] and not result["ready"] and "private" not in str(result)
    assert not writes(fake)


def test_successful_job_cannot_return_another_profiles_post(creation):
    funcs, fake = creation
    fake.resources["structured_posts/t3_post"]["profile_id"] = "t2_other"
    assert funcs["reddit_get_ad_post_job"](PROFILE, "job123")["error"]


def test_completed_job_retains_ids_when_post_is_not_readable_yet(creation, monkeypatch):
    funcs, fake = creation
    original = fake.request

    def fail_post(method, path, **kwargs):
        if path == "structured_posts/t3_post":
            raise RedditAdsApiError("private provider detail", 404)
        return original(method, path, **kwargs)

    monkeypatch.setattr(fake, "request", fail_post)
    result = funcs["reddit_get_ad_post_job"](PROFILE, "job123")
    assert result["warning"] and not result["ready"] and not result["verified"]
    assert result["job_id"] == "job123" and result["post_id"] == "t3_post"
    assert "private" not in str(result) and not writes(fake)


@pytest.mark.parametrize("mode", ["missing_upload", "invalid_media", "asset_pending"])
def test_upload_status_checks_id_and_processed_asset(creation, mode):
    funcs, fake = creation
    if mode == "missing_upload":
        fake.upload["id"] = "different"
    elif mode == "invalid_media":
        fake.upload["status"] = "INVALID_MEDIA"
    else:
        fake.upload["result"]["status"] = "PROCESSING_MEDIA"
    result = funcs["reddit_get_media_upload"](PROFILE, "upload123")
    assert not result.get("ready") and (result.get("error") or result.get("warning"))


def test_ad_creation_is_paused_and_uses_same_destination_with_preview_link(creation):
    funcs, fake = creation
    result = funcs["reddit_create_ad"](**AD_ARGS, confirm=True)
    assert result["created"] and result["verified"]
    saved = writes(fake)[0]["body"]["data"]
    assert saved["configured_status"] == "PAUSED" and saved["click_url"] == DESTINATION
    assert saved["post_id"] == "t3_post" and saved["profile_id"] == PROFILE
    assert result["resource"]["preview_url"].startswith("https://www.reddit.com/")
    assert len(writes(fake)) == 1


@pytest.mark.parametrize("expiry", ["2000-09-07T00:00:00Z", "2099-09-07T00:00:00Z"])
def test_preview_expiry_must_be_within_provider_window(creation, expiry):
    funcs, fake = creation
    assert funcs["reddit_create_ad"](**AD_ARGS, preview_expires_at=expiry, confirm=True)["error"]
    assert not fake.calls


def test_ad_can_be_verified_while_placement_preview_is_unavailable(creation, monkeypatch):
    funcs, fake = creation
    original = fake.request

    def no_preview(method, path, **kwargs):
        response = original(method, path, **kwargs)
        if path == "ads/500":
            response["data"].pop("preview_url", None)
        return response

    monkeypatch.setattr(fake, "request", no_preview)
    result = funcs["reddit_create_ad"](**AD_ARGS, confirm=True)
    assert result["created"] and result["verified"] and result["warning"]
    assert result["preview_url"] is None and result["post_url"] == "https://www.reddit.com/comments/post"
    assert "created paused" in result["message"] and len(writes(fake)) == 1


def test_legacy_group_without_type_uses_verified_manual_parent(creation):
    funcs, fake = creation
    del fake.resources["ad_groups/234"]["type"]
    assert funcs["reddit_create_ad"](**AD_ARGS)["warning"]
    assert not writes(fake)
    del fake.resources["campaigns/123"]["type"]
    assert funcs["reddit_create_ad"](**AD_ARGS, confirm=True)["error"]
    assert not writes(fake)


@pytest.mark.parametrize("changes", [{"type": "AUTOMATED"}, {"is_max": True}])
def test_max_campaign_cannot_receive_standard_group_or_ad(creation, changes):
    funcs, fake = creation
    fake.resources["campaigns/123"].update(changes)
    assert funcs["reddit_create_ad"](**AD_ARGS, confirm=True)["error"]
    assert funcs["reddit_create_ad_group"](**GROUP_ARGS, confirm=True)["error"]
    assert not writes(fake)


@pytest.mark.parametrize(
    "mode", ["foreign_group", "foreign_campaign", "foreign_profile", "foreign_post", "automated_group", "destination"]
)
def test_ad_ownership_and_destination_checks_prevent_writes(creation, mode):
    funcs, fake = creation
    if mode == "foreign_group":
        fake.resources["ad_groups/234"]["ad_account_id"] = "a2_other"
    elif mode == "foreign_campaign":
        fake.resources["campaigns/123"]["ad_account_id"] = "a2_other"
    elif mode == "foreign_profile":
        fake.profiles = []
    elif mode == "foreign_post":
        fake.resources["structured_posts/t3_post"]["profile_id"] = "t2_other"
    elif mode == "automated_group":
        fake.resources["ad_groups/234"]["type"] = "AUTOMATED"
    else:
        fake.resources["structured_posts/t3_post"]["creative"]["destination"]["url"] = "javascript:alert(1)"
    assert funcs["reddit_create_ad"](**AD_ARGS, confirm=True)["error"]
    assert not writes(fake)


@pytest.mark.parametrize(
    "tool,args",
    [
        ("reddit_create_ad_group", GROUP_ARGS),
        ("reddit_upload_media", UPLOAD_ARGS),
        ("reddit_create_ad_post", POST_ARGS),
        ("reddit_create_ad", AD_ARGS),
    ],
)
@pytest.mark.parametrize(
    "error,outcome",
    [(requests.Timeout("private secret"), "unknown"), (RedditAdsApiError("private secret", 403), "rejected")],
)
def test_interrupted_writes_never_retry_or_claim_success(creation, tool, args, error, outcome):
    funcs, fake = creation
    fake.fail_write = error
    result = funcs[tool](**args, confirm=True)
    assert result["error"] and result["mutation_outcome"] == outcome
    assert "private" not in str(result)
    assert len(writes(fake)) == 1


@pytest.mark.parametrize("tool,args", [("reddit_upload_media", UPLOAD_ARGS), ("reddit_create_ad_post", POST_ARGS)])
def test_acknowledged_job_without_id_does_not_invite_blind_retry(creation, tool, args):
    funcs, fake = creation
    fake.malformed_ack = True
    result = funcs[tool](**args, confirm=True)
    assert result["submitted"] and result["warning"] and not result["verified"]
    assert "before retrying" in result["message"] and len(writes(fake)) == 1


@pytest.mark.parametrize("tool,args", [("reddit_create_ad_group", GROUP_ARGS), ("reddit_create_ad", AD_ARGS)])
def test_readback_failure_preserves_created_id(creation, tool, args):
    funcs, fake = creation
    fake.fail_readback = True
    result = funcs[tool](**args, confirm=True)
    assert result["created"] and result["resource_id"] == "500" and not result["verified"]
    assert "private" not in str(result) and len(writes(fake)) == 1


def test_discovery_and_inventory_are_account_scoped(creation):
    funcs, fake = creation
    assert funcs["reddit_list_profiles"](page_size=1000)["data"] == fake.profiles
    assert fake.calls[-1]["params"]["page.size"] == 100
    assert funcs["reddit_list_pixels"]()["data"] == fake.pixels
    assert funcs["reddit_list_creative_assets"](PROFILE)["rows"] == 2
    assert funcs["reddit_list_ad_posts"](PROFILE)["rows"] == 1
    assert fake.calls[-1]["params"]["source"] == "PROMOTED"
    fake.profiles = []
    assert funcs["reddit_list_creative_assets"](PROFILE)["error"]
    assert funcs["reddit_list_ad_posts"](PROFILE)["error"]
    assert not writes(fake)


def test_profile_link_can_be_verified_on_later_page(creation, monkeypatch):
    funcs, fake = creation
    original = fake.request

    def pages(method, path, **kwargs):
        if path.endswith("/profiles") and not kwargs.get("next_url"):
            return {
                "data": [],
                "pagination": {"next_url": f"https://ads-api.reddit.com/api/v3/{path}?page.token=second&page.size=100"},
            }
        return original(method, path, **kwargs)

    monkeypatch.setattr(fake, "request", pages)
    assert funcs["reddit_create_ad_post"](**POST_ARGS)["warning"]
    assert any(call["next_url"] for call in fake.calls)
    assert not writes(fake)


def test_new_pagination_filters_and_endpoint_limits():
    path = f"profiles/{PROFILE}/structured_posts"
    url = f"https://ads-api.reddit.com/api/v3/{path}?page.token=second&page.size=100&source=PROMOTED"
    assert validate_page_url(url, path) == url
    with pytest.raises(ValueError, match="bound"):
        validate_page_url(url.replace("page.size=100", "page.size=101"), path)


def test_readback_checks_nested_values_but_allows_provider_defaults():
    desired = {"targeting": {"communities": ["StudentNurse", "NCLEX"], "expand_targeting": False}}
    saved = {"targeting": {"communities": ["nclex", "studentnurse"], "expand_targeting": False, "platforms": ["ALL"]}}
    assert requested_fields_match(saved, desired)
    saved["targeting"]["expand_targeting"] = True
    assert not requested_fields_match(saved, desired)
    assert not requested_fields_match({"targeting": {}}, desired)
    assert not requested_fields_match(
        {"is_campaign_budget_optimization": 0}, {"is_campaign_budget_optimization": False}
    )


def test_complete_creation_workflow_through_real_fastmcp(creation):
    _, fake = creation

    async def run():
        mcp = FastMCP("reddit-creation-test")
        register(mcp)
        async with Client(mcp) as client:
            assert len(await client.list_tools()) == 11
            assert (await client.call_tool("reddit_create_ad_group", GROUP_ARGS)).data["warning"]
            assert not writes(fake)
            group = (await client.call_tool("reddit_create_ad_group", GROUP_ARGS | {"confirm": True})).data
            upload = (await client.call_tool("reddit_upload_media", UPLOAD_ARGS | {"confirm": True})).data
            asset = (
                await client.call_tool(
                    "reddit_get_media_upload", {"profile_id": PROFILE, "upload_id": upload["upload_id"]}
                )
            ).data
            post = (
                await client.call_tool(
                    "reddit_create_ad_post", POST_ARGS | {"media_asset_id": asset["asset"]["id"], "confirm": True}
                )
            ).data
            job = (
                await client.call_tool("reddit_get_ad_post_job", {"profile_id": PROFILE, "job_id": post["job_id"]})
            ).data
            ad = (
                await client.call_tool(
                    "reddit_create_ad",
                    AD_ARGS | {"ad_group_id": group["resource_id"], "post_id": job["post_id"], "confirm": True},
                )
            ).data
            assert ad["verified"] and ad["resource"]["configured_status"] == "PAUSED"
            assert ad["resource"]["click_url"] == DESTINATION
            assert len(writes(fake)) == 4

    asyncio.run(run())
