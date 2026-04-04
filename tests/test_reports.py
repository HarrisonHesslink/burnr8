"""Tests for burnr8.reports — CSV export, sanitization, cleanup, and storage stats."""

import csv
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from burnr8.reports import (
    _prune_old_reports,
    _sanitize_cell,
    get_storage_stats,
    save_report,
)


def test_save_report_creates_csv():
    rows = [
        {"keyword": "test", "clicks": 10, "cost": 5.0},
        {"keyword": "demo", "clicks": 20, "cost": 10.0},
    ]
    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.reports.REPORTS_DIR", Path(tmpdir)):
        result = save_report(rows, "test_report")

        assert result["rows"] == 2
        assert result["file"] is not None
        assert Path(result["file"]).exists()
        assert result["columns"] == ["keyword", "clicks", "cost"]
        assert len(result["top"]) == 2

        # Verify CSV content
        with open(result["file"]) as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
            assert len(csv_rows) == 2
            assert csv_rows[0]["keyword"] == "test"


def test_save_report_empty_rows():
    result = save_report([], "empty_report")
    assert result["rows"] == 0
    assert result["file"] is None
    assert result["top"] == []


def test_save_report_top_n_truncation():
    rows = [{"id": i, "value": i * 10} for i in range(100)]
    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.reports.REPORTS_DIR", Path(tmpdir)):
        result = save_report(rows, "big_report", top_n=5)

        assert result["rows"] == 100
        assert len(result["top"]) == 5
        assert result["top"][0]["id"] == 0

        # CSV has all 100 rows
        with open(result["file"]) as f:
            reader = csv.DictReader(f)
            assert len(list(reader)) == 100


def test_save_report_filename_format():
    rows = [{"a": 1}]
    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.reports.REPORTS_DIR", Path(tmpdir)):
        result = save_report(rows, "search_terms")
        filename = Path(result["file"]).name
        assert filename.startswith("search_terms_")
        assert filename.endswith(".csv")
        # Should have UUID suffix for collision avoidance
        parts = filename.replace(".csv", "").split("_")
        assert len(parts) >= 4  # name_date_time_uuid


# --- CSV formula injection ---


def test_sanitize_cell_equals():
    assert _sanitize_cell("=CMD()") == "'=CMD()"


def test_sanitize_cell_plus():
    assert _sanitize_cell("+1234") == "'+1234"


def test_sanitize_cell_minus():
    assert _sanitize_cell("-1234") == "'-1234"


def test_sanitize_cell_at():
    assert _sanitize_cell("@SUM(A1)") == "'@SUM(A1)"


def test_sanitize_cell_safe_string():
    assert _sanitize_cell("normal text") == "normal text"


def test_sanitize_cell_number():
    assert _sanitize_cell(42) == 42


def test_sanitize_cell_empty():
    assert _sanitize_cell("") == ""


def test_sanitize_cell_strips_tabs():
    """Tab injection: 'safe\t=CMD()' should have tab stripped."""
    result = _sanitize_cell("safe\t=CMD()")
    assert "\t" not in result


def test_sanitize_cell_strips_newlines():
    """Newline injection: 'safe\n=CMD()' should have newline stripped."""
    result = _sanitize_cell("safe\n=HYPERLINK()")
    assert "\n" not in result


def test_sanitize_cell_strips_carriage_return():
    result = _sanitize_cell("safe\r\n=CMD()")
    assert "\r" not in result
    assert "\n" not in result


def test_csv_contains_sanitized_values():
    rows = [{"term": "=CMD()", "clicks": 5}]
    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.reports.REPORTS_DIR", Path(tmpdir)):
        result = save_report(rows, "test_sanitize")
        with open(result["file"]) as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert row["term"] == "'=CMD()"


# --- File permissions ---


def test_csv_file_permissions():
    rows = [{"a": 1}]
    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.reports.REPORTS_DIR", Path(tmpdir)):
        result = save_report(rows, "perms_test")
        mode = oct(os.stat(result["file"]).st_mode)[-3:]
        assert mode == "600"


# --- Path traversal ---


def test_path_traversal_rejected():
    rows = [{"a": 1}]
    result = save_report(rows, "../../etc/evil")
    assert result.get("error") is True
    assert "Invalid report_name" in result["message"]


def test_report_name_with_slashes_rejected():
    rows = [{"a": 1}]
    result = save_report(rows, "foo/bar")
    assert result.get("error") is True


def test_report_name_with_spaces_rejected():
    rows = [{"a": 1}]
    result = save_report(rows, "foo bar")
    assert result.get("error") is True


# --- Symlink check ---


def test_symlink_reports_dir_rejected():
    rows = [{"a": 1}]
    with tempfile.TemporaryDirectory() as tmpdir:
        real_dir = Path(tmpdir) / "real"
        real_dir.mkdir()
        link_dir = Path(tmpdir) / "link"
        link_dir.symlink_to(real_dir)
        with patch("burnr8.reports.REPORTS_DIR", link_dir):
            result = save_report(rows, "test_report")
            assert result.get("error") is True
            assert "symlink" in result["message"]


# --- Auto-prune ---


def test_prune_old_reports():
    with tempfile.TemporaryDirectory() as tmpdir:
        reports_dir = Path(tmpdir)
        # Create an "old" file
        old_file = reports_dir / "old_report.csv"
        old_file.write_text("a,b\n1,2")
        old_time = time.time() - 10 * 86400
        os.utime(old_file, (old_time, old_time))

        # Create a "new" file
        new_file = reports_dir / "new_report.csv"
        new_file.write_text("a,b\n3,4")

        with patch("burnr8.reports.REPORTS_DIR", reports_dir):
            deleted = _prune_old_reports(max_age_days=7)
            assert deleted == 1
            assert not old_file.exists()
            assert new_file.exists()


# --- Storage stats ---


def test_get_storage_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        reports_dir = Path(tmpdir)
        (reports_dir / "report1.csv").write_text("a,b\n1,2\n3,4")
        (reports_dir / "report2.csv").write_text("x,y\n5,6")

        with patch("burnr8.reports.REPORTS_DIR", reports_dir):
            stats = get_storage_stats()
            assert stats["report_files"] == 2
            assert stats["total_size_mb"] >= 0
            assert stats["oldest_file"] is not None


def test_get_storage_stats_empty():
    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.reports.REPORTS_DIR", Path(tmpdir)):
        stats = get_storage_stats()
        assert stats["report_files"] == 0
        assert stats["total_size_mb"] == 0
