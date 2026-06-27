"""HTTP server for the Kompressor context gateway."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from kompressor.gateway.models import GatewayConfig
from kompressor.gateway.rewriter import GatewayRewriter
from kompressor.gateway.stats import GatewayStats
from kompressor.gateway.store import OriginalStore

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


class KompressorGatewayServer(ThreadingHTTPServer):
    upstream: str
    api_key: str | None
    config: GatewayConfig
    store: OriginalStore
    stats: GatewayStats
    last_telemetry: dict[str, Any] | None
    last_upstream_request: dict[str, Any] | None


def _filtered_headers(headers: Any) -> dict[str, str]:
    return {key: value for key, value in dict(headers).items() if key.lower() not in HOP_BY_HOP_HEADERS}


def create_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server: KompressorGatewayServer

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path in {"/healthz", "/health"}:
                self._send_json(200, {"status": "ok"})
                return
            if path == "/v1/kompressor/stats":
                self._send_json(200, self.server.stats.load())
                return
            if path.startswith("/v1/kompressor/retrieve/"):
                digest = path.rsplit("/", 1)[-1]
                try:
                    self._send_json(
                        200,
                        {
                            "digest": digest,
                            "content": self.server.store.get_text(digest),
                            "metadata": self.server.store.get_metadata(digest).to_dict(),
                        },
                    )
                except KeyError as exc:
                    self._send_json(404, {"error": str(exc)})
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
                headers["authorization"] = f"Bearer {self.server.api_key}"
                headers["x-api-key"] = self.server.api_key
            route = urlsplit(self.path).path
            if self.command == "POST" and route in {"/v1/messages", "/v1/chat/completions", "/v1/responses"} and body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                    rewriter = GatewayRewriter(self.server.config, self.server.store)
                    rewritten, telemetry = rewriter.rewrite_request(payload)
                    self.server.stats.record(telemetry)
                    self.server.last_telemetry = telemetry.to_dict()
                    self.server.last_upstream_request = rewritten
                    body = json.dumps(rewritten, ensure_ascii=False).encode("utf-8")
                    headers["content-type"] = "application/json"
                    headers["x-kompressor-rewrite-count"] = str(telemetry.rewrite_count)
                except Exception as exc:
                    self._send_json(400, {"error": "kompressor gateway rewrite failed", "detail": str(exc)})
                    return
            try:
                with httpx.Client(timeout=None) as client:
                    response = client.request(self.command, url, headers=headers, content=body)
            except httpx.HTTPError as exc:
                self._send_json(502, {"error": "upstream request failed", "detail": str(exc)})
                return
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            self.send_header("x-kompressor-gateway", "1")
            if self.server.last_telemetry:
                self.send_header("x-kompressor-rewrite-count", str(self.server.last_telemetry.get("rewrite_count", 0)))
            self.end_headers()
            self.wfile.write(response.content)

    return Handler


def create_gateway_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    upstream: str = "https://api.openai.com",
    api_key: str | None = None,
    config: GatewayConfig | None = None,
) -> KompressorGatewayServer:
    server = KompressorGatewayServer((host, port), create_handler())
    server.upstream = upstream
    server.api_key = api_key
    server.config = config or GatewayConfig()
    server.store = OriginalStore(server.config.store_dir)
    server.stats = GatewayStats(server.store.root / "stats.json")
    server.last_telemetry = None
    server.last_upstream_request = None
    return server


def serve_gateway(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    upstream: str = "https://api.openai.com",
    api_key: str | None = None,
    config: GatewayConfig | None = None,
) -> None:
    server = create_gateway_server(host=host, port=port, upstream=upstream, api_key=api_key, config=config)
    try:
        server.serve_forever()
    finally:
        server.server_close()
