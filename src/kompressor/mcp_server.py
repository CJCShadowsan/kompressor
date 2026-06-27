"""Optional MCP server entrypoint for Kompressor Gateway retrieval."""

from __future__ import annotations

import sys
from typing import Any

from kompressor.gateway.models import GatewayConfig
from kompressor.gateway.rewriter import GatewayRewriter
from kompressor.gateway.stats import GatewayStats
from kompressor.gateway.store import OriginalStore


def kompressor_retrieve(digest: str, *, store_dir: str | None = None) -> dict[str, Any]:
    store = OriginalStore(store_dir)
    return {"digest": digest, "content": store.get_text(digest), "metadata": store.get_metadata(digest).to_dict()}


def kompressor_stats(*, store_dir: str | None = None) -> dict[str, Any]:
    store = OriginalStore(store_dir)
    return GatewayStats(store.root / "stats.json").load()


def kompressor_compress(text: str, *, mode: str = "strict", store_dir: str | None = None) -> dict[str, Any]:
    request = {"messages": [{"role": "user", "content": text}]}
    config = GatewayConfig(mode=mode, store_dir=store_dir, threshold_chars=0)  # type: ignore[arg-type]
    rewritten, telemetry = GatewayRewriter(config).rewrite_request(request)
    return {"request": rewritten, "telemetry": telemetry.to_dict()}


def main() -> None:
    try:
        import mcp  # noqa: F401
    except Exception:
        print("kompressor-mcp requires the optional MCP dependency: pip install 'kompressor[mcp]'", file=sys.stderr)
        raise SystemExit(2) from None
    print("Kompressor MCP helper functions are installed; wire them through your MCP host configuration.")
