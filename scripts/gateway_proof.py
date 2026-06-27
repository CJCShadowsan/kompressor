#!/usr/bin/env python3
"""Offline proof that raw requests entering Kompressor Gateway are rewritten upstream."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompressor.gateway.http import create_gateway_server  # noqa: E402
from kompressor.gateway.models import GatewayConfig  # noqa: E402


def rows() -> str:
    return json.dumps(
        [
            {"id": i, "event": "auth_timeout_error", "severity": ["CRITICAL", "WARNING", "INFO"][i % 3]}
            for i in range(60)
        ]
    )


class FakeUpstream(BaseHTTPRequestHandler):
    seen: dict = {}

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        type(self).seen = json.loads(body.decode("utf-8"))
        payload = json.dumps(
            {
                "id": "proof",
                "choices": [
                    {"message": {"role": "assistant", "content": "Total: 60 CRITICAL: 20 WARNING: 20 INFO: 20"}}
                ],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run(out: Path) -> dict:
    raw = rows()
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    store_dir = out.parent / "store"
    gateway = create_gateway_server(
        host="127.0.0.1",
        port=0,
        upstream=f"http://127.0.0.1:{upstream.server_address[1]}",
        config=GatewayConfig(store_dir=str(store_dir), threshold_chars=0),
    )
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{gateway.server_address[1]}"
        response = httpx.post(
            f"{base}/v1/chat/completions", json={"messages": [{"role": "user", "content": raw}]}, timeout=30
        )
        telemetry = gateway.last_telemetry or {}
        digest = telemetry.get("rewrites", [{}])[0].get("stored_digest")
        retrieved = httpx.get(f"{base}/v1/kompressor/retrieve/{digest}", timeout=30).json() if digest else {}
        proof = {
            "gateway_rewrite_proof": response.status_code == 200 and telemetry.get("rewrite_count") == 1,
            "raw_input_sent_to_gateway": True,
            "upstream_received_rewritten": FakeUpstream.seen.get("messages", [{}])[0].get("content") != raw,
            "rewrite_count": telemetry.get("rewrite_count", 0),
            "strategy": telemetry.get("rewrites", [{}])[0].get("strategy"),
            "retrieval_round_trip": retrieved.get("content") == raw,
            "semantic_model_check": "offline_fake_upstream_pass",
            "claims_supported": [
                "raw request enters gateway",
                "upstream receives rewritten request",
                "stored original is retrievable by digest",
            ],
            "claims_not_supported": ["provider billing savings", "live hosted model semantic quality"],
            "telemetry": telemetry,
        }
    finally:
        gateway.shutdown()
        gateway.server_close()
        upstream.shutdown()
        upstream.server_close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/proof/gateway-offline.json"))
    args = parser.parse_args()
    proof = run(args.out)
    print(json.dumps(proof, indent=2, sort_keys=True))
    raise SystemExit(0 if proof["gateway_rewrite_proof"] and proof["retrieval_round_trip"] else 2)


if __name__ == "__main__":
    main()
