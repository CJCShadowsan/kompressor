"""Optional MCP server entrypoint for Kompressor Gateway retrieval."""

from __future__ import annotations

import sys
from typing import Any

from kompressor.gateway.models import GatewayConfig
from kompressor.gateway.rewriter import GatewayRewriter
from kompressor.gateway.stats import GatewayStats
from kompressor.gateway.store import OriginalStore


def kompressor_retrieve(digest: str, *, store_dir: str | None = None) -> dict[str, Any]:
    """Retrieve exact original text from the local Kompressor store by digest."""
    store = OriginalStore(store_dir)
    return {"digest": digest, "content": store.get_text(digest), "metadata": store.get_metadata(digest).to_dict()}


def kompressor_stats(*, store_dir: str | None = None) -> dict[str, Any]:
    """Return raw-text-free Kompressor gateway statistics."""
    store = OriginalStore(store_dir)
    return GatewayStats(store.root / "stats.json").load()


def kompressor_compress(text: str, *, mode: str = "strict", store_dir: str | None = None) -> dict[str, Any]:
    """Compress text as an OpenAI-style user message and return the rewritten request plus telemetry."""
    request = {"messages": [{"role": "user", "content": text}]}
    config = GatewayConfig(mode=mode, store_dir=store_dir, threshold_chars=0)  # type: ignore[arg-type]
    rewritten, telemetry = GatewayRewriter(config).rewrite_request(request)
    return {"request": rewritten, "telemetry": telemetry.to_dict()}


def build_mcp_server() -> Any:
    """Build the stdio-capable FastMCP server.

    The import stays optional so the core package can be installed without the
    MCP extra and still expose the Python helper functions above.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("kompressor-mcp requires the optional MCP dependency: pip install 'kompressor[mcp]'", file=sys.stderr)
        raise SystemExit(2) from None

    server = FastMCP(
        "kompressor",
        instructions=(
            "Use these tools to compress oversized context, inspect Kompressor gateway savings, "
            "and retrieve exact originals from the local Kompressor content store."
        ),
    )
    server.tool()(kompressor_compress)
    server.tool()(kompressor_retrieve)
    server.tool()(kompressor_stats)
    return server


def main() -> None:
    build_mcp_server().run("stdio")


if __name__ == "__main__":
    main()
