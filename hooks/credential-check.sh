#!/usr/bin/env bash
# PreToolUse hook: check if burnr8 credentials are configured before any tool call.
# If ~/.burnr8/.env doesn't exist and env vars aren't set, block with setup instructions.

# Only check for burnr8 MCP tools
TOOL_NAME="${MCP_TOOL_NAME:-}"
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
