from __future__ import annotations

import json

from kompressor.mcp_server import kompressor_compress, kompressor_retrieve, kompressor_stats


def test_mcp_helper_functions_round_trip(tmp_path):
    text = json.dumps([{"id": i, "kind": "event"} for i in range(20)])
    compressed = kompressor_compress(text, store_dir=str(tmp_path))
    telemetry = compressed["telemetry"]
    assert telemetry["rewrite_count"] == 1
    digest = telemetry["rewrites"][0]["stored_digest"]
    assert kompressor_retrieve(digest, store_dir=str(tmp_path))["content"] == text
    stats = kompressor_stats(store_dir=str(tmp_path))
    assert stats["requests"] == 0
