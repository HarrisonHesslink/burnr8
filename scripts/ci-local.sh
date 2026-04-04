#!/usr/bin/env bash
# Run the full CI pipeline locally before pushing.
# Usage: ./scripts/ci-local.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; exit 1; }
step() { echo -e "\n${YELLOW}=== $1 ===${NC}"; }

cd "$(dirname "$0")/.."

step "Lint (ruff)"
.venv/bin/ruff check src/ tests/ || fail "ruff found issues"
pass "ruff check"

step "Tests (pytest)"
PYTHONPATH=src .venv/bin/pytest tests/ -v --tb=short || fail "tests failed"
pass "pytest"

step "Import check"
PYTHONPATH=src .venv/bin/python -c "from burnr8.server import mcp; print(f'  Server: {mcp.name}')" || fail "import failed"
pass "server imports"

step "CVE scan (pip-audit)"
.venv/bin/pip-audit -r requirements.lock \
  --ignore-vuln CVE-2025-8869 \
  --ignore-vuln CVE-2026-1703 \
  || fail "vulnerabilities found"
pass "no CVEs in dependencies"

step "Verify direct dependencies"
.venv/bin/pip show google-ads > /tmp/dep-check 2>&1 && grep -qi "google" /tmp/dep-check || fail "google-ads not verified"
.venv/bin/pip show fastmcp > /tmp/dep-check 2>&1 && grep -qi "fastmcp\|prefect" /tmp/dep-check || fail "fastmcp not verified"
.venv/bin/pip show python-dotenv > /tmp/dep-check 2>&1 && grep -qi "dotenv" /tmp/dep-check || fail "python-dotenv not verified"
rm -f /tmp/dep-check
pass "direct deps verified"

step "Build check"
.venv/bin/pip install -q build 2>/dev/null
.venv/bin/python -m build --outdir /tmp/burnr8-build 2>/dev/null || fail "build failed"
rm -rf /tmp/burnr8-build
pass "package builds"

echo -e "\n${GREEN}All CI checks passed locally.${NC} Safe to push."
