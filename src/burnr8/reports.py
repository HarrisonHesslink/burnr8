"""Report export utilities — saves full data to CSV, returns summary to Claude.

Supports pluggable output backends via BURNR8_REPORT_MODE env var:
- "disk" (default): writes CSV to ~/.burnr8/reports/
- "supabase": uploads CSV to Supabase Storage, returns signed URL
"""

import csv
import io
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPORT_MODE = os.environ.get("BURNR8_REPORT_MODE", "disk")
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
        value = value.translate(_CONTROL_CHARS)
        if value and value[0] in _FORMULA_CHARS:
            return "'" + value
    return value


def _sanitize_row(row: dict) -> dict:
    """Sanitize all string values in a row dict."""
    return {k: _sanitize_cell(v) for k, v in row.items()}


def _rows_to_csv_bytes(rows: list[dict], fieldnames: list[str]) -> bytes:
    """Render sanitized rows as CSV bytes (UTF-8). Shared by both handlers."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(_sanitize_row(row))
    return buf.getvalue().encode("utf-8")


def _generate_filename(report_name: str) -> str:
    """Generate a collision-resistant filename."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{report_name}_{timestamp}_{suffix}.csv"


# ---------------------------------------------------------------------------
# Disk handler (default, self-hosted)
# ---------------------------------------------------------------------------


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


def _save_to_disk(rows: list[dict], fieldnames: list[str], report_name: str, top_n: int) -> dict:
    """Write CSV to local disk with restrictive permissions."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if REPORTS_DIR.is_symlink():
        return {"error": True, "message": f"REPORTS_DIR is a symlink — refusing to write: {REPORTS_DIR}"}

    _prune_old_reports(max_age_days=7)

    filename = _generate_filename(report_name)
    filepath = REPORTS_DIR / filename

    csv_bytes = _rows_to_csv_bytes(rows, fieldnames)
    fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with open(fd, "wb") as f:
        f.write(csv_bytes)

    return {
        "file": str(filepath),
        "rows": len(rows),
        "columns": fieldnames,
        "top": rows[:top_n],
    }


# ---------------------------------------------------------------------------
# Supabase Storage handler (hosted/burnrate.sh)
# ---------------------------------------------------------------------------


def _save_to_supabase(rows: list[dict], fieldnames: list[str], report_name: str, top_n: int) -> dict:
    """Upload CSV to Supabase Storage and return a signed download URL."""
    try:
        import requests
    except ImportError:
        return {"error": True, "message": "requests package required for Supabase mode"}

    supabase_url = os.environ.get("BURNR8_SUPABASE_URL")
    supabase_key = os.environ.get("BURNR8_SUPABASE_KEY")
    bucket = os.environ.get("BURNR8_SUPABASE_BUCKET", "reports")

    if not supabase_url or not supabase_key:
        return {"error": True, "message": "BURNR8_SUPABASE_URL and BURNR8_SUPABASE_KEY required for Supabase mode"}

    filename = _generate_filename(report_name)
    csv_bytes = _rows_to_csv_bytes(rows, fieldnames)

    # Upload to Supabase Storage
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "text/csv",
        "x-upsert": "false",
    }

    try:
        resp = requests.post(upload_url, headers=headers, data=csv_bytes, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return {"error": True, "message": f"Supabase upload failed: {e}"}

    # Create signed URL (24 hour expiry)
    sign_url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{filename}"
    sign_headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    try:
        sign_resp = requests.post(
            sign_url,
            headers=sign_headers,
            json={"expiresIn": 86400},
            timeout=10,
        )
        sign_resp.raise_for_status()
        signed_url = f"{supabase_url}/storage/v1{sign_resp.json()['signedURL']}"
    except Exception:
        # Upload succeeded but signing failed — return the public path as fallback
        signed_url = f"{supabase_url}/storage/v1/object/public/{bucket}/{filename}"

    return {
        "url": signed_url,
        "rows": len(rows),
        "columns": fieldnames,
        "top": rows[:top_n],
    }


# ---------------------------------------------------------------------------
# Storage stats
# ---------------------------------------------------------------------------


def get_storage_stats() -> dict:
    """Get report storage stats. Disk mode returns file count/size. Supabase mode returns mode indicator."""
    if REPORT_MODE == "supabase":
        return {
            "report_mode": "supabase",
            "supabase_bucket": os.environ.get("BURNR8_SUPABASE_BUCKET", "reports"),
        }

    if not REPORTS_DIR.exists():
        return {"report_mode": "disk", "report_files": 0, "total_size_mb": 0, "oldest_file": None}

    files = list(REPORTS_DIR.glob("*.csv"))
    if not files:
        return {"report_mode": "disk", "report_files": 0, "total_size_mb": 0, "oldest_file": None, "reports_dir": str(REPORTS_DIR)}

    file_stats = [f.stat() for f in files if f.exists()]
    total_bytes = sum(s.st_size for s in file_stats)
    oldest = min((s.st_mtime for s in file_stats), default=None)

    return {
        "report_mode": "disk",
        "report_files": len(files),
        "total_size_mb": round(total_bytes / 1_048_576, 2),
        "oldest_file": datetime.fromtimestamp(oldest, tz=UTC).strftime("%Y-%m-%d") if oldest else None,
        "reports_dir": str(REPORTS_DIR),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def save_report(rows: list[dict], report_name: str, top_n: int = 10) -> dict:
    """Save rows as CSV and return summary + location (file path or URL).

    The output backend is controlled by BURNR8_REPORT_MODE:
    - "disk" (default): writes to ~/.burnr8/reports/, returns {"file": "..."}
    - "supabase": uploads to Supabase Storage, returns {"url": "..."}

    Shared behavior (both modes):
    - Validates report_name (path traversal prevention)
    - Sanitizes cells (CSV formula injection + control char injection)
    - Returns top_n rows inline for context efficiency
    """
    if not rows:
        return {
            "file": None,
            "url": None,
            "rows": 0,
            "top": [],
            "message": "No data returned.",
        }

    if not _SAFE_NAME.match(report_name):
        return {"error": True, "message": f"Invalid report_name: {report_name!r}"}

    fieldnames = list(rows[0].keys())

    if REPORT_MODE == "supabase":
        return _save_to_supabase(rows, fieldnames, report_name, top_n)
    else:
        return _save_to_disk(rows, fieldnames, report_name, top_n)
