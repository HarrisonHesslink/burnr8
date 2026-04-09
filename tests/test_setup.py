"""Tests for burnr8.setup — credential wizard helpers."""

import os
import stat
from unittest.mock import patch

from burnr8.setup import _load_existing, _save_env


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

        content = env_file.read_text()
        assert "GOOGLE_ADS_DEVELOPER_TOKEN=my_token" in content
        assert "GOOGLE_ADS_CLIENT_ID=my_id" in content
        assert "GOOGLE_ADS_CLIENT_SECRET=my_secret" in content
        assert "GOOGLE_ADS_REFRESH_TOKEN=my_refresh" in content

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

        content = env_file.read_text()
        assert "GOOGLE_ADS_LOGIN_CUSTOMER_ID=1234567890" in content

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

        content = env_file.read_text()
        assert "LOGIN_CUSTOMER_ID" not in content


class TestMainEntrypoint:
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
