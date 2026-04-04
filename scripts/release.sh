#!/usr/bin/env bash
# Standard release workflow for burnr8.
# Usage: ./scripts/release.sh 0.5.0
#
# Steps:
#   1. Validates you're on main with clean tree
#   2. Runs full local CI
#   3. Bumps version in pyproject.toml
#   4. Commits, tags, pushes
#   5. Creates GitHub Release (triggers PyPI publish workflow)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

fail() { echo -e "${RED}ERROR:${NC} $1"; exit 1; }

cd "$(dirname "$0")/.."

# --- Validate args ---
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    echo "Usage: ./scripts/release.sh <version>"
    echo "Example: ./scripts/release.sh 0.5.0"
    exit 1
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    fail "Version must be semver (e.g. 0.5.0), got: $VERSION"
fi

# --- Validate state ---
BRANCH=$(git branch --show-current)
[ "$BRANCH" = "main" ] || fail "Must be on main branch (currently on $BRANCH)"

if [ -n "$(git status --porcelain)" ]; then
    fail "Working tree is not clean. Commit or stash changes first."
fi

git pull origin main --rebase || fail "Could not pull latest main"

echo -e "${YELLOW}Releasing burnr8 v${VERSION}${NC}"
echo ""

# --- Run local CI ---
echo -e "${YELLOW}Running local CI...${NC}"
./scripts/ci-local.sh || fail "Local CI failed. Fix issues before releasing."
echo ""

# --- Bump version ---
CURRENT=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
echo -e "Version: ${RED}${CURRENT}${NC} → ${GREEN}${VERSION}${NC}"

sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml

# --- Commit + tag + push ---
git add pyproject.toml
git commit -m "Release v${VERSION}"
git tag -a "v${VERSION}" -m "burnr8 v${VERSION}"
git push origin main --follow-tags

# --- Create GitHub Release ---
echo ""
echo -e "${YELLOW}Creating GitHub Release...${NC}"
gh release create "v${VERSION}" \
    --title "v${VERSION}" \
    --generate-notes

echo ""
echo -e "${GREEN}Released burnr8 v${VERSION}${NC}"
echo ""
echo "PyPI + Docker publish workflows triggered automatically."
echo "Check: https://github.com/HarrisonHesslink/burnr8/actions"
