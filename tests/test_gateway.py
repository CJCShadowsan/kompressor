from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from typer.testing import CliRunner

from kompressor.cli import app
from kompressor.gateway.http import _should_rewrite_route, create_gateway_server
from kompressor.gateway.models import GatewayConfig
from kompressor.gateway.policy import classify_result, decide_gateway_use
from kompressor.gateway.rewriter import GatewayRewriter
from kompressor.gateway.shapes import detect_request_format, iter_text_targets
from kompressor.gateway.stats import GatewayStats
from kompressor.gateway.store import OriginalStore
from kompressor.gateway.wrap import build_wrap_plan, print_cursor_settings
from kompressor.models import OptimizationResult, TokenStats

runner = CliRunner()


def _rows(count: int = 40) -> str:
    return json.dumps([{"id": i, "event": "auth_timeout_error", "severity": "CRITICAL"} for i in range(count)])


def test_gateway_config_defaults_to_strict() -> None:
    config = GatewayConfig()
    assert config.mode == "strict"
    assert config.allow_lossy is False
    assert config.enable_transport_compression is False


def test_original_store_round_trips_text(tmp_path: Path) -> None:
    store = OriginalStore(tmp_path)
    stored = store.put_text("hello", source="user_text")
    assert store.get_text(stored.digest) == "hello"
    assert store.get_metadata(stored.digest).chars == 5


def test_request_shape_iterates_openai_tool_content() -> None:
    request = {"messages": [{"role": "tool", "content": "x"}, {"role": "assistant", "tool_calls": []}]}
    assert detect_request_format(request) == "openai"
    targets = list(iter_text_targets(request, "openai"))
    assert targets[0].source == "tool_result"
    assert targets[0].text == "x"


def test_gateway_rewrites_openai_request_and_stores_original(tmp_path: Path) -> None:
    request = {
        "messages": [{"role": "user", "content": _rows()}],
        "tools": [{"type": "function", "function": {"name": "x"}}],
    }
    rewritten, telemetry = GatewayRewriter(GatewayConfig(store_dir=str(tmp_path), threshold_chars=0)).rewrite_request(
        request
    )
    assert telemetry.rewrite_count == 1
    assert "KOMPRESSOR_GATEWAY_INSTRUCTIONS" in json.dumps(rewritten)
    assert rewritten["tools"] == request["tools"]
    digest = telemetry.rewrites[0].stored_digest
    assert digest is not None
    assert OriginalStore(tmp_path).get_text(digest) == request["messages"][0]["content"]


def test_gateway_rewrites_anthropic_tool_result(tmp_path: Path) -> None:
    request = {"system": "s", "messages": [{"role": "user", "content": [{"type": "tool_result", "content": _rows()}]}]}
    rewritten, telemetry = GatewayRewriter(GatewayConfig(store_dir=str(tmp_path), threshold_chars=0)).rewrite_request(
        request
    )
    assert telemetry.request_format == "anthropic"
    assert telemetry.rewrite_count == 1
    assert rewritten["messages"][0]["content"][0]["content"] != request["messages"][0]["content"][0]["content"]


def test_gateway_stats_records_without_raw_text(tmp_path: Path) -> None:
    stats = GatewayStats(tmp_path / "stats.json")
    rewrite_request = {"messages": [{"role": "user", "content": _rows()}]}
    _, telemetry = GatewayRewriter(GatewayConfig(store_dir=str(tmp_path), threshold_chars=0)).rewrite_request(
        rewrite_request
    )
    payload = stats.record(telemetry)
    assert payload["requests"] == 1
    assert payload["rewrites"] == 1
    assert "auth_timeout_error" not in json.dumps(payload)


def test_gateway_policy_rejects_lossy_by_default() -> None:
    stats = TokenStats(100, 10, 25, 3, 22, 88.0, 0, 0, 0, "test")
    result = OptimizationResult("log_summary", "summary", "", stats, False)
    decision = decide_gateway_use(result, GatewayConfig(), retrieval_available=True, local_decode_available=False)
    assert decision.allowed is False
    assert decision.reason == "lossy_not_allowed"
    assert classify_result(result) == "lossy_analytical"


def test_gateway_rewrites_chatgpt_backend_response_routes() -> None:
    assert _should_rewrite_route("/backend-api/responses")
    assert _should_rewrite_route("/backend-api/codex/responses")


def test_wrap_plan_for_claudish_points_to_gateway() -> None:
    plan = build_wrap_plan("claudish", gateway_url="http://127.0.0.1:9999", args=("--model", "x"))
    assert plan.settings["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9999"
    assert plan.command[-2:] == ["--model", "x"]
    assert print_cursor_settings()["openai_base_url"].endswith("/v1")


class _FakeUpstream(BaseHTTPRequestHandler):
    seen: dict = {}

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        type(self).seen = json.loads(body.decode("utf-8"))
        payload = b'{"id":"ok","choices":[{"message":{"role":"assistant","content":"ok"}}]}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_gateway_http_rewrites_and_retrieves(tmp_path: Path) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    gateway = create_gateway_server(
        host="127.0.0.1",
        port=0,
        upstream=f"http://127.0.0.1:{upstream.server_address[1]}",
        config=GatewayConfig(store_dir=str(tmp_path), threshold_chars=0),
    )
    gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
    gateway_thread.start()
    try:
        base = f"http://127.0.0.1:{gateway.server_address[1]}"
        response = httpx.post(f"{base}/v1/chat/completions", json={"messages": [{"role": "user", "content": _rows()}]})
        assert response.status_code == 200
        assert response.headers["x-kompressor-rewrite-count"] == "1"
        assert _FakeUpstream.seen["messages"][0]["content"] != _rows()
        digest = gateway.last_telemetry["rewrites"][0]["stored_digest"]
        retrieved = httpx.get(f"{base}/v1/kompressor/retrieve/{digest}")
        assert retrieved.json()["content"] == _rows()
        stats = httpx.get(f"{base}/v1/kompressor/stats").json()
        assert stats["rewrites"] == 1
    finally:
        gateway.shutdown()
        gateway.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_gateway_cli_rewrite_json(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"messages": [{"role": "user", "content": _rows()}]}), encoding="utf-8")
    result = runner.invoke(app, ["gateway", "rewrite", str(request), "--store-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["telemetry"]["rewrite_count"] == 1


def test_wrap_cli_print_only() -> None:
    result = runner.invoke(app, ["wrap", "agent", "claudish", "--print-only", "--json", "--", "--model", "x"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["agent"] == "claudish"
