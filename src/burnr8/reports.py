"""Report export utilities — saves full data to CSV, returns summary to Claude."""

import csv
import os
from datetime import UTC, datetime
from pathlib import Path

REPORTS_DIR = Path(os.environ.get("BURNR8_REPORTS_DIR", os.path.expanduser("~/.burnr8/reports")))


def save_report(rows: list[dict], report_name: str, top_n: int = 10) -> dict:
    """Save a list of dicts as CSV and return a summary with top rows + file path.

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
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    filename = f"{report_name}_{timestamp}.csv"
    filepath = REPORTS_DIR / filename

    # Write CSV
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "file": str(filepath),
        "rows": len(rows),
        "columns": fieldnames,
        "top": rows[:top_n],
    }
