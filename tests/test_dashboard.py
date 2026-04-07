"""Tests for burnr8.dashboard — terminal dashboard helpers and main flow."""

from unittest.mock import MagicMock, patch

from burnr8.dashboard import bar, format_dollars


class TestBar:
    def test_zero_percent(self):
        assert bar(0, width=10) == "[----------]"

    def test_hundred_percent(self):
        assert bar(100, width=10) == "[##########]"

    def test_fifty_percent(self):
        assert bar(50, width=10) == "[#####-----]"

    def test_default_width(self):
        result = bar(50)
        # Default width is 20
        assert len(result) == 22  # 20 chars + 2 brackets
        assert result.count("#") == 10
        assert result.count("-") == 10

    def test_small_percentage(self):
        result = bar(5, width=20)
        assert result.count("#") == 1


class TestFormatDollars:
    def test_basic(self):
        assert format_dollars(100.0) == "$100.00"

    def test_thousands_separator(self):
        assert format_dollars(1234.56) == "$1,234.56"

    def test_zero(self):
        assert format_dollars(0) == "$0.00"

    def test_large_number(self):
        assert format_dollars(1_000_000.99) == "$1,000,000.99"


class TestMain:
    def test_help_flag(self, capsys):
        from burnr8.dashboard import main

        with patch("sys.argv", ["burnr8", "--help"]):
            main()

        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_h_flag(self, capsys):
        from burnr8.dashboard import main

        with patch("sys.argv", ["burnr8", "-h"]):
            main()

        captured = capsys.readouterr()
        assert "Usage" in captured.out


class TestPrintDashboard:
    def test_runs_without_credentials(self, capsys):
        """print_dashboard should handle missing credentials gracefully."""
        from burnr8.dashboard import print_dashboard

        mock_stats = {
            "ops_today": 42,
            "ops_limit": 15_000,
            "ops_pct": 0.3,
            "errors_today": 1,
            "recent_calls": [
                {"time": "12:00:00", "tool": "list_campaigns", "status": "ok", "duration": 0.5},
            ],
        }
        mock_storage = {"report_files": 3, "total_size_mb": 1.2}

        mock_log_path = MagicMock()
        mock_log_path.exists.return_value = False
        mock_log_dir = MagicMock()
        mock_log_dir.__truediv__ = MagicMock(return_value=mock_log_path)

        # Patch at the source modules since dashboard imports locally
        with (
            patch("burnr8.dashboard.load_dotenv"),
            patch("burnr8.logging.get_usage_stats", return_value=mock_stats),
            patch("burnr8.reports.get_storage_stats", return_value=mock_storage),
            patch("burnr8.logging.LOG_DIR", mock_log_dir),
            patch("burnr8.client.get_client", side_effect=OSError("Missing required credentials")),
        ):
            print_dashboard()

        captured = capsys.readouterr()
        assert "burnr8" in captured.out
        assert "API Ops Today" in captured.out
        assert "Could not load campaign data" in captured.out
