"""Host-facing hook entrypoints for Kompressor."""

from __future__ import annotations

from typing import Any

from kompressor.gateway.models import GatewayConfig
from kompressor.gateway.rewriter import GatewayRewriter

REQUEST_REWRITE_HOOK = "kompressor.request_rewrite"
REQUEST_REWRITE_HOOK_VERSION = 1


def extract_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the model request from a raw request or hook envelope."""
    for key in ("request", "body"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def request_rewrite_hook(payload: dict[str, Any], config: GatewayConfig | None = None) -> dict[str, Any]:
    """Rewrite a model request and return a stable hook envelope.

    Hosts may pass either the raw OpenAI/Anthropic-style request object or an
    envelope containing the request under ``request`` or ``body``.
    """
    request = extract_request(payload)
    rewritten, telemetry = GatewayRewriter(config).rewrite_request(request)
    return {
        "hook": {
            "name": REQUEST_REWRITE_HOOK,
            "version": REQUEST_REWRITE_HOOK_VERSION,
        },
        "decision": "rewrite" if telemetry.rewrite_count else "continue",
        "request": rewritten,
        "telemetry": telemetry.to_dict(),
    }
