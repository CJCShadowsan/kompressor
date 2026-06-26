import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

from kompressor.anthropic_proxy import create_anthropic_proxy_server
from kompressor.proxy import KOMPRESSOR_SYSTEM_MARKER, rewrite_anthropic_messages_request

BIG_JSON = json.dumps([{"id": idx, "event": "auth_timeout_error", "service": "api"} for idx in range(80)])


def test_rewrite_anthropic_string_user_content() -> None:
    request = {"model": "claude-test", "messages": [{"role": "user", "content": BIG_JSON}]}

    rewritten, metadata = rewrite_anthropic_messages_request(request, threshold_chars=20)

    assert metadata.rewrite_count == 1
    assert "<kompressor:" in rewritten["messages"][0]["content"]
    assert KOMPRESSOR_SYSTEM_MARKER in rewritten["system"]


def test_rewrite_anthropic_blocks_and_preserve_non_text() -> None:
    request = {
        "model": "claude-test",
        "system": [{"type": "text", "text": "existing"}],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": BIG_JSON},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}},
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": BIG_JSON},
                ],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}]},
        ],
    }

    rewritten, metadata = rewrite_anthropic_messages_request(request, threshold_chars=20)

    assert metadata.rewrite_count == 2
    blocks = rewritten["messages"][0]["content"]
    assert "<kompressor:" in blocks[0]["text"]
    assert blocks[1] == request["messages"][0]["content"][1]
    assert "<kompressor:" in blocks[2]["content"]
    assert rewritten["messages"][1] == request["messages"][1]
    assert rewritten["system"][0]["text"] == "existing"
    assert KOMPRESSOR_SYSTEM_MARKER in rewritten["system"][1]["text"]


def test_rewrite_skips_already_compressed() -> None:
    payload = "<kompressor:schema_rows_v1>\n{}\n@rows\n[0]"
    request = {"messages": [{"role": "user", "content": payload}]}

    rewritten, metadata = rewrite_anthropic_messages_request(request, threshold_chars=1)

    assert metadata.rewrite_count == 0
    assert rewritten["messages"][0]["content"] == payload
    assert "system" not in rewritten


class _FakeAnthropicHandler(BaseHTTPRequestHandler):
    received: dict[str, Any] | None = None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length)
        type(self).received = json.loads(body.decode("utf-8"))
        response = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def test_anthropic_proxy_forwards_rewritten_request() -> None:
    fake = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAnthropicHandler)
    fake_thread = threading.Thread(target=fake.serve_forever, daemon=True)
    fake_thread.start()
    upstream = f"http://127.0.0.1:{fake.server_address[1]}"

    proxy = create_anthropic_proxy_server(port=0, upstream=upstream, threshold_chars=20)
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}/v1/messages"

    try:
        response = httpx.post(
            proxy_url,
            json={"model": "claude-test", "messages": [{"role": "user", "content": BIG_JSON}]},
            timeout=10,
        )
    finally:
        proxy.shutdown()
        fake.shutdown()

    assert response.status_code == 200
    assert _FakeAnthropicHandler.received is not None
    received_text = _FakeAnthropicHandler.received["messages"][0]["content"]
    assert "<kompressor:" in received_text
    assert KOMPRESSOR_SYSTEM_MARKER in _FakeAnthropicHandler.received["system"]
    assert proxy.last_rewrite_metadata is not None
    assert proxy.last_rewrite_metadata["rewrite_count"] == 1
