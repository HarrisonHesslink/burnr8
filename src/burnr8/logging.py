import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.environ.get("BURNR8_LOG_DIR", os.path.expanduser("~/.burnr8/logs")))
USAGE_FILE = LOG_DIR / "usage.json"

_logger: logging.Logger | None = None
_usage_lock = threading.Lock()


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _logger = logging.getLogger("burnr8")
        _logger.setLevel(logging.INFO)
        handler = logging.FileHandler(LOG_DIR / "burnr8.log")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        _logger.addHandler(handler)
    return _logger


def _load_usage() -> dict:
    """Load today's usage data from disk."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(USAGE_FILE)


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
        usage = _load_usage()
        usage["ops"] += 1
        if status == "error":
            usage["errors"] += 1

        # Keep last 50 calls
        usage["calls"] = usage.get("calls", [])[-49:] + [{
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
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
