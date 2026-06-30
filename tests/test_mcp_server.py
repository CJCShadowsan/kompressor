from __future__ import annotations

import json
import sys

import pytest

from kompressor.mcp_server import build_mcp_server, kompressor_compress, kompressor_retrieve, kompressor_stats


def test_mcp_helper_functions_round_trip(tmp_path):
    text = json.dumps([{"id": i, "kind": "event"} for i in range(20)])
    compressed = kompressor_compress(text, store_dir=str(tmp_path))
    telemetry = compressed["telemetry"]
    assert telemetry["rewrite_count"] == 1
    digest = telemetry["rewrites"][0]["stored_digest"]
    assert kompressor_retrieve(digest, store_dir=str(tmp_path))["content"] == text
    stats = kompressor_stats(store_dir=str(tmp_path))
    assert stats["requests"] == 0


def test_build_mcp_server_lists_tools():
    pytest.importorskip("mcp")

    import anyio

    async def list_tool_names() -> set[str]:
        return {tool.name for tool in await build_mcp_server().list_tools()}

    assert {"kompressor_compress", "kompressor_retrieve", "kompressor_stats"} <= anyio.run(list_tool_names)


def test_mcp_stdio_server_round_trip(tmp_path):
    pytest.importorskip("mcp")

    import anyio
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def run_client() -> None:
        text = json.dumps([{"id": i, "kind": "event"} for i in range(20)])
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "kompressor.mcp_server"],
        )
        async with (
            stdio_client(server) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
                await session.initialize()
                tools = await session.list_tools()
                assert {"kompressor_compress", "kompressor_retrieve", "kompressor_stats"} <= {
                    tool.name for tool in tools.tools
                }

                compressed = await session.call_tool(
                    "kompressor_compress",
                    {"text": text, "store_dir": str(tmp_path)},
                )
                assert not compressed.isError
                assert compressed.structuredContent is not None
                telemetry = compressed.structuredContent["telemetry"]
                assert telemetry["rewrite_count"] == 1

                digest = telemetry["rewrites"][0]["stored_digest"]
                retrieved = await session.call_tool(
                    "kompressor_retrieve",
                    {"digest": digest, "store_dir": str(tmp_path)},
                )
                assert not retrieved.isError
                assert retrieved.structuredContent is not None
                assert retrieved.structuredContent["content"] == text

    anyio.run(run_client)
