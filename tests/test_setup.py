"""Tests for burnr8.setup — credential wizard helpers."""

import os
import stat
from unittest.mock import patch

from dotenv import dotenv_values

from burnr8.setup import _load_existing, _prompt, _save_env


class TestLoadExisting:
    def test_loads_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "GOOGLE_ADS_DEVELOPER_TOKEN=tok123\n"
            "GOOGLE_ADS_CLIENT_ID=cid456\n"
            "# comment line\n"
            "\n"
            "GOOGLE_ADS_CLIENT_SECRET=sec789\n"
        )
        with patch("burnr8.setup.ENV_FILE", env_file):
            result = _load_existing()

        assert result["GOOGLE_ADS_DEVELOPER_TOKEN"] == "tok123"
        assert result["GOOGLE_ADS_CLIENT_ID"] == "cid456"
        assert result["GOOGLE_ADS_CLIENT_SECRET"] == "sec789"

    def test_strips_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('GOOGLE_ADS_DEVELOPER_TOKEN="quoted_value"\n')
        with patch("burnr8.setup.ENV_FILE", env_file):
            result = _load_existing()

        assert result["GOOGLE_ADS_DEVELOPER_TOKEN"] == "quoted_value"

    def test_returns_empty_when_no_file(self, tmp_path):
        env_file = tmp_path / ".env"
        with patch("burnr8.setup.ENV_FILE", env_file):
            result = _load_existing()

        assert result == {}

    def test_skips_comment_lines(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# this is a comment\nKEY=val\n")
        with patch("burnr8.setup.ENV_FILE", env_file):
            result = _load_existing()

        assert "# this is a comment" not in result
        assert result["KEY"] == "val"

    def test_skips_empty_lines(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("\n\nKEY=val\n\n")
        with patch("burnr8.setup.ENV_FILE", env_file):
            result = _load_existing()

        assert len(result) == 1


class TestSaveEnv:
    def test_preserves_conversion_token_and_other_existing_settings(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("REDDIT_CAPI_ACCESS_TOKEN='conversion-value'\nBURNR8_MAX_DAILY_BUDGET_DOLLARS=25\n")
        with patch("burnr8.setup.ENV_FILE", env_file), patch("burnr8.setup.BURNR8_DIR", tmp_path):
            _save_env({"GOOGLE_ADS_CLIENT_ID": "new-id"})
        saved = dotenv_values(env_file)
        assert saved["REDDIT_CAPI_ACCESS_TOKEN"] == "conversion-value"
        assert saved["BURNR8_MAX_DAILY_BUDGET_DOLLARS"] == "25"
        assert saved["GOOGLE_ADS_CLIENT_ID"] == "new-id"

    def test_round_trips_spaces_hashes_quotes_and_backslashes(self, tmp_path):
        env_file = tmp_path / ".env"
        value = r"/photos/student's #1\image"
        with patch("burnr8.setup.ENV_FILE", env_file), patch("burnr8.setup.BURNR8_DIR", tmp_path):
            _save_env({"BURNR8_MEDIA_ROOT": value})
            assert _load_existing()["BURNR8_MEDIA_ROOT"] == value

    def test_creates_file_with_restrictive_permissions(self, tmp_path):
        env_file = tmp_path / ".burnr8" / ".env"
        creds = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "tok",
            "GOOGLE_ADS_CLIENT_ID": "cid",
            "GOOGLE_ADS_CLIENT_SECRET": "sec",
            "GOOGLE_ADS_REFRESH_TOKEN": "ref",
        }
        with (
            patch("burnr8.setup.ENV_FILE", env_file),
            patch("burnr8.setup.BURNR8_DIR", tmp_path / ".burnr8"),
        ):
            _save_env(creds)

        assert env_file.exists()
        mode = stat.S_IMODE(os.stat(env_file).st_mode)
        assert mode == 0o600

    def test_writes_all_credentials(self, tmp_path):
        env_file = tmp_path / ".burnr8" / ".env"
        creds = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "my_token",
            "GOOGLE_ADS_CLIENT_ID": "my_id",
            "GOOGLE_ADS_CLIENT_SECRET": "my_secret",
            "GOOGLE_ADS_REFRESH_TOKEN": "my_refresh",
        }
        with (
            patch("burnr8.setup.ENV_FILE", env_file),
            patch("burnr8.setup.BURNR8_DIR", tmp_path / ".burnr8"),
        ):
            _save_env(creds)

        content = dotenv_values(env_file, interpolate=False)
        assert content["GOOGLE_ADS_DEVELOPER_TOKEN"] == "my_token"
        assert content["GOOGLE_ADS_CLIENT_ID"] == "my_id"
        assert content["GOOGLE_ADS_CLIENT_SECRET"] == "my_secret"
        assert content["GOOGLE_ADS_REFRESH_TOKEN"] == "my_refresh"

    def test_includes_login_customer_id_when_present(self, tmp_path):
        env_file = tmp_path / ".burnr8" / ".env"
        creds = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "t",
            "GOOGLE_ADS_CLIENT_ID": "i",
            "GOOGLE_ADS_CLIENT_SECRET": "s",
            "GOOGLE_ADS_REFRESH_TOKEN": "r",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "1234567890",
        }
        with (
            patch("burnr8.setup.ENV_FILE", env_file),
            patch("burnr8.setup.BURNR8_DIR", tmp_path / ".burnr8"),
        ):
            _save_env(creds)

        content = dotenv_values(env_file, interpolate=False)
        assert content["GOOGLE_ADS_LOGIN_CUSTOMER_ID"] == "1234567890"

    def test_omits_login_customer_id_when_absent(self, tmp_path):
        env_file = tmp_path / ".burnr8" / ".env"
        creds = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "t",
            "GOOGLE_ADS_CLIENT_ID": "i",
            "GOOGLE_ADS_CLIENT_SECRET": "s",
            "GOOGLE_ADS_REFRESH_TOKEN": "r",
        }
        with (
            patch("burnr8.setup.ENV_FILE", env_file),
            patch("burnr8.setup.BURNR8_DIR", tmp_path / ".burnr8"),
        ):
            _save_env(creds)

        content = dotenv_values(env_file, interpolate=False)
        assert "GOOGLE_ADS_LOGIN_CUSTOMER_ID" not in content

    def test_writes_optional_meta_credentials(self, tmp_path):
        env_file = tmp_path / ".burnr8" / ".env"
        creds = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "t",
            "GOOGLE_ADS_CLIENT_ID": "i",
            "GOOGLE_ADS_CLIENT_SECRET": "s",
            "GOOGLE_ADS_REFRESH_TOKEN": "r",
            "META_ACCESS_TOKEN": "meta-token",
            "META_APP_SECRET": "meta-secret",
            "META_AD_ACCOUNT_ID": "123",
            "META_GRAPH_API_VERSION": "v25.0",
            "BURNR8_MEDIA_ROOT": "/approved/photos",
        }
        with (
            patch("burnr8.setup.ENV_FILE", env_file),
            patch("burnr8.setup.BURNR8_DIR", tmp_path / ".burnr8"),
        ):
            _save_env(creds)

        content = dotenv_values(env_file, interpolate=False)
        assert content["META_ACCESS_TOKEN"] == "meta-token"
        assert content["META_APP_SECRET"] == "meta-secret"
        assert content["META_AD_ACCOUNT_ID"] == "123"
        assert content["META_GRAPH_API_VERSION"] == "v25.0"
        assert content["BURNR8_MEDIA_ROOT"] == "/approved/photos"

    def test_writes_optional_seo_credentials(self, tmp_path):
        env_file = tmp_path / ".burnr8" / ".env"
        creds = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "t",
            "GOOGLE_ADS_CLIENT_ID": "i",
            "GOOGLE_ADS_CLIENT_SECRET": "s",
            "GOOGLE_ADS_REFRESH_TOKEN": "r",
            "GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN": "gsc-refresh",
            "GOOGLE_SEARCH_CONSOLE_PROPERTY": "sc-domain:studywithlily.com",
            "GOOGLE_PAGESPEED_API_KEY": "pagespeed-key",
            "GOOGLE_CRUX_API_KEY": "crux-key",
            "BURNR8_SEO_MAX_CRAWL_PAGES": "50",
        }
        with (
            patch("burnr8.setup.ENV_FILE", env_file),
            patch("burnr8.setup.BURNR8_DIR", tmp_path / ".burnr8"),
        ):
            _save_env(creds)

        content = dotenv_values(env_file, interpolate=False)
        assert content["GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN"] == "gsc-refresh"
        assert content["GOOGLE_SEARCH_CONSOLE_PROPERTY"] == "sc-domain:studywithlily.com"
        assert content["GOOGLE_PAGESPEED_API_KEY"] == "pagespeed-key"
        assert content["GOOGLE_CRUX_API_KEY"] == "crux-key"
        assert content["BURNR8_SEO_MAX_CRAWL_PAGES"] == "50"


class TestMainEntrypoint:
    def test_secret_prompt_hides_saved_and_new_values(self):
        with patch("burnr8.setup.getpass.getpass", return_value="replacement-value") as prompt:
            assert _prompt("Access token", "private-value", secret=True) == "replacement-value"
        assert prompt.call_args.args == ("  Access token [saved]: ",)

    def test_keyboard_interrupt_exits_cleanly(self, capsys):
        from burnr8.setup import main

        with patch("burnr8.setup._main", side_effect=KeyboardInterrupt), patch("sys.exit") as mock_exit:
            main()

        mock_exit.assert_called_once_with(0)
        captured = capsys.readouterr()
        assert "interrupted" in captured.out.lower()

    def test_os_error_exits_with_message(self, capsys):
        from burnr8.setup import main

        with patch("burnr8.setup._main", side_effect=OSError("Port in use")), patch("sys.exit") as mock_exit:
            main()

        mock_exit.assert_called_once_with(1)
        captured = capsys.readouterr()
        assert "Port in use" in captured.out
