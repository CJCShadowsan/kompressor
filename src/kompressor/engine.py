"""Optimization engine orchestration."""

from __future__ import annotations

import json
from typing import Any

from kompressor.codecs import BinaryCodec, JsonPathCodec, JsonTableCodec, PatternHashCodec, XmlPathCodec
from kompressor.estimation import calculate_stats
from kompressor.models import KompressorConfig, OptimizationResult
from kompressor.prompts import build_system_prompt


class KompressorEngine:
    def __init__(self, config: KompressorConfig | None = None) -> None:
        self.config = config or KompressorConfig()

    def _baseline(self, value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _parse(self, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith(("[", "{")):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
        return value

    def optimize(self, value: object) -> OptimizationResult:
        parsed = self._parse(value)
        raw = self._baseline(parsed)
        if len(raw) < self.config.minimum_chars_to_optimize:
            stats = calculate_stats(raw, raw, self.config)
            return OptimizationResult("none", raw, "", stats, True, {}, ["payload below optimization threshold"])
        codecs = [
            JsonTableCodec(self.config.delimiter_candidates),
            JsonPathCodec(),
            XmlPathCodec(),
            PatternHashCodec(),
            BinaryCodec(),
        ]
        candidates = []
        for codec in codecs:
            if not codec.can_handle(parsed):
                continue
            try:
                result = codec.compress(parsed)
                if result.reversible:
                    restored = codec.decompress(result.payload, result.metadata)
                    if restored != parsed:
                        continue
                stats = calculate_stats(raw, result.payload, self.config)
                candidates.append((codec.name, result, stats))
            except Exception:
                continue
        if not candidates:
            stats = calculate_stats(raw, raw, self.config)
            return OptimizationResult("none", raw, "", stats, True, {}, ["no safe optimization strategy found"])
        candidates.sort(key=lambda item: item[2].optimized_tokens_estimate)
        kind, codec_result, stats = candidates[0]
        warnings = list(codec_result.warnings)
        if stats.saved_tokens_estimate < 0 and not self.config.allow_expansion:
            original_stats = calculate_stats(raw, raw, self.config)
            return OptimizationResult("none", raw, "", original_stats, True, {}, ["best codec expanded payload"])
        prompt = build_system_prompt(kind, codec_result.metadata)
        return OptimizationResult(
            kind,
            codec_result.payload,
            prompt,
            stats,
            codec_result.reversible,
            codec_result.metadata,
            warnings,
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        marker = str(metadata.get("marker", ""))
        if "json_table" in marker:
            return JsonTableCodec().decompress(payload, metadata)
        if "pattern_hash" in marker:
            return PatternHashCodec().decompress(payload, metadata)
        if "binary" in marker:
            encoding = metadata.get("encoding") if isinstance(metadata.get("encoding"), str) else None
            return BinaryCodec(encoding).decompress(payload, metadata)
        raise ValueError("unsupported metadata marker for decompression")
