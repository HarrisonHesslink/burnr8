"""Tests for burnr8.errors — error handling decorator."""

from unittest.mock import patch

from burnr8.errors import handle_google_ads_errors


def test_decorator_returns_result_on_success():
    @handle_google_ads_errors
    def my_tool():
        return {"data": "ok"}

    with patch("burnr8.errors.log_tool_call"):
        assert my_tool() == {"data": "ok"}


def test_decorator_catches_key_error():
    @handle_google_ads_errors
    def my_tool():
        raise KeyError("missing_key")

    with patch("burnr8.errors.log_tool_call"):
        result = my_tool()
        assert result["error"] is True
        assert "missing_key" in result["message"]


def test_decorator_catches_value_error():
    @handle_google_ads_errors
    def my_tool():
        raise ValueError("bad value")

    with patch("burnr8.errors.log_tool_call"):
        result = my_tool()
        assert result["error"] is True
        assert "bad value" in result["message"]


def test_decorator_catches_type_error():
    @handle_google_ads_errors
    def my_tool():
        raise TypeError("wrong type")

    with patch("burnr8.errors.log_tool_call"):
        result = my_tool()
        assert result["error"] is True


def test_decorator_preserves_function_name():
    @handle_google_ads_errors
    def my_special_tool():
        return {}

    assert my_special_tool.__name__ == "my_special_tool"


def test_decorator_passes_args_through():
    @handle_google_ads_errors
    def my_tool(customer_id, value=None):
        return {"customer_id": customer_id, "value": value}

    with patch("burnr8.errors.log_tool_call"):
        result = my_tool("123456", value="test")
        assert result["customer_id"] == "123456"
        assert result["value"] == "test"


def test_decorator_logs_ok_on_success():
    @handle_google_ads_errors
    def my_tool(customer_id):
        return {"data": "ok"}

    with patch("burnr8.errors.log_tool_call") as mock_log:
        my_tool("123456")
        mock_log.assert_called_once()
        args = mock_log.call_args
        assert args[0][0] == "my_tool"  # tool name
        assert args[0][1] == "123456"  # customer_id
        assert args[0][3] == "ok"  # status


def test_decorator_logs_error_on_exception():
    @handle_google_ads_errors
    def my_tool(customer_id):
        raise ValueError("boom")

    with patch("burnr8.errors.log_tool_call") as mock_log:
        my_tool("123456")
        mock_log.assert_called_once()
        args = mock_log.call_args
        assert args[0][3] == "error"  # status


def test_decorator_logs_error_status_for_error_result():
    @handle_google_ads_errors
    def my_tool():
        return {"error": True, "message": "validation failed"}

    with patch("burnr8.errors.log_tool_call") as mock_log:
        result = my_tool()
        assert result["error"] is True
        mock_log.assert_called_once()
        args = mock_log.call_args
        assert args[0][3] == "error"


def test_decorator_logs_warn_for_warning_result():
    @handle_google_ads_errors
    def my_tool():
        return {"warning": "Set confirm=true to execute."}

    with patch("burnr8.errors.log_tool_call") as mock_log:
        result = my_tool()
        assert "warning" in result
        mock_log.assert_called_once()
        args = mock_log.call_args
        assert args[0][3] == "warn"


def test_decorator_reports_row_count_for_list_result():
    @handle_google_ads_errors
    def my_tool():
        return [{"id": 1}, {"id": 2}, {"id": 3}]

    with patch("burnr8.errors.log_tool_call") as mock_log:
        result = my_tool()
        assert len(result) == 3
        args = mock_log.call_args
        assert "rows=3" in args[0][4]


def test_decorator_reports_added_count():
    @handle_google_ads_errors
    def my_tool():
        return {"added": 5}

    with patch("burnr8.errors.log_tool_call") as mock_log:
        my_tool()
        args = mock_log.call_args
        assert "added=5" in args[0][4]
