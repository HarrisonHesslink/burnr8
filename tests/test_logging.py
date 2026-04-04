"""Tests for burnr8.logging — usage tracking and tool call logging."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_usage_stats_default():
    """Test get_usage_stats returns correct structure."""
    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.logging.LOG_DIR", Path(tmpdir)), \
             patch("burnr8.logging.USAGE_FILE", Path(tmpdir) / "usage.json"):
        from burnr8.logging import get_usage_stats
        stats = get_usage_stats()
        assert "date" in stats
        assert "ops_today" in stats
        assert "ops_limit" in stats
        assert stats["ops_limit"] == 15_000
        assert "ops_pct" in stats
        assert "errors_today" in stats
        assert "recent_calls" in stats


def test_log_tool_call_increments_ops():
    """Test that logging a tool call increments the ops counter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with patch("burnr8.logging.LOG_DIR", log_dir), \
             patch("burnr8.logging.USAGE_FILE", usage_file), \
             patch("burnr8.logging._logger", None):
            from burnr8.logging import _load_usage, log_tool_call
            log_tool_call("test_tool", "123456", 0.5, "ok")
            data = _load_usage()
            assert data["ops"] >= 1


def test_log_tool_call_tracks_errors():
    """Test that error calls increment the errors counter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with patch("burnr8.logging.LOG_DIR", log_dir), \
             patch("burnr8.logging.USAGE_FILE", usage_file), \
             patch("burnr8.logging._logger", None):
            from burnr8.logging import _load_usage, log_tool_call
            log_tool_call("fail_tool", "123456", 0.5, "error", "msg=\"test\"")
            data = _load_usage()
            assert data["errors"] >= 1


def test_usage_file_atomic_write():
    """Test that usage file is written atomically (no .tmp left behind)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with patch("burnr8.logging.LOG_DIR", log_dir), \
             patch("burnr8.logging.USAGE_FILE", usage_file):
            from burnr8.logging import _save_usage
            _save_usage({"date": "2026-04-04", "ops": 1, "errors": 0, "calls": []})
            assert usage_file.exists()
            assert not (usage_file.with_suffix(".tmp")).exists()
            data = json.loads(usage_file.read_text())
            assert data["ops"] == 1


def test_load_usage_returns_fresh_for_new_day():
    """Test that _load_usage returns fresh data when date changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        # Write stale data with yesterday's date
        usage_file.write_text(json.dumps({
            "date": "1999-01-01", "ops": 999, "errors": 99, "calls": []
        }))
        with patch("burnr8.logging.LOG_DIR", log_dir), \
             patch("burnr8.logging.USAGE_FILE", usage_file):
            from burnr8.logging import _load_usage
            data = _load_usage()
            # Should be reset since date doesn't match today
            assert data["ops"] == 0
            assert data["errors"] == 0


def test_load_usage_handles_corrupt_file():
    """Test that _load_usage handles corrupt JSON gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        usage_file.write_text("not valid json{{{")
        with patch("burnr8.logging.LOG_DIR", log_dir), \
             patch("burnr8.logging.USAGE_FILE", usage_file):
            from burnr8.logging import _load_usage
            data = _load_usage()
            assert data["ops"] == 0
            assert data["errors"] == 0


def test_log_tool_call_keeps_last_50_calls():
    """Test that the calls list is capped at 50 entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with patch("burnr8.logging.LOG_DIR", log_dir), \
             patch("burnr8.logging.USAGE_FILE", usage_file), \
             patch("burnr8.logging._logger", None):
            from burnr8.logging import _load_usage, log_tool_call
            for i in range(60):
                log_tool_call(f"tool_{i}", "123456", 0.1, "ok")
            data = _load_usage()
            assert len(data["calls"]) == 50


def test_get_usage_stats_recent_calls_limited_to_10():
    """Test that get_usage_stats returns at most 10 recent calls."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with patch("burnr8.logging.LOG_DIR", log_dir), \
             patch("burnr8.logging.USAGE_FILE", usage_file), \
             patch("burnr8.logging._logger", None):
            from burnr8.logging import get_usage_stats, log_tool_call
            for i in range(20):
                log_tool_call(f"tool_{i}", "123456", 0.1, "ok")
            stats = get_usage_stats()
            assert len(stats["recent_calls"]) == 10
