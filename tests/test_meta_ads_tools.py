"""Behavior tests for Meta Ads MCP tools."""

from pathlib import Path
from unittest.mock import patch

import pytest

from burnr8.meta.client import MetaAdsApiError
from burnr8.tools.meta_ads import register


class _Capture:
    def __init__(self):
        self.tools = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


class _FakeMetaClient:
    def __init__(self, *, fail_path: str | None = None, currency: str = "USD"):
        self.calls = []
        self.fail_path = fail_path
        self.currency = currency
        self._image_index = 0
        self._creative_index = 0
        self._ad_index = 0

    def request(self, method, path, *, params=None, files=None):
        recorded_files = None
        if files:
            name, handle, content_type = files["filename"]
            recorded_files = {"filename": name, "content_type": content_type, "bytes": handle.read()}
        self.calls.append({"method": method, "path": path, "params": params, "files": recorded_files})
        if path == self.fail_path:
            raise MetaAdsApiError("Rejected creative", status_code=400, code=100, trace_id="trace")
        if path == "me/adaccounts":
            return {"data": [{"id": "act_123", "account_id": "123", "name": "StudyWithLily"}]}
        if path.endswith("/promote_pages"):
            return {"data": [{"id": "456", "name": "StudyWithLily"}]}
        if path.endswith("/connected_instagram_accounts"):
            return {"data": [{"id": "789", "username": "studywithlily"}]}
        if path == "act_123":
            return {
                "id": "act_123",
                "account_id": "123",
                "name": "StudyWithLily",
                "account_status": 1,
                "currency": self.currency,
            }
        if path.endswith("/adimages"):
            self._image_index += 1
            return {
                "images": {
                    f"photo-{self._image_index}.png": {
                        "hash": f"hash-{self._image_index}",
                        "name": f"photo-{self._image_index}.png",
                        "url": f"https://cdn.test/{self._image_index}",
                        "width": 1080,
                        "height": 1920,
                    }
                }
            }
        if path.endswith("/campaigns"):
            return {"id": "1001"}
        if path.endswith("/adsets"):
            return {"id": "2001"}
        if path.endswith("/adcreatives"):
            self._creative_index += 1
            return {"id": str(3000 + self._creative_index)}
        if path.endswith("/ads"):
            self._ad_index += 1
            return {"id": str(4000 + self._ad_index)}
        raise AssertionError(f"Unexpected request: {method} {path}")


@pytest.fixture
def tools():
    capture = _Capture()
    register(capture)
    return capture.tools


def _write_png(path: Path, width: int = 1080, height: int = 1920) -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )
    return path


def _campaign_args(photos):
    return {
        "campaign_name": "StudyWithLily Reels",
        "image_paths": [str(photo) for photo in photos],
        "page_id": "456",
        "instagram_user_id": "789",
        "landing_url": "https://studywithlily.com/daily",
        "primary_text": "Turn revision into a daily habit.",
        "headline": "Study smarter with Lily",
        "daily_budget_dollars": 25.0,
        "account_id": "act_123",
    }


def test_dry_run_validates_without_credentials_or_api_calls(tools, tmp_path):
    photo = _write_png(tmp_path / "lily.png")
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}, clear=False),
        patch("burnr8.tools.meta_ads.get_meta_client") as get_client,
    ):
        result = tools["meta_create_reels_campaign"](**_campaign_args([photo]))

    assert result["warning"] is True
    assert result["validated"] == "client_side"
    assert result["plan"]["objects_to_create"] == {"campaigns": 1, "ad_sets": 1, "creatives": 1, "ads": 1}
    assert result["plan"]["initial_status"] == "PAUSED"
    get_client.assert_not_called()


def test_upload_requires_confirmation(tools, tmp_path):
    photo = _write_png(tmp_path / "lily.png")
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}, clear=False),
        patch("burnr8.tools.meta_ads.get_meta_client") as get_client,
    ):
        result = tools["meta_upload_image"](str(photo), account_id="123")

    assert result["warning"] is True
    assert result["image"]["width"] == 1080
    get_client.assert_not_called()


def test_confirmed_upload_sends_multipart_file(tools, tmp_path):
    photo = _write_png(tmp_path / "lily.png")
    client = _FakeMetaClient()
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}, clear=False),
        patch("burnr8.tools.meta_ads.get_meta_client", return_value=client),
    ):
        result = tools["meta_upload_image"](str(photo), confirm=True, account_id="123")

    assert result["uploaded"] is True
    assert result["image"]["image_hash"] == "hash-1"
    call = client.calls[0]
    assert call["path"] == "act_123/adimages"
    assert call["files"]["filename"] == "lily.png"
    assert call["files"]["bytes"].startswith(b"\x89PNG")


def test_creates_paused_reels_campaign_with_one_ad_per_photo(tools, tmp_path):
    photos = [_write_png(tmp_path / f"lily-{index}.png") for index in (1, 2)]
    client = _FakeMetaClient()
    args = _campaign_args(photos)
    args.update(
        {
            "countries": ["US", "GB"],
            "url_tags": "utm_source=meta&utm_medium=paid_social",
            "confirm": True,
        }
    )
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}, clear=False),
        patch("burnr8.tools.meta_ads.get_meta_client", return_value=client),
    ):
        result = tools["meta_create_reels_campaign"](**args)

    assert result["created"] is True
    assert result["status"] == "PAUSED"
    assert result["campaign"]["campaign_id"] == "1001"
    assert result["campaign"]["ad_set_id"] == "2001"
    assert result["campaign"]["ad_ids"] == ["4001", "4002"]

    campaign_call = next(call for call in client.calls if call["path"].endswith("/campaigns"))
    assert campaign_call["params"]["objective"] == "OUTCOME_TRAFFIC"
    assert campaign_call["params"]["status"] == "PAUSED"

    ad_set_call = next(call for call in client.calls if call["path"].endswith("/adsets"))
    targeting = ad_set_call["params"]["targeting"]
    assert targeting["publisher_platforms"] == ["facebook", "instagram"]
    assert targeting["facebook_positions"] == ["facebook_reels"]
    assert targeting["instagram_positions"] == ["reels"]
    assert targeting["device_platforms"] == ["mobile"]
    assert targeting["geo_locations"] == {"countries": ["US", "GB"]}
    assert ad_set_call["params"]["daily_budget"] == 2500
    assert ad_set_call["params"]["status"] == "PAUSED"

    creative_calls = [call for call in client.calls if call["path"].endswith("/adcreatives")]
    assert [call["params"]["object_story_spec"]["link_data"]["image_hash"] for call in creative_calls] == [
        "hash-1",
        "hash-2",
    ]
    assert all(
        call["params"]["degrees_of_freedom_spec"]["creative_features_spec"]["standard_enhancements"]["enroll_status"]
        == "OPT_OUT"
        for call in creative_calls
    )
    ad_calls = [call for call in client.calls if call["path"].endswith("/ads")]
    assert all(call["params"]["status"] == "PAUSED" for call in ad_calls)


def test_non_usd_account_stops_before_upload_or_mutation(tools, tmp_path):
    photo = _write_png(tmp_path / "lily.png")
    client = _FakeMetaClient(currency="GBP")
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}, clear=False),
        patch("burnr8.tools.meta_ads.get_meta_client", return_value=client),
    ):
        result = tools["meta_create_reels_campaign"](**_campaign_args([photo]), confirm=True)

    assert result["error"] is True
    assert "USD ad accounts only" in result["message"]
    assert [call["path"] for call in client.calls] == ["act_123"]


def test_partial_failure_reports_paused_objects_created_so_far(tools, tmp_path):
    photo = _write_png(tmp_path / "lily.png")
    client = _FakeMetaClient(fail_path="act_123/adcreatives")
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}, clear=False),
        patch("burnr8.tools.meta_ads.get_meta_client", return_value=client),
    ):
        result = tools["meta_create_reels_campaign"](**_campaign_args([photo]), confirm=True)

    assert result["error"] is True
    assert result["partial_failure"] is True
    assert result["created_before_failure"]["campaign_id"] == "1001"
    assert result["created_before_failure"]["ad_set_id"] == "2001"
    assert result["created_before_failure"]["ad_ids"] == []
    assert "PAUSED" in result["safety_note"]


def test_account_asset_discovery_returns_page_and_instagram_ids(tools):
    client = _FakeMetaClient()
    with patch("burnr8.tools.meta_ads.get_meta_client", return_value=client):
        result = tools["meta_get_account_assets"](account_id="123")

    assert result["facebook_pages"] == [{"id": "456", "name": "StudyWithLily"}]
    assert result["instagram_accounts"] == [{"id": "789", "username": "studywithlily"}]
