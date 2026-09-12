"""Tests for the small Meta Graph API client."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

from burnr8.meta.client import MetaAdsApiError, MetaAdsClient, get_meta_client


def _response(payload, *, status=200, ok=True):
    response = MagicMock()
    response.json.return_value = payload
    response.status_code = status
    response.ok = ok
    return response


def test_get_request_encodes_graph_params_and_appsecret_proof():
    session = MagicMock()
    session.request.return_value = _response({"data": []})
    app_secret = "secret" + "-456"
    client = MetaAdsClient("token-123", app_secret=app_secret, session=session)

    result = client.request(
        "GET",
        "me/adaccounts",
        params={"fields": "id,name", "targeting": {"countries": ["US"]}, "enabled": True},
    )

    assert result == {"data": []}
    _, url = session.request.call_args.args
    kwargs = session.request.call_args.kwargs
    assert url == "https://graph.facebook.com/v25.0/me/adaccounts"
    assert kwargs["headers"] == {"Authorization": "Bearer token-123"}
    assert kwargs["allow_redirects"] is False
    assert json.loads(kwargs["params"]["targeting"]) == {"countries": ["US"]}
    assert kwargs["params"]["enabled"] == "true"
    expected = hmac.new(b"secret-456", b"token-123", hashlib.sha256).hexdigest()
    assert kwargs["params"]["appsecret_proof"] == expected


def test_post_request_uses_form_data_and_files():
    session = MagicMock()
    session.request.return_value = _response({"id": "123"})
    client = MetaAdsClient("token", session=session)
    files = {"filename": ("photo.png", object(), "image/png")}

    client.request("POST", "act_1/adimages", params={"status": "PAUSED"}, files=files)

    kwargs = session.request.call_args.kwargs
    assert kwargs["data"] == {"status": "PAUSED"}
    assert kwargs["files"] is files
    assert "params" not in kwargs


def test_meta_error_is_sanitized_and_structured():
    session = MagicMock()
    session.request.return_value = _response(
        {
            "error": {
                "message": "Invalid parameter",
                "type": "OAuthException",
                "code": 100,
                "error_subcode": 18157520,
                "is_transient": False,
                "error_user_title": "Creative error",
                "error_user_msg": "Fix the image",
                "fbtrace_id": "trace123",
            }
        },
        status=400,
        ok=False,
    )
    client = MetaAdsClient("super-secret-token", session=session)

    with pytest.raises(MetaAdsApiError) as exc_info:
        client.request("POST", "act_1/ads")

    result = exc_info.value.as_dict()
    assert result["message"] == "Invalid parameter"
    assert result["meta_error_code"] == 100
    assert result["meta_error_subcode"] == 18157520
    assert result["trace_id"] == "trace123"
    assert "super-secret-token" not in repr(result)


def test_non_json_response_becomes_safe_error():
    session = MagicMock()
    response = _response({}, status=502, ok=False)
    response.json.side_effect = ValueError("HTML from proxy with secrets")
    session.request.return_value = response
    client = MetaAdsClient("token", session=session)

    with pytest.raises(MetaAdsApiError, match="non-JSON response"):
        client.request("GET", "me/adaccounts")


def test_error_redacts_credentials_in_all_fields_before_truncation():
    token = "private-access-value"
    secret = "private-app-value"
    proof = hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
    session = MagicMock()
    session.request.return_value = _response(
        {
            "error": {
                "message": "x" * 495 + token,
                "type": token,
                "error_user_title": secret,
                "error_user_msg": proof,
                "fbtrace_id": token,
            }
        },
        status=400,
        ok=False,
    )
    client = MetaAdsClient(token, app_secret=secret, session=session)
    with pytest.raises(MetaAdsApiError) as caught:
        client.request("GET", "me/adaccounts")
    result = caught.value.as_dict()
    assert result["message"] == "x" * 495 + "[REDA"
    assert all(value not in repr(result) for value in (token, secret, proof))
    assert result["user_title"] == result["user_message"] == result["trace_id"] == "[REDACTED]"


def test_redirect_is_not_reported_as_success():
    session = MagicMock()
    session.request.return_value = _response({"data": []}, status=307)
    with pytest.raises(MetaAdsApiError):
        MetaAdsClient("access-value", session=session).request("POST", "act_1/ads")
    assert session.request.call_args.kwargs["allow_redirects"] is False


def test_missing_token_has_actionable_setup_message():
    with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="META_ACCESS_TOKEN"):
        get_meta_client()


@pytest.mark.parametrize("version", ["25.0", "latest", "v25", "https://example.test"])
def test_rejects_invalid_api_version(version):
    with pytest.raises(ValueError, match="META_GRAPH_API_VERSION"):
        MetaAdsClient("token", api_version=version)
