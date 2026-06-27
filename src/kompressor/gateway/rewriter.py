"""Gateway request rewriter built on KompressorEngine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kompressor.engine import KompressorEngine
from kompressor.gateway.models import GatewayConfig, GatewayRewrite, GatewayTelemetry
from kompressor.gateway.output_shaping import apply_output_shaping
from kompressor.gateway.policy import decide_gateway_use
from kompressor.gateway.shapes import (
    TextTarget,
    detect_request_format,
    inject_instructions,
    iter_text_targets,
    replace_text_target,
)
from kompressor.gateway.store import OriginalStore
from kompressor.models import KompressorConfig
from kompressor.security import find_secrets, redact_secrets

ALREADY_COMPRESSED_MARKERS = ("<kompressor:", "KOMPRESSOR_PAYLOAD", "KOMPRESSOR_PARSING_INSTRUCTIONS")

PARSING_INSTRUCTIONS = """
Some context blocks are compact Kompressor payloads. Parse them according to their marker.
For <kompressor:schema_rows_v1>, the JSON header defines variable columns, constant columns,
enum dictionaries, and transforms. Each line after @rows is one record. Count those row lines for
the total. Map row cells positionally to header.columns, add header.constants to every record,
map enum integer cells through header.enums, and expand int_sequence transforms from start/step
when cells are null placeholders. If a block contains kompressor://sha256/<digest> and you need
exact original text, use the configured Kompressor retrieval tool or endpoint. Do not invent
externalized content that was not retrieved.
"""


def _is_already_compressed(text: str) -> bool:
    return any(marker in text for marker in ALREADY_COMPRESSED_MARKERS)


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


class GatewayRewriter:
    def __init__(self, config: GatewayConfig | None = None, store: OriginalStore | None = None) -> None:
        self.config = config or GatewayConfig()
        store_root = Path(self.config.store_dir).expanduser() if self.config.store_dir else None
        self.store = store or OriginalStore(store_root)
        engine_config = KompressorConfig(
            minimum_chars_to_optimize=0,
            reversible_only=not self.config.allow_lossy,
            enable_transport_compression=self.config.enable_transport_compression,
        )
        self.engine = KompressorEngine(engine_config)

    def _secure(self, text: str) -> tuple[str, list[str]]:
        findings = find_secrets(text)
        if findings and not self.config.allow_sensitive and not self.config.redact:
            raise ValueError("suspected secrets found; use redaction or explicit override")
        if findings and self.config.redact:
            return redact_secrets(text), ["suspected secrets were redacted before compression"]
        return text, []

    def _target_rewrite(self, target: TextTarget) -> tuple[str | None, GatewayRewrite | None, str | None, list[str]]:
        text = target.text
        if len(text) < self.config.threshold_chars or _is_already_compressed(text):
            return None, None, None, []
        safe_text, warnings = self._secure(text)
        stored = self.store.put_text(
            safe_text,
            source=target.source,
            content_type="text/plain",
            metadata={"path": target.path},
        )
        target_value: object = safe_text
        embedded = _find_embedded_json(safe_text)
        if embedded is not None:
            target_value, _task = embedded
        result = self.engine.optimize(target_value)
        decision = decide_gateway_use(
            result,
            self.config,
            retrieval_available=True,
            local_decode_available=self.config.mode == "local_decode",
        )
        if not decision.allowed:
            return None, None, decision.reason, warnings
        optimized = result.optimized_payload
        if result.kind in {"sidecar_ref", "blob_ref"}:
            optimized = f"<kompressor:external_ref_v1>\nuri=kompressor://sha256/{stored.digest}\nchars={stored.chars}"
        if len(optimized) >= len(safe_text):
            return None, None, "no_positive_savings", warnings
        rewrite = GatewayRewrite(
            path=target.path,
            source=target.source,
            strategy=str(result.kind),
            original_chars=len(text),
            rewritten_chars=len(optimized),
            saved_chars=len(text) - len(optimized),
            reversibility_class=decision.reversibility_class,
            stored_digest=stored.digest,
            warnings=tuple([*warnings, *result.warnings]),
        )
        return optimized, rewrite, None, list(rewrite.warnings)

    def rewrite_request(self, request: dict[str, Any]) -> tuple[dict[str, Any], GatewayTelemetry]:
        request_format = detect_request_format(request)
        rewritten_request = request
        rewrites: list[GatewayRewrite] = []
        warnings: list[str] = []
        rejections: list[str] = []
        for target in list(iter_text_targets(rewritten_request, request_format)):
            optimized, rewrite, rejection, target_warnings = self._target_rewrite(target)
            warnings.extend(target_warnings)
            if rejection:
                rejections.append(rejection)
            if optimized is not None and rewrite is not None:
                rewritten_request = replace_text_target(rewritten_request, target, optimized)
                rewrites.append(rewrite)
        system_prompt_added = False
        if rewrites and self.config.inject_parsing_instructions:
            rewritten_request, system_prompt_added = inject_instructions(
                rewritten_request,
                request_format,
                PARSING_INSTRUCTIONS,
                anchor=self.config.stable_instruction_anchor,
            )
        rewritten_request, shaped = apply_output_shaping(rewritten_request, request_format, self.config)
        system_prompt_added = system_prompt_added or shaped
        telemetry = GatewayTelemetry(
            request_format=request_format,
            rewrite_count=len(rewrites),
            rewrites=tuple(rewrites),
            warnings=tuple(dict.fromkeys(warnings)),
            system_prompt_added=system_prompt_added,
            retrieval_available=True,
            policy_rejections=tuple(rejections),
        )
        return rewritten_request, telemetry
