#!/bin/bash
# Verify unit tests pass before Claude stops. Blocks if tests fail.
cd "$CLAUDE_PROJECT_DIR" || exit 0

# Check if any Python source files were modified in the working tree
if ! git diff --name-only HEAD 2>/dev/null | grep -q '\.py$'; then
  # No Python changes — skip test verification
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
