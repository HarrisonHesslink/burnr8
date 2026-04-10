#!/bin/bash
# Auto-regenerate lockfiles when pyproject.toml dependencies change.
INPUT=$(cat)
FILE=$(python3 -c "import sys,json; print(json.loads(sys.argv[1]).get('tool_input',{}).get('file_path',''))" "$INPUT" 2>/dev/null)

if [[ "$FILE" != *"pyproject.toml" ]]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 0

echo "pyproject.toml changed — regenerating lockfiles..." >&2
.venv/bin/pip-compile pyproject.toml --generate-hashes --output-file=requirements.lock --strip-extras --allow-unsafe --quiet 2>&1 >&2
.venv/bin/pip-compile pyproject.toml --extra=dev --generate-hashes --output-file=requirements-dev.lock --strip-extras --allow-unsafe --quiet 2>&1 >&2
echo "Lockfiles regenerated." >&2

exit 0
