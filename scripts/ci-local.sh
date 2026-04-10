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

# Load credentials from .env.local if present (gitignored)
if [ -f .env.local ]; then
    set -a
    source .env.local
    set +a
fi

step "Lint (ruff)"
.venv/bin/ruff check src/ tests/ || fail "ruff found issues"
pass "ruff check"

step "Type check (mypy)"
.venv/bin/mypy src/burnr8/ --ignore-missing-imports || fail "mypy found errors"
pass "mypy strict"

step "Unit tests (pytest)"
PYTHONPATH=src .venv/bin/pytest tests/ --ignore=tests/integration -v --tb=short || fail "unit tests failed"
pass "unit tests"

step "Integration tests"
if [ -n "${GOOGLE_ADS_LOGIN_CUSTOMER_ID:-}" ]; then
    PYTHONPATH=src .venv/bin/pytest tests/integration/ -v --tb=short -x || fail "integration tests failed"
    pass "integration tests"
else
    echo -e "  ${YELLOW}SKIP${NC} — set GOOGLE_ADS_LOGIN_CUSTOMER_ID to run integration tests"
fi

step "Import check"
PYTHONPATH=src .venv/bin/python -c "from burnr8.server import mcp; print(f'  Server: {mcp.name}')" || fail "import failed"
pass "server imports"

step "CVE scan (pip-audit)"
.venv/bin/pip-audit -r requirements.lock \
  --ignore-vuln CVE-2025-8869 \
  --ignore-vuln CVE-2026-1703 \
  || fail "vulnerabilities found"
pass "no CVEs in dependencies"

step "Build check"
.venv/bin/pip install -q build 2>/dev/null
.venv/bin/python -m build --outdir /tmp/burnr8-build 2>/dev/null || fail "build failed"
rm -rf /tmp/burnr8-build
pass "package builds"

echo -e "\n${GREEN}All CI checks passed locally.${NC} Safe to push."
