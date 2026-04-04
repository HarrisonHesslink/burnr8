#!/usr/bin/env bash
# Standard release workflow for burnr8.
# Usage: ./scripts/release.sh 0.5.0
#
# Steps:
#   1. Validates you're on main with clean tree
#   2. Runs full local CI
#   3. Bumps version in pyproject.toml
#   4. Creates a PR for the version bump (branch protection)
#   5. After PR merges: tags, creates GitHub Release
#   6. Triggers PyPI + Docker publish workflows

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
if [ "$CURRENT" = "$VERSION" ]; then
    echo -e "Version already ${GREEN}${VERSION}${NC}, skipping bump."
else
    echo -e "Version: ${RED}${CURRENT}${NC} → ${GREEN}${VERSION}${NC}"

    # Bump all version files in sync
    sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
    sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"${VERSION}\"/g" .claude-plugin/marketplace.json
    sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"${VERSION}\"/g" .claude-plugin/plugin.json
    sed -i "s/version: .*/version: ${VERSION}/" skills/google-ads-audit/SKILL.md

    # --- Create PR for version bump (branch protection) ---
    RELEASE_BRANCH="release-v${VERSION}"
    git checkout -b "$RELEASE_BRANCH"
    git add pyproject.toml .claude-plugin/marketplace.json .claude-plugin/plugin.json skills/google-ads-audit/SKILL.md
    git commit -m "Release v${VERSION}"
    git push -u origin "$RELEASE_BRANCH"

    PR_URL=$(gh pr create --title "Release v${VERSION}" --body "Version bump to ${VERSION}. Merge to trigger release.")
    echo ""
    echo -e "${YELLOW}PR created: ${PR_URL}${NC}"
    echo -e "${YELLOW}Merge the PR, then run:${NC}"
    echo ""
    echo "  ./scripts/release.sh ${VERSION}"
    echo ""
    echo "The script will detect the version is already bumped and proceed to tag + release."
    git checkout main
    exit 0
fi

# --- Version already matches, tag and release ---
echo ""
echo -e "${YELLOW}Tagging v${VERSION}...${NC}"

# Clean up any stale tag
git tag -d "v${VERSION}" 2>/dev/null || true
git push origin ":refs/tags/v${VERSION}" 2>/dev/null || true

git tag -a "v${VERSION}" -m "burnr8 v${VERSION}"
git push origin "v${VERSION}"

# --- Create GitHub Release ---
echo ""
echo -e "${YELLOW}Creating GitHub Release...${NC}"

# Delete stale release if exists
gh release delete "v${VERSION}" --yes 2>/dev/null || true

gh release create "v${VERSION}" \
    --title "v${VERSION}" \
    --generate-notes

echo ""
echo -e "${GREEN}Released burnr8 v${VERSION}${NC}"
echo ""
echo "PyPI + Docker publish workflows triggered automatically."
echo "Check: https://github.com/HarrisonHesslink/burnr8/actions"
