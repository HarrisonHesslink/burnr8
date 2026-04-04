"""Report export utilities — saves full data to CSV, returns summary to Claude."""

import csv
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPORTS_DIR = Path(os.environ.get("BURNR8_REPORTS_DIR", os.path.expanduser("~/.burnr8/reports")))

# Characters that trigger formula execution in Excel/LibreOffice
_FORMULA_CHARS = frozenset("=+-@|%")
# Control chars used for tab/newline injection in CSV
_CONTROL_CHARS = str.maketrans("", "", "\t\r\n")
# Only allow safe characters in report names
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _sanitize_cell(value: object) -> object:
    """Prevent CSV formula injection — strips control chars and prefixes dangerous cells."""
    if isinstance(value, str) and value:
        # Strip tab/newline injection vectors first
        value = value.translate(_CONTROL_CHARS)
        if value and value[0] in _FORMULA_CHARS:
            return "'" + value
    return value


def _sanitize_row(row: dict) -> dict:
    """Sanitize all string values in a row dict."""
    return {k: _sanitize_cell(v) for k, v in row.items()}


def _prune_old_reports(max_age_days: int = 7) -> int:
    """Delete report CSVs older than max_age_days. Returns count of deleted files."""
    if not REPORTS_DIR.exists():
        return 0
    cutoff = datetime.now(UTC).timestamp() - max_age_days * 86400
    deleted = 0
    for f in REPORTS_DIR.glob("*.csv"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                deleted += 1
        except OSError:
            pass
    return deleted


def get_storage_stats() -> dict:
    """Get report storage stats: file count, total size, oldest file."""
    if not REPORTS_DIR.exists():
        return {"report_files": 0, "total_size_mb": 0, "oldest_file": None}

    files = list(REPORTS_DIR.glob("*.csv"))
    if not files:
        return {"report_files": 0, "total_size_mb": 0, "oldest_file": None, "reports_dir": str(REPORTS_DIR)}

    # Single stat() per file
    file_stats = [f.stat() for f in files if f.exists()]
    total_bytes = sum(s.st_size for s in file_stats)
    oldest = min((s.st_mtime for s in file_stats), default=None)

    return {
        "report_files": len(files),
        "total_size_mb": round(total_bytes / 1_048_576, 2),
        "oldest_file": datetime.fromtimestamp(oldest, tz=UTC).strftime("%Y-%m-%d") if oldest else None,
        "reports_dir": str(REPORTS_DIR),
    }


def save_report(rows: list[dict], report_name: str, top_n: int = 10) -> dict:
    """Save a list of dicts as CSV and return a summary with top rows + file path.

    Security:
    - Validates report_name (alphanumeric + hyphens/underscores only)
    - Sanitizes cells to prevent CSV formula injection (including tab/newline bypass)
    - Writes with restrictive permissions (0o600)
    - Checks REPORTS_DIR is not a symlink

    Disk management:
    - Auto-prunes files older than 7 days
    - Uses UUID suffix to prevent filename collisions

    Args:
        rows: Full result set from a GAQL query
        report_name: Name for the file (alphanumeric, hyphens, underscores only)
        top_n: Number of rows to include inline in the summary

    Returns:
        dict with file path, row count, top rows, and the full column list
    """
    if not rows:
        return {
            "file": None,
            "rows": 0,
            "top": [],
            "message": "No data returned.",
        }

    # Validate report_name to prevent path traversal
    if not _SAFE_NAME.match(report_name):
        return {"error": True, "message": f"Invalid report_name: {report_name!r}"}

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Refuse to write into symlinked directories
    if REPORTS_DIR.is_symlink():
        return {"error": True, "message": f"REPORTS_DIR is a symlink — refusing to write: {REPORTS_DIR}"}

    # Auto-prune old reports
    _prune_old_reports(max_age_days=7)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    filename = f"{report_name}_{timestamp}_{suffix}.csv"
    filepath = REPORTS_DIR / filename

    # Write CSV with restrictive permissions and formula sanitization
    fieldnames = list(rows[0].keys())
    fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with open(fd, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_sanitize_row(row))

    return {
        "file": str(filepath),
        "rows": len(rows),
        "columns": fieldnames,
        "top": rows[:top_n],
    }
