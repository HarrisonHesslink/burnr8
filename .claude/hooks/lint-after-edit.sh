#!/bin/bash
# Auto-lint Python files after edits. Surfaces ruff errors as feedback.
INPUT=$(cat)
FILE=$(python3 -c "import sys,json; print(json.loads(sys.argv[1]).get('tool_input',{}).get('file_path',''))" "$INPUT" 2>/dev/null)

# Only check Python files
if [[ ! "$FILE" =~ \.py$ ]]; then
  exit 0
fi

# Skip if file doesn't exist (was deleted)
if [ ! -f "$FILE" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 0

OUTPUT=$(.venv/bin/ruff check "$FILE" 2>&1)
if [ $? -ne 0 ]; then
  echo "ruff found issues in $FILE:" >&2
  echo "$OUTPUT" >&2
fi

exit 0
