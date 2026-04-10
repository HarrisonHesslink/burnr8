#!/bin/bash
# Block destructive shell commands that are hard to reverse.
INPUT=$(cat)
COMMAND=$(python3 -c "import sys,json; print(json.loads(sys.argv[1]).get('tool_input',{}).get('command',''))" "$INPUT" 2>/dev/null)

if [ -z "$COMMAND" ]; then
  exit 0
fi

# Block rm -rf (except safe dirs like .pytest_cache, __pycache__, dist, build)
if echo "$COMMAND" | grep -qE 'rm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--force.*-r|-rf)' && \
   ! echo "$COMMAND" | grep -qE '(\.pytest_cache|__pycache__|dist/|build/|\.hypothesis)'; then
  echo "Blocked: recursive force-delete is too risky. Run manually if needed." >&2
  exit 2
fi

# Block force push
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*--force'; then
  echo "Blocked: force push can destroy remote history. Run manually if needed." >&2
  exit 2
fi

# Block git reset --hard
if echo "$COMMAND" | grep -qE 'git\s+reset\s+--hard'; then
  echo "Blocked: git reset --hard discards uncommitted work. Run manually if needed." >&2
  exit 2
fi

# Block pip uninstall without confirmation
if echo "$COMMAND" | grep -qE 'pip\s+uninstall\s+-y'; then
  echo "Blocked: bulk package removal. Run manually if needed." >&2
  exit 2
fi

exit 0
