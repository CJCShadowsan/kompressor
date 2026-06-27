"""Hermes-native Kompressor request middleware.

Installed by `kompressor hermes install`. The plugin rewrites large structured
user messages in Hermes's `llm_request` middleware hook before provider dispatch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_CONFIG = Path(__file__).with_name("config.json")
if _CONFIG.exists():
    try:
        _config = json.loads(_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        _config = {}
    for _entry in _config.get("python_paths", []):
        if _entry and Path(_entry).exists() and _entry not in sys.path:
            sys.path.insert(0, _entry)
else:
    _config = {}


def _threshold() -> int:
    try:
        return int(os.environ.get("KOMPRESSOR_HERMES_THRESHOLD_CHARS", "512"))
    except ValueError:
        return 512


def _find_embedded_json(text: str) -> tuple[object, str] | None:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        task = (text[:idx] + text[idx + end :]).strip()
        return value, task
    return None


def _write_proof(event: dict[str, Any]) -> None:
    proof_path = os.environ.get("KOMPRESSOR_HERMES_PROOF_LOG", "").strip()
    if not proof_path:
        return
    path = Path(proof_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _compress_with_import(content: str) -> tuple[str, dict[str, Any]] | None:
    from kompressor.engine import KompressorEngine
    from kompressor.harnesses import get_harness_adapter
    from kompressor.security import find_secrets, redact_secrets

    allow_sensitive = os.environ.get("KOMPRESSOR_HERMES_ALLOW_SENSITIVE", "").lower() in {"1", "true", "yes", "on"}
    redact = os.environ.get("KOMPRESSOR_HERMES_REDACT", "1").lower() not in {"0", "false", "no", "off"}
    safe_content = content
    findings = find_secrets(content)
    if findings and not allow_sensitive and not redact:
        return None
    if findings and redact:
        safe_content = redact_secrets(content)

    target: object = safe_content
    task = ""
    embedded = _find_embedded_json(safe_content)
    if embedded is not None:
        target, task = embedded

    result = KompressorEngine().optimize(target)
    if result.kind == "none":
        return None

    bundle = get_harness_adapter("hermes").package(result, task=task)
    metadata = {
        "strategy": result.kind,
        "original_chars": len(content),
        "compressed_chars": len(bundle.content),
        "saved_chars": len(content) - len(bundle.content),
        "task_chars": len(task),
        "redacted": bool(findings and redact),
    }
    return bundle.content, metadata


def _compress_with_cli(content: str) -> tuple[str, dict[str, Any]] | None:
    cli = _config.get("kompressor_cli") or "kompressor"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        proc = subprocess.run(
            [cli, "plugin", "preflight", "hermes", str(temp_path), "--json"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    finally:
        temp_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not payload.get("changed"):
        return None
    compressed = payload.get("content")
    if not isinstance(compressed, str):
        return None
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata = {
        "strategy": metadata.get("strategy", "unknown"),
        "original_chars": len(content),
        "compressed_chars": len(compressed),
        "saved_chars": len(content) - len(compressed),
        "task_chars": 0,
        "redacted": False,
    }
    return compressed, metadata


def _compress_content(content: str) -> tuple[str, dict[str, Any]] | None:
    if len(content) < _threshold():
        return None
    try:
        return _compress_with_import(content)
    except Exception:
        if os.environ.get("KOMPRESSOR_HERMES_DISABLE_CLI_FALLBACK", "").lower() in {"1", "true", "yes", "on"}:
            return None
        return _compress_with_cli(content)


def _rewrite_messages(messages: list[Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    rewritten: list[Any] = []
    events: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            rewritten.append(message)
            continue
        msg = dict(message)
        role = msg.get("role")
        content = msg.get("content")
        if role == "user" and isinstance(content, str):
            compressed = _compress_content(content)
            if compressed is not None:
                new_content, metadata = compressed
                msg["content"] = new_content
                event = {"message_index": index, "role": role, **metadata}
                events.append(event)
                _write_proof(event)
        rewritten.append(msg)
    return rewritten, events


def on_llm_request_middleware(*, request: dict[str, Any], **_: Any) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return None
    try:
        from kompressor.gateway.models import GatewayConfig
        from kompressor.gateway.rewriter import GatewayRewriter

        config = GatewayConfig(threshold_chars=_threshold(), redact=True)
        next_request, telemetry = GatewayRewriter(config).rewrite_request(request)
        if telemetry.rewrite_count:
            for rewrite in telemetry.rewrites:
                _write_proof(
                    {
                        "message_index": -1,
                        "role": rewrite.source,
                        "strategy": rewrite.strategy,
                        "original_chars": rewrite.original_chars,
                        "compressed_chars": rewrite.rewritten_chars,
                        "saved_chars": rewrite.saved_chars,
                        "reversibility_class": rewrite.reversibility_class,
                        "stored_digest": rewrite.stored_digest,
                        "gateway": True,
                    }
                )
            return {
                "request": next_request,
                "name": "kompressor-hermes",
                "source": "kompressor-gateway",
                "reason": "gateway_context_rewritten",
            }
    except Exception:
        if os.environ.get("KOMPRESSOR_HERMES_DISABLE_LEGACY_FALLBACK", "").lower() in {"1", "true", "yes", "on"}:
            return None
    next_request = dict(request)
    messages = next_request.get("messages")
    if isinstance(messages, list):
        rewritten, events = _rewrite_messages(messages)
        if events:
            next_request["messages"] = rewritten
            return {
                "request": next_request,
                "name": "kompressor-hermes",
                "source": "kompressor",
                "reason": "structured_context_compressed",
            }
    responses_input = next_request.get("input")
    if isinstance(responses_input, list):
        rewritten, events = _rewrite_messages(responses_input)
        if events:
            next_request["input"] = rewritten
            return {
                "request": next_request,
                "name": "kompressor-hermes",
                "source": "kompressor",
                "reason": "structured_context_compressed",
            }
    return None


def register(ctx) -> None:
    ctx.register_middleware("llm_request", on_llm_request_middleware)
