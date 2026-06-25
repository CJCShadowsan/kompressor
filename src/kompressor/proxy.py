"""Harness request preparation helpers."""

from __future__ import annotations

from typing import Any

from kompressor.engine import KompressorEngine
from kompressor.security import find_secrets, redact_secrets


def healthz() -> dict[str, str]:
    return {"status": "ok"}


def prepare_messages_request(
    request: dict[str, Any],
    *,
    dry_run: bool = True,
    allow_sensitive: bool = False,
    redact: bool = False,
) -> dict[str, Any]:
    engine = KompressorEngine()
    prepared = dict(request)
    system_prompts: list[str] = []
    messages = []
    for message in request.get("messages", []):
        msg = dict(message)
        content = msg.get("content")
        if msg.get("role") == "user" and isinstance(content, str) and len(content) > 20:
            findings = find_secrets(content)
            if findings and not allow_sensitive and not redact:
                raise ValueError("suspected secrets found; use redaction or explicit override")
            if redact:
                content = redact_secrets(content)
            result = engine.optimize(content)
            if result.kind != "none":
                msg["content"] = result.optimized_payload
                if result.system_prompt:
                    system_prompts.append(result.system_prompt)
        messages.append(msg)
    prepared["messages"] = messages
    if system_prompts:
        existing = prepared.get("system", "")
        prepared["system"] = "\n\n".join([str(existing), *system_prompts]).strip()
    prepared["_kompressor"] = {"dry_run": dry_run, "forwarded": False}
    return prepared
