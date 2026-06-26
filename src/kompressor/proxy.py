"""Anthropic-compatible request rewrite and proxy helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from kompressor.engine import KompressorEngine
from kompressor.models import OptimizationResult
from kompressor.prompts import build_system_prompt
from kompressor.security import find_secrets, redact_secrets

KOMPRESSOR_SYSTEM_MARKER = "KOMPRESSOR_PARSING_INSTRUCTIONS"
ALREADY_COMPRESSED_MARKERS = ("<kompressor:", "KOMPRESSOR_PAYLOAD", "KOMPRESSOR_PARSING_INSTRUCTIONS")


@dataclass
class RewriteRecord:
    path: str
    source: str
    strategy: str
    original_chars: int
    compressed_chars: int
    saved_chars: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RewriteMetadata:
    provider: str = "anthropic"
    rewrites: list[RewriteRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    system_prompt_added: bool = False

    @property
    def rewrite_count(self) -> int:
        return len(self.rewrites)

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "rewrite_count": self.rewrite_count,
            "rewrites": [record.to_dict() for record in self.rewrites],
            "warnings": self.warnings,
            "system_prompt_added": self.system_prompt_added,
        }


def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _is_already_compressed(text: str) -> bool:
    return any(marker in text for marker in ALREADY_COMPRESSED_MARKERS)


def _secure_text(text: str, *, allow_sensitive: bool, redact: bool) -> tuple[str, list[str]]:
    findings = find_secrets(text)
    if findings and not allow_sensitive and not redact:
        raise ValueError("suspected secrets found; use redaction or explicit override")
    if findings and redact:
        return redact_secrets(text), ["suspected secrets were redacted before compression"]
    return text, []


def _optimize_text(
    text: str,
    *,
    engine: KompressorEngine,
    threshold_chars: int,
    allow_sensitive: bool,
    redact: bool,
) -> tuple[str, OptimizationResult | None, list[str]]:
    if len(text) < threshold_chars or _is_already_compressed(text):
        return text, None, []
    safe_text, warnings = _secure_text(text, allow_sensitive=allow_sensitive, redact=redact)
    result = engine.optimize(safe_text)
    if result.kind == "none":
        return safe_text, result, warnings
    return result.optimized_payload, result, [*warnings, *result.warnings]


def _record_rewrite(path: str, source: str, original: str, optimized: str, result: OptimizationResult) -> RewriteRecord:
    return RewriteRecord(
        path=path,
        source=source,
        strategy=result.kind,
        original_chars=len(original),
        compressed_chars=len(optimized),
        saved_chars=len(original) - len(optimized),
    )


def _rewrite_text_value(
    text: str,
    *,
    path: str,
    source: str,
    engine: KompressorEngine,
    threshold_chars: int,
    allow_sensitive: bool,
    redact: bool,
    metadata: RewriteMetadata,
) -> str:
    optimized, result, warnings = _optimize_text(
        text,
        engine=engine,
        threshold_chars=threshold_chars,
        allow_sensitive=allow_sensitive,
        redact=redact,
    )
    metadata.warnings.extend(warnings)
    if result is not None and result.kind != "none" and optimized != text:
        metadata.rewrites.append(_record_rewrite(path, source, text, optimized, result))
    return optimized


def _rewrite_tool_result_content(
    content: Any,
    *,
    path: str,
    engine: KompressorEngine,
    threshold_chars: int,
    allow_sensitive: bool,
    redact: bool,
    metadata: RewriteMetadata,
) -> Any:
    if isinstance(content, str):
        return _rewrite_text_value(
            content,
            path=path,
            source="tool_result",
            engine=engine,
            threshold_chars=threshold_chars,
            allow_sensitive=allow_sensitive,
            redact=redact,
            metadata=metadata,
        )
    if isinstance(content, list):
        rewritten = []
        for idx, item in enumerate(content):
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                block = dict(item)
                block["text"] = _rewrite_text_value(
                    item["text"],
                    path=f"{path}[{idx}].text",
                    source="tool_result",
                    engine=engine,
                    threshold_chars=threshold_chars,
                    allow_sensitive=allow_sensitive,
                    redact=redact,
                    metadata=metadata,
                )
                rewritten.append(block)
            else:
                rewritten.append(item)
        return rewritten
    return content


def _rewrite_content_blocks(
    blocks: list[Any],
    *,
    message_path: str,
    engine: KompressorEngine,
    threshold_chars: int,
    allow_sensitive: bool,
    redact: bool,
    metadata: RewriteMetadata,
) -> list[Any]:
    rewritten = []
    for idx, item in enumerate(blocks):
        if not isinstance(item, dict):
            rewritten.append(item)
            continue
        block = dict(item)
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            block["text"] = _rewrite_text_value(
                block["text"],
                path=f"{message_path}.content[{idx}].text",
                source="user_text",
                engine=engine,
                threshold_chars=threshold_chars,
                allow_sensitive=allow_sensitive,
                redact=redact,
                metadata=metadata,
            )
        elif block_type == "tool_result" and "content" in block:
            block["content"] = _rewrite_tool_result_content(
                block["content"],
                path=f"{message_path}.content[{idx}].content",
                engine=engine,
                threshold_chars=threshold_chars,
                allow_sensitive=allow_sensitive,
                redact=redact,
                metadata=metadata,
            )
        rewritten.append(block)
    return rewritten


def _append_system_prompt(request: dict[str, Any], prompt: str) -> bool:
    if not prompt:
        return False
    system = request.get("system")
    if system is None:
        request["system"] = f"{KOMPRESSOR_SYSTEM_MARKER}\n{prompt}"
        return True
    if isinstance(system, str):
        if KOMPRESSOR_SYSTEM_MARKER in system or prompt in system:
            return False
        request["system"] = f"{system}\n\n{KOMPRESSOR_SYSTEM_MARKER}\n{prompt}".strip()
        return True
    if isinstance(system, list):
        serialized = json.dumps(system, ensure_ascii=False)
        if KOMPRESSOR_SYSTEM_MARKER in serialized or prompt in serialized:
            return False
        request["system"] = [*system, {"type": "text", "text": f"{KOMPRESSOR_SYSTEM_MARKER}\n{prompt}"}]
        return True
    request["system"] = f"{system}\n\n{KOMPRESSOR_SYSTEM_MARKER}\n{prompt}".strip()
    return True


def rewrite_anthropic_messages_request(
    request: dict[str, Any],
    *,
    threshold_chars: int = 512,
    allow_sensitive: bool = False,
    redact: bool = False,
) -> tuple[dict[str, Any], RewriteMetadata]:
    """Rewrite an Anthropic /v1/messages request before provider dispatch.

    Large user text and tool-result content are replaced with Kompressor's compact
    payload. Assistant tool_use blocks, images, documents, tool schemas, and
    non-text payloads are preserved.
    """

    engine = KompressorEngine()
    prepared = dict(request)
    metadata = RewriteMetadata()
    messages = []
    system_prompt: str | None = None

    for msg_idx, message in enumerate(request.get("messages", [])):
        if not isinstance(message, dict):
            messages.append(message)
            continue
        msg = dict(message)
        role = msg.get("role")
        content = msg.get("content")
        message_path = f"messages[{msg_idx}]"
        if role == "user" and isinstance(content, str):
            original = content
            optimized, result, warnings = _optimize_text(
                content,
                engine=engine,
                threshold_chars=threshold_chars,
                allow_sensitive=allow_sensitive,
                redact=redact,
            )
            metadata.warnings.extend(warnings)
            if result is not None and result.kind != "none" and optimized != original:
                msg["content"] = optimized
                system_prompt = system_prompt or result.system_prompt
                metadata.rewrites.append(
                    _record_rewrite(f"{message_path}.content", "user_text", original, optimized, result)
                )
        elif role == "user" and isinstance(content, list):
            before_count = metadata.rewrite_count
            msg["content"] = _rewrite_content_blocks(
                content,
                message_path=message_path,
                engine=engine,
                threshold_chars=threshold_chars,
                allow_sensitive=allow_sensitive,
                redact=redact,
                metadata=metadata,
            )
            if metadata.rewrite_count > before_count:
                system_prompt = system_prompt or build_system_prompt("schema_rows")
        messages.append(msg)

    if messages:
        prepared["messages"] = messages
    if metadata.rewrite_count:
        # Use the canonical prompt from any real optimization result when possible.
        if system_prompt is None:
            system_prompt = build_system_prompt("schema_rows")
        metadata.system_prompt_added = _append_system_prompt(prepared, system_prompt)
    return prepared, metadata


def prepare_messages_request(
    request: dict[str, Any],
    *,
    dry_run: bool = True,
    allow_sensitive: bool = False,
    redact: bool = False,
) -> dict[str, Any]:
    prepared, metadata = rewrite_anthropic_messages_request(
        request,
        threshold_chars=20,
        allow_sensitive=allow_sensitive,
        redact=redact,
    )
    prepared["_kompressor"] = {"dry_run": dry_run, "forwarded": False, **metadata.to_dict()}
    return prepared
