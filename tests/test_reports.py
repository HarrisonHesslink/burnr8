"""Tests for burnr8.reports — CSV export and summary generation."""

import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

from burnr8.reports import save_report


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
