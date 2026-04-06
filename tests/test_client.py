"""Tests for burnr8.client — singleton GoogleAdsClient with credential validation."""

import importlib
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


def _reload_client():
    """Re-import client module to reset the singleton."""
    import burnr8.client as mod

    mod._client = None
    return mod


class TestGetClientValidation:
    def test_missing_all_credentials_raises(self):
        mod = _reload_client()
        with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="Missing required credentials"):
            mod.get_client()

    def test_missing_single_credential_raises(self):
        mod = _reload_client()
        env = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "token",
            "GOOGLE_ADS_CLIENT_ID": "id",
            "GOOGLE_ADS_CLIENT_SECRET": "secret",
            # GOOGLE_ADS_REFRESH_TOKEN is missing
        }
        with patch.dict("os.environ", env, clear=True), pytest.raises(OSError, match="GOOGLE_ADS_REFRESH_TOKEN"):
            mod.get_client()

    def test_missing_credentials_mentions_burnr8_setup(self):
        mod = _reload_client()
        with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="burnr8-setup"):
            mod.get_client()

    def test_valid_credentials_creates_client(self):
        mod = _reload_client()
        env = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token",
            "GOOGLE_ADS_CLIENT_ID": "client-id",
            "GOOGLE_ADS_CLIENT_SECRET": "client-secret",
            "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token",
        }
        mock_gac = MagicMock()
        mock_gac.load_from_dict.return_value = MagicMock(name="FakeClient")

        mock_module = MagicMock(GoogleAdsClient=mock_gac)
        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"google.ads.googleads.client": mock_module}),
        ):
            importlib.reload(mod)
            mod._client = None
            mod.get_client()

        mock_gac.load_from_dict.assert_called_once()
        call_kwargs = mock_gac.load_from_dict.call_args
        config = call_kwargs.kwargs.get("config_dict", call_kwargs[1].get("config_dict"))
        assert config["developer_token"] == "dev-token"
        assert config["use_proto_plus"] is True
        assert call_kwargs.kwargs.get("version", call_kwargs[1].get("version")) == "v23"

    def test_login_customer_id_absent_when_env_unset(self):
        mod = _reload_client()
        env = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token",
            "GOOGLE_ADS_CLIENT_ID": "client-id",
            "GOOGLE_ADS_CLIENT_SECRET": "client-secret",
            "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token",
            # GOOGLE_ADS_LOGIN_CUSTOMER_ID intentionally absent
        }
        mock_gac = MagicMock()
        mock_gac.load_from_dict.return_value = MagicMock()

        mock_module = MagicMock(GoogleAdsClient=mock_gac)
        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"google.ads.googleads.client": mock_module}),
        ):
            importlib.reload(mod)
            mod._client = None
            mod.get_client()

        config = mock_gac.load_from_dict.call_args.kwargs.get(
            "config_dict", mock_gac.load_from_dict.call_args[1].get("config_dict")
        )
        assert "login_customer_id" not in config

    def test_login_customer_id_strips_dashes(self):
        mod = _reload_client()
        env = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token",
            "GOOGLE_ADS_CLIENT_ID": "client-id",
            "GOOGLE_ADS_CLIENT_SECRET": "client-secret",
            "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "123-456-7890",
        }
        mock_gac = MagicMock()
        mock_gac.load_from_dict.return_value = MagicMock()

        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"google.ads.googleads.client": MagicMock(GoogleAdsClient=mock_gac)}),
        ):
            importlib.reload(mod)
            mod._client = None
            mod.get_client()

        config = mock_gac.load_from_dict.call_args.kwargs.get(
            "config_dict", mock_gac.load_from_dict.call_args[1].get("config_dict")
        )
        assert config["login_customer_id"] == "1234567890"


class TestSingleton:
    def test_returns_same_instance(self):
        mod = _reload_client()
        env = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "t",
            "GOOGLE_ADS_CLIENT_ID": "i",
            "GOOGLE_ADS_CLIENT_SECRET": "s",
            "GOOGLE_ADS_REFRESH_TOKEN": "r",
        }
        mock_gac = MagicMock()
        fake_client = MagicMock(name="SingletonClient")
        mock_gac.load_from_dict.return_value = fake_client

        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"google.ads.googleads.client": MagicMock(GoogleAdsClient=mock_gac)}),
        ):
            importlib.reload(mod)
            mod._client = None
            c1 = mod.get_client()
            c2 = mod.get_client()

        assert c1 is c2
        assert mock_gac.load_from_dict.call_count == 1

    def test_concurrent_get_client_creates_once(self):
        """Double-checked locking: concurrent calls should still create only one client."""
        mod = _reload_client()
        env = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "t",
            "GOOGLE_ADS_CLIENT_ID": "i",
            "GOOGLE_ADS_CLIENT_SECRET": "s",
            "GOOGLE_ADS_REFRESH_TOKEN": "r",
        }
        mock_gac = MagicMock()
        fake_client = MagicMock(name="ThreadSafeClient")

        def slow_load(*args, **kwargs):
            time.sleep(0.01)  # widen race window past GIL quantum
            return fake_client

        mock_gac.load_from_dict.side_effect = slow_load

        results = []
        barrier = threading.Barrier(4)

        def call_get_client():
            barrier.wait()
            results.append(mod.get_client())

        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"google.ads.googleads.client": MagicMock(GoogleAdsClient=mock_gac)}),
        ):
            importlib.reload(mod)
            mod._client = None
            threads = [threading.Thread(target=call_get_client) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # All threads got the same instance, created only once
        assert all(r is fake_client for r in results)
        assert mock_gac.load_from_dict.call_count == 1
