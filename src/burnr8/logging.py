import contextvars
import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.environ.get("BURNR8_LOG_DIR", os.path.expanduser("~/.burnr8/logs")))
LOG_LEVEL = os.environ.get("BURNR8_LOG_LEVEL", "INFO").upper()
USAGE_FILE = LOG_DIR / "usage.json"

_logger: logging.Logger | None = None
_usage_lock = threading.Lock()
_usage_cache: dict | None = None

# Correlation ID for tracing multi-tool workflows (e.g. quick_audit → 6 GAQL queries)
correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    """Generate and set a new correlation ID. Returns the ID."""
    cid = uuid.uuid4().hex[:12]
    correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    """Get the current correlation ID, or None if not set."""
    return correlation_id.get()


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
                _logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
                # Rotating handler: 10MB max, 3 backups
                handler = RotatingFileHandler(
                    log_path, maxBytes=10_000_000, backupCount=3
                )
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
    cid = get_correlation_id()
    if cid:
        msg += f" cid={cid}"
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
        "log_file": str(LOG_DIR / "burnr8.log"),
        "log_level": LOG_LEVEL,
    }


def get_recent_errors(limit: int = 20) -> list[dict]:
    """Read recent ERROR lines from burnr8.log. Returns parsed log entries."""
    log_path = LOG_DIR / "burnr8.log"
    if not log_path.exists():
        return []

    errors = []
    try:
        with open(log_path) as f:
            for line in f:
                if " ERROR " in line:
                    errors.append({"raw": line.strip()})
    except OSError:
        return []

    return errors[-limit:]
