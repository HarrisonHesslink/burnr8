#!/usr/bin/env bash
# PreToolUse hook: check if burnr8 credentials are configured before any tool call.
# If ~/.burnr8/.env doesn't exist and env vars aren't set, block with setup instructions.
# Requires jq for JSON parsing.

# Read hook input from stdin (Claude Code passes JSON)
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# If jq is not available or tool_name is empty, allow (don't break things)
if [[ -z "$TOOL_NAME" ]]; then
    exit 0
fi

# Only check for burnr8 MCP tools
if [[ "$TOOL_NAME" != mcp__burnr8__* ]] && [[ "$TOOL_NAME" != mcp__claude_ai_BurnR8__* ]]; then
    exit 0
fi

# Check if credentials are available
if [[ -f "$HOME/.burnr8/.env" ]]; then
    exit 0
fi

if [[ -n "$GOOGLE_ADS_DEVELOPER_TOKEN" ]] && [[ -n "$GOOGLE_ADS_REFRESH_TOKEN" ]]; then
    exit 0
fi

# No credentials found — block and suggest setup
echo "burnr8 credentials not configured. Run: ! burnr8-setup"
exit 2
