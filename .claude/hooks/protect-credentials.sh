#!/bin/bash
# Block edits to credential files and sensitive directories.
INPUT=$(cat)
FILE=$(python3 -c "import sys,json; print(json.loads(sys.argv[1]).get('tool_input',{}).get('file_path',''))" "$INPUT" 2>/dev/null)

if [ -z "$FILE" ]; then
  exit 0
fi

# Block .env files (except .env.example)
if [[ "$FILE" =~ \.env($|\.) ]] && [[ ! "$FILE" =~ \.env\.example$ ]]; then
  echo "Blocked: cannot edit credential file '$FILE'. Edit manually." >&2
  exit 2
fi

# Block ~/.burnr8/ directory (credentials, logs)
if [[ "$FILE" =~ \.burnr8/ ]]; then
  echo "Blocked: cannot edit burnr8 runtime directory '$FILE'." >&2
  exit 2
fi

# Block Google OAuth credential files
if [[ "$FILE" =~ google.*credentials|client_secret.*\.json ]]; then
  echo "Blocked: cannot edit Google OAuth credential file '$FILE'." >&2
  exit 2
fi

exit 0
