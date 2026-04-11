#!/bin/bash
# Verify unit tests pass before Claude stops. Blocks if tests fail.
cd "$CLAUDE_PROJECT_DIR" || exit 0

# Check if any Python files changed (uncommitted OR in recent commits on this branch)
HAS_CHANGES=false
if git diff --name-only HEAD 2>/dev/null | grep -q '\.py$'; then
  HAS_CHANGES=true
elif git diff --name-only main...HEAD 2>/dev/null | grep -q '\.py$'; then
  HAS_CHANGES=true
fi

if [ "$HAS_CHANGES" = false ]; then
  exit 0
fi

OUTPUT=$(.venv/bin/pytest tests/ -x -q --ignore=tests/integration --tb=line 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  SUMMARY=$(echo "$OUTPUT" | tail -5)
  echo "{\"decision\": \"block\", \"reason\": \"Tests are failing. Fix before finishing:\\n$SUMMARY\"}"
  exit 0
fi

exit 0
