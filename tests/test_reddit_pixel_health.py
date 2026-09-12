"""Read-only pixel signal diagnostics through the real MCP boundary."""

import asyncio
from unittest.mock import MagicMock

from fastmcp import Client, FastMCP

from burnr8.tools.reddit_creation import register


def test_pixel_health_requires_account_link_and_reports_received_timestamps(monkeypatch):
    api = MagicMock()
    api.request.side_effect = [
        {"data": [{"id": "a2_pixel"}]},
        {"data": {"page_visit": "2026-09-12T19:00:00Z", "sign_up": None, "purchase": None}},
    ]
    monkeypatch.setattr("burnr8.tools.reddit_creation.get_reddit_client", lambda: api)
    mcp = FastMCP("pixel-health-test")
    register(mcp)

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "reddit_get_pixel_health", {"account_id": "a2_account", "pixel_id": "a2_pixel"}
            )
            assert result.data["last_fired_at"]["sign_up"] is None
            assert result.data["pixel_id"] == "a2_pixel"
            assert "ingestion" in result.data["interpretation"]

    asyncio.run(run())
    assert all(call.args[0] == "GET" for call in api.request.call_args_list)
    assert api.request.call_args_list[-1].args == ("GET", "pixels/a2_pixel/last_fired_at")


def test_unlinked_pixel_is_not_queried(monkeypatch):
    api = MagicMock()
    api.request.return_value = {"data": [{"id": "a2_other"}]}
    monkeypatch.setattr("burnr8.tools.reddit_creation.get_reddit_client", lambda: api)
    mcp = FastMCP("pixel-health-ownership")
    register(mcp)

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "reddit_get_pixel_health", {"account_id": "a2_account", "pixel_id": "a2_pixel"}, raise_on_error=False
            )
            assert result.is_error or result.data.get("error")

    asyncio.run(run())
    assert len(api.request.call_args_list) == 1
