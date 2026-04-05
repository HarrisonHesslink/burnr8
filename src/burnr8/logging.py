import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

LOG_DIR = Path(os.environ.get("BURNR8_LOG_DIR", os.path.expanduser("~/.burnr8/logs")))
USAGE_FILE = LOG_DIR / "usage.json"

_logger: logging.Logger | None = None
_usage_lock = threading.Lock()
_usage_cache: dict | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        with _usage_lock:
            if _logger is None:  # double-check
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                log_path = LOG_DIR / "burnr8.log"
                # Create log file with restrictive permissions if it doesn't exist
                if not log_path.exists():
                    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    os.close(fd)
                _logger = logging.getLogger("burnr8")
                _logger.setLevel(logging.INFO)
                handler = logging.FileHandler(log_path)
                handler.setFormatter(logging.Formatter(
                    "%(asctime)s %(levelname)-5s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
                ))
                _logger.addHandler(handler)
    return _logger


def _load_usage() -> dict:
    """Load today's usage data from disk."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if USAGE_FILE.exists():
        try:
            data = json.loads(USAGE_FILE.read_text())
            if data.get("date") == today:
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"date": today, "ops": 0, "errors": 0, "calls": []}


def _save_usage(data: dict) -> None:
    """Atomic write: temp file then replace."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = USAGE_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w") as f:
        f.write(json.dumps(data, indent=2))
    tmp.replace(USAGE_FILE)


def _get_usage() -> dict:
    global _usage_cache
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if _usage_cache is None or _usage_cache.get("date") != today:
        _usage_cache = _load_usage()
    return _usage_cache


def log_tool_call(tool_name: str, customer_id: str | None, duration: float, status: str, detail: str = "") -> None:
    """Log a tool call and update daily usage counters. Thread-safe."""
    logger = get_logger()
    msg = f"tool={tool_name}"
    if customer_id:
        msg += f" customer={customer_id[:6]}"
    msg += f" duration={duration:.1f}s status={status}"
    if detail:
        msg += f" {detail}"

    if status == "error":
        logger.error(msg)
    else:
        logger.info(msg)

    with _usage_lock:
        usage = _get_usage()
        usage["ops"] += 1
        if status == "error":
            usage["errors"] += 1

        # Keep last 50 calls
        usage["calls"] = usage.get("calls", [])[-49:] + [{
            "time": datetime.now(UTC).strftime("%H:%M:%S"),
            "tool": tool_name,
            "status": status,
            "duration": round(duration, 1),
        }]
        _save_usage(usage)


def get_usage_stats() -> dict:
    """Get today's usage stats."""
    data = _load_usage()
    return {
        "date": data["date"],
        "ops_today": data["ops"],
        "ops_limit": 15_000,
        "ops_pct": round(data["ops"] / 15_000 * 100, 1),
        "errors_today": data["errors"],
        "recent_calls": data.get("calls", [])[-10:],
    }
