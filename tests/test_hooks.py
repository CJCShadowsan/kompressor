from __future__ import annotations

import json

from kompressor.gateway.models import GatewayConfig
from kompressor.hooks import request_rewrite_hook


def _request() -> dict[str, object]:
    return {"messages": [{"role": "user", "content": json.dumps([{"id": i, "kind": "event"} for i in range(20)])}]}


def test_request_rewrite_hook_accepts_raw_request(tmp_path) -> None:
    result = request_rewrite_hook(
        _request(),
        GatewayConfig(store_dir=str(tmp_path), threshold_chars=0),
    )
    assert result["decision"] == "rewrite"
    assert result["hook"]["name"] == "kompressor.request_rewrite"
    assert result["telemetry"]["rewrite_count"] == 1
    contents = [message["content"] for message in result["request"]["messages"]]
    assert any(content.startswith("<kompressor:schema_rows_v1>") for content in contents)


def test_request_rewrite_hook_accepts_envelope(tmp_path) -> None:
    result = request_rewrite_hook(
        {"event": "model_request", "request": _request()},
        GatewayConfig(store_dir=str(tmp_path), threshold_chars=0),
    )
    assert result["decision"] == "rewrite"
    assert result["telemetry"]["rewrites"][0]["source"] == "user_text"
