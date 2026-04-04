"""Report export utilities — saves full data to CSV, returns summary to Claude."""

import csv
import os
from datetime import UTC, datetime
from pathlib import Path

REPORTS_DIR = Path(os.environ.get("BURNR8_REPORTS_DIR", os.path.expanduser("~/.burnr8/reports")))

# Characters that trigger formula execution in Excel/LibreOffice
_FORMULA_CHARS = frozenset("=+-@|%")


def _sanitize_cell(value: object) -> object:
    """Prevent CSV formula injection by prefixing dangerous cells with a single quote."""
    if isinstance(value, str) and value and value[0] in _FORMULA_CHARS:
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
    total_bytes = sum(f.stat().st_size for f in files if f.exists())
    oldest = min((f.stat().st_mtime for f in files), default=None) if files else None

    return {
        "report_files": len(files),
        "total_size_mb": round(total_bytes / 1_048_576, 2),
        "oldest_file": datetime.fromtimestamp(oldest, tz=UTC).strftime("%Y-%m-%d") if oldest else None,
        "reports_dir": str(REPORTS_DIR),
    }


def save_report(rows: list[dict], report_name: str, top_n: int = 10) -> dict:
    """Save a list of dicts as CSV and return a summary with top rows + file path.

    - Sanitizes cells to prevent CSV formula injection
    - Writes with restrictive permissions (0o600)
    - Auto-prunes files older than 7 days

    Args:
        rows: Full result set from a GAQL query
        report_name: Name for the file (e.g. "search_terms", "keyword_performance")
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

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Auto-prune old reports
    _prune_old_reports(max_age_days=7)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    filename = f"{report_name}_{timestamp}.csv"
    filepath = REPORTS_DIR / filename

    # Write CSV with restrictive permissions and formula sanitization
    fieldnames = list(rows[0].keys())
    fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
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
