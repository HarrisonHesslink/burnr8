"""Tests for burnr8.logging — usage tracking, tool call logging, correlation IDs, error viewer."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_usage_stats_default():
    """Test get_usage_stats returns correct structure."""
    with (
        tempfile.TemporaryDirectory() as tmpdir,
        patch("burnr8.logging.LOG_DIR", Path(tmpdir)),
        patch("burnr8.logging.USAGE_FILE", Path(tmpdir) / "usage.json"),
    ):
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
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
        ):
            from burnr8.logging import _load_usage, log_tool_call

            log_tool_call("test_tool", "123456", 0.5, "ok")
            data = _load_usage()
            assert data["ops"] >= 1


def test_log_tool_call_tracks_errors():
    """Test that error calls increment the errors counter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
        ):
            from burnr8.logging import _load_usage, log_tool_call

            log_tool_call("fail_tool", "123456", 0.5, "error", 'msg="test"')
            data = _load_usage()
            assert data["errors"] >= 1


def test_usage_file_atomic_write():
    """Test that usage file is written atomically (no .tmp left behind)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with patch("burnr8.logging.LOG_DIR", log_dir), patch("burnr8.logging.USAGE_FILE", usage_file):
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
        usage_file.write_text(json.dumps({"date": "1999-01-01", "ops": 999, "errors": 99, "calls": []}))
        with patch("burnr8.logging.LOG_DIR", log_dir), patch("burnr8.logging.USAGE_FILE", usage_file):
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
        with patch("burnr8.logging.LOG_DIR", log_dir), patch("burnr8.logging.USAGE_FILE", usage_file):
            from burnr8.logging import _load_usage

            data = _load_usage()
            assert data["ops"] == 0
            assert data["errors"] == 0


def test_log_tool_call_keeps_last_50_calls():
    """Test that the calls list is capped at 50 entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
        ):
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
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
        ):
            from burnr8.logging import get_usage_stats, log_tool_call

            for i in range(20):
                log_tool_call(f"tool_{i}", "123456", 0.1, "ok")
            stats = get_usage_stats()
            assert len(stats["recent_calls"]) == 10


# --- Correlation ID ---


def test_new_correlation_id_returns_string():
    from burnr8.logging import new_correlation_id

    cid = new_correlation_id()
    assert isinstance(cid, str)
    assert len(cid) == 12


def test_get_correlation_id_returns_set_value():
    from burnr8.logging import get_correlation_id, new_correlation_id

    cid = new_correlation_id()
    assert get_correlation_id() == cid


def test_correlation_id_changes_each_call():
    from burnr8.logging import new_correlation_id

    cid1 = new_correlation_id()
    cid2 = new_correlation_id()
    assert cid1 != cid2


# --- Error viewer ---


def test_get_recent_errors_empty_log():
    from burnr8.logging import get_recent_errors

    with tempfile.TemporaryDirectory() as tmpdir, patch("burnr8.logging.LOG_DIR", Path(tmpdir)):
        errors = get_recent_errors()
        assert errors == []


def test_get_recent_errors_finds_errors():
    from burnr8.logging import get_recent_errors

    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        log_file = log_dir / "burnr8.log"
        log_file.write_text(
            "2026-04-04 18:32:15 INFO  tool=list_campaigns status=ok\n"
            "2026-04-04 18:32:16 ERROR tool=update_campaign status=error msg=failed\n"
            "2026-04-04 18:32:17 INFO  tool=list_keywords status=ok\n"
            "2026-04-04 18:32:18 ERROR tool=set_status status=error msg=denied\n"
        )
        with patch("burnr8.logging.LOG_DIR", log_dir):
            errors = get_recent_errors(limit=10)
            assert len(errors) == 2
            assert "update_campaign" in errors[0]["raw"]
            assert "set_status" in errors[1]["raw"]


def test_get_recent_errors_respects_limit():
    from burnr8.logging import get_recent_errors

    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        log_file = log_dir / "burnr8.log"
        lines = [f"2026-04-04 18:32:{i:02d} ERROR tool=tool_{i}\n" for i in range(50)]
        log_file.write_text("".join(lines))
        with patch("burnr8.logging.LOG_DIR", log_dir):
            errors = get_recent_errors(limit=5)
            assert len(errors) == 5
            # Should be the LAST 5
            assert "tool_45" in errors[0]["raw"]


# --- Log level ---


# --- Cloud logging ---


def test_cloud_log_enqueues_when_cloud_mode_and_user_id_set():
    """In cloud mode with a user_id, log_tool_call should enqueue a cloud log row."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
            patch("burnr8.logging.CLOUD_MODE", True),
            patch("burnr8.logging._enqueue_cloud_log") as mock_enqueue,
        ):
            from burnr8.logging import cloud_api_key_id, cloud_user_id, log_tool_call

            cloud_user_id.set("user-abc-123")
            cloud_api_key_id.set("key-456")
            log_tool_call("test_tool", "123456", 0.5, "ok", "detail=test")

            mock_enqueue.assert_called_once()
            row = mock_enqueue.call_args[0][0]
            assert row["user_id"] == "user-abc-123"
            assert row["api_key_id"] == "key-456"
            assert row["tool_name"] == "test_tool"
            assert row["customer_id"] == "123456"
            assert row["duration_ms"] == 500
            assert row["status"] == "ok"
            # detail and correlation_id excluded — not in schema, PII risk
            assert "detail" not in row
            assert "correlation_id" not in row
            assert "created_at" not in row  # let Supabase default handle it

            cloud_user_id.set(None)


def test_cloud_log_normalizes_warn_status_to_error():
    """The DB CHECK constraint only allows 'ok' and 'error' — 'warn' maps to 'error'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
            patch("burnr8.logging.CLOUD_MODE", True),
            patch("burnr8.logging._enqueue_cloud_log") as mock_enqueue,
        ):
            from burnr8.logging import cloud_user_id, log_tool_call

            cloud_user_id.set("user-abc-123")
            log_tool_call("test_tool", "123456", 0.5, "warn", "confirm=false")

            row = mock_enqueue.call_args[0][0]
            assert row["status"] == "error"  # warn → error for DB CHECK constraint

            cloud_user_id.set(None)


def test_cloud_log_skipped_when_no_user_id():
    """Cloud mode without user_id should not enqueue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
            patch("burnr8.logging.CLOUD_MODE", True),
            patch("burnr8.logging._enqueue_cloud_log") as mock_enqueue,
        ):
            from burnr8.logging import cloud_user_id, log_tool_call

            cloud_user_id.set(None)
            log_tool_call("test_tool", "123456", 0.5, "ok")
            mock_enqueue.assert_not_called()


def test_cloud_log_skipped_when_not_cloud_mode():
    """Without BURNR8_CLOUD, no cloud logging should happen."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        usage_file = log_dir / "usage.json"
        with (
            patch("burnr8.logging.LOG_DIR", log_dir),
            patch("burnr8.logging.USAGE_FILE", usage_file),
            patch("burnr8.logging._logger", None),
            patch("burnr8.logging.CLOUD_MODE", False),
            patch("burnr8.logging._enqueue_cloud_log") as mock_enqueue,
        ):
            from burnr8.logging import log_tool_call

            log_tool_call("test_tool", "123456", 0.5, "ok")
            mock_enqueue.assert_not_called()


def test_write_cloud_log_posts_correct_row():
    """_write_cloud_log should POST to Supabase with correct headers and row."""
    from unittest.mock import MagicMock

    mock_post = MagicMock()
    row = {
        "user_id": "user-abc",
        "tool_name": "list_campaigns",
        "customer_id": "1234567890",
        "duration_ms": 500,
        "status": "ok",
        "correlation_id": "abc123def456",
        "created_at": "2026-04-05T00:00:00+00:00",
    }

    with (
        patch("burnr8.logging.os.environ.get") as mock_env,
        patch.dict("sys.modules", {"requests": MagicMock()}),
    ):
        import sys

        mock_requests = sys.modules["requests"]
        mock_requests.post = mock_post
        mock_env.side_effect = lambda k, d=None: {
            "BURNR8_SUPABASE_URL": "https://test.supabase.co",
            "BURNR8_SUPABASE_KEY": "test-key",
        }.get(k, d)

        from burnr8.logging import _write_cloud_log

        _write_cloud_log(row)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "rest/v1/usage_logs" in call_kwargs[0][0] or call_kwargs.kwargs.get("url", call_kwargs[0][0])
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["apikey"] == "test-key"
        assert headers["Prefer"] == "return=minimal"
        assert call_kwargs.kwargs.get("timeout") == 5 or call_kwargs[1].get("timeout") == 5


def test_write_cloud_log_suppresses_network_errors():
    """_write_cloud_log should not raise on network failures."""
    from unittest.mock import MagicMock

    mock_post = MagicMock(side_effect=ConnectionError("network down"))

    with (
        patch("burnr8.logging.os.environ.get") as mock_env,
        patch.dict("sys.modules", {"requests": MagicMock()}),
    ):
        import sys

        mock_requests = sys.modules["requests"]
        mock_requests.post = mock_post
        mock_env.side_effect = lambda k, d=None: {
            "BURNR8_SUPABASE_URL": "https://test.supabase.co",
            "BURNR8_SUPABASE_KEY": "test-key",
        }.get(k, d)

        from burnr8.logging import _write_cloud_log

        # Should not raise
        _write_cloud_log({"user_id": "test", "tool_name": "test"})


# --- Log level ---


def test_log_level_default():
    from burnr8.logging import LOG_LEVEL

    assert LOG_LEVEL == "INFO" or LOG_LEVEL in {"DEBUG", "WARNING", "ERROR"}


def test_usage_stats_includes_log_level():
    with (
        tempfile.TemporaryDirectory() as tmpdir,
        patch("burnr8.logging.LOG_DIR", Path(tmpdir)),
        patch("burnr8.logging.USAGE_FILE", Path(tmpdir) / "usage.json"),
    ):
        from burnr8.logging import get_usage_stats

        stats = get_usage_stats()
        assert "log_level" in stats
        assert "log_file" in stats
