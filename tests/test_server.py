"""Tests for burnr8.server — MCP server initialization and registration."""

import asyncio


def test_server_import():
    """Server module should import without credentials."""
    from burnr8.server import mcp
    assert mcp.name == "burnr8"


def test_tool_count():
    """Verify expected tool count."""
    from burnr8.server import mcp
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 61


def test_all_tools_have_descriptions():
    """Every tool should have a non-empty description."""
    from burnr8.server import mcp
    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        assert tool.description, f"Tool {tool.name} has no description"
        assert len(tool.description) > 10, f"Tool {tool.name} description too short"


def test_prompts_registered():
    """Verify all expected prompts are registered."""
    from burnr8.server import mcp
    prompts = asyncio.run(mcp.list_prompts())
    names = {p.name for p in prompts}
    assert "audit" in names
    assert "optimize" in names
    assert "new_campaign" in names


def test_resources_registered():
    """Verify expected resources are registered."""
    from burnr8.server import mcp
    resources = asyncio.run(mcp.list_resources())
    assert len(resources) >= 2


def test_resource_templates_registered():
    """Verify expected resource templates are registered."""
    from burnr8.server import mcp
    templates = asyncio.run(mcp.list_resource_templates())
    assert len(templates) >= 3


def test_tool_names_are_unique():
    """All tool names should be unique."""
    from burnr8.server import mcp
    tools = asyncio.run(mcp.list_tools())
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), f"Duplicate tool names found: {[n for n in names if names.count(n) > 1]}"


def test_prompt_count():
    """Verify expected prompt count."""
    from burnr8.server import mcp
    prompts = asyncio.run(mcp.list_prompts())
    assert len(prompts) == 3
