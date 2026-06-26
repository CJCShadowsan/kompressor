"""Minimal Anthropic-compatible HTTP proxy for Kompressor request rewriting."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from kompressor.proxy import rewrite_anthropic_messages_request

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


class KompressorAnthropicProxy(ThreadingHTTPServer):
    upstream: str
    api_key: str | None
    threshold_chars: int
    allow_sensitive: bool
    redact: bool
    last_rewrite_metadata: dict[str, Any] | None
    last_upstream_request: dict[str, Any] | None


def _filtered_headers(headers: Any) -> dict[str, str]:
    return {key: value for key, value in dict(headers).items() if key.lower() not in HOP_BY_HOP_HEADERS}


def create_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server: KompressorAnthropicProxy

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/healthz", "/health"}:
                self._send_json(200, {"status": "ok"})
                return
            self._proxy()

        def do_POST(self) -> None:  # noqa: N802
            self._proxy()

        def do_PUT(self) -> None:  # noqa: N802
            self._proxy()

        def do_PATCH(self) -> None:  # noqa: N802
            self._proxy()

        def do_DELETE(self) -> None:  # noqa: N802
            self._proxy()

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _proxy(self) -> None:
            length = int(self.headers.get("content-length", "0") or "0")
            body = self.rfile.read(length) if length else b""
            path = self.path.lstrip("/")
            url = urljoin(self.server.upstream.rstrip("/") + "/", path)
            headers = _filtered_headers(self.headers)
            if self.server.api_key:
                headers["x-api-key"] = self.server.api_key
                headers["authorization"] = f"Bearer {self.server.api_key}"

            if self.command == "POST" and urlsplit(self.path).path == "/v1/messages" and body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                    rewritten, metadata = rewrite_anthropic_messages_request(
                        payload,
                        threshold_chars=self.server.threshold_chars,
                        allow_sensitive=self.server.allow_sensitive,
                        redact=self.server.redact,
                    )
                    body = json.dumps(rewritten, ensure_ascii=False).encode("utf-8")
                    headers["content-type"] = "application/json"
                    headers["x-kompressor-rewrite-count"] = str(metadata.rewrite_count)
                    self.server.last_rewrite_metadata = metadata.to_dict()
                    self.server.last_upstream_request = rewritten
                except Exception as exc:  # pragma: no cover - exercised by CLI behavior
                    self._send_json(400, {"error": "kompressor rewrite failed", "detail": str(exc)})
                    return

            try:
                with httpx.Client(timeout=None) as client:
                    response = client.request(self.command, url, headers=headers, content=body)
            except httpx.HTTPError as exc:  # pragma: no cover - network dependent
                self._send_json(502, {"error": "upstream request failed", "detail": str(exc)})
                return

            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            self.send_header("x-kompressor-proxy", "1")
            self.end_headers()
            self.wfile.write(response.content)

    return Handler


def create_anthropic_proxy_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    upstream: str = "https://api.anthropic.com",
    api_key: str | None = None,
    threshold_chars: int = 512,
    allow_sensitive: bool = False,
    redact: bool = False,
) -> KompressorAnthropicProxy:
    server = KompressorAnthropicProxy((host, port), create_handler())
    server.upstream = upstream
    server.api_key = api_key
    server.threshold_chars = threshold_chars
    server.allow_sensitive = allow_sensitive
    server.redact = redact
    server.last_rewrite_metadata = None
    server.last_upstream_request = None
    return server


def serve_anthropic_proxy(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    upstream: str = "https://api.anthropic.com",
    api_key: str | None = None,
    threshold_chars: int = 512,
    allow_sensitive: bool = False,
    redact: bool = False,
) -> None:
    server = create_anthropic_proxy_server(
        host=host,
        port=port,
        upstream=upstream,
        api_key=api_key,
        threshold_chars=threshold_chars,
        allow_sensitive=allow_sensitive,
        redact=redact,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
