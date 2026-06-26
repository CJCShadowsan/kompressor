"""Optimization engine orchestration."""

from __future__ import annotations

import json
from typing import Any

from kompressor.codecs import (
    AtomDictCodec,
    BinaryCodec,
    BlobRefCodec,
    ChunkStoreCodec,
    CiOutputCodec,
    CodeSymbolsCodec,
    CodeTokensCodec,
    DedupeCodec,
    DomainTableCodec,
    ExtractiveTextCodec,
    GrammarCodec,
    HtmlVisibleCodec,
    JsonPathCodec,
    JsonTableCodec,
    K8sYamlCodec,
    LogSummaryCodec,
    LogTemplatesCodec,
    MarkdownOutlineCodec,
    MetaTokensCodec,
    OpenApiCodec,
    PathDictRowsCodec,
    PatternHashCodec,
    SchemaRowsCodec,
    SeparatorSegmentsCodec,
    SessionDeltaCodec,
    ShapeRowsCodec,
    SidecarRefCodec,
    TerraformPlanCodec,
    TokenLzCodec,
    ToolOutputCodec,
    TransportDeflateCodec,
    TreeDictCodec,
    XmlPathCodec,
    XmlShapeRowsCodec,
)
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
            SessionDeltaCodec(),
            BlobRefCodec(),
            SidecarRefCodec(),
            OpenApiCodec(),
            TerraformPlanCodec(),
            K8sYamlCodec(),
            CiOutputCodec(),
            ToolOutputCodec(),
            HtmlVisibleCodec(),
            MarkdownOutlineCodec(),
            CodeSymbolsCodec(),
            DomainTableCodec(),
            CodeTokensCodec(),
            DedupeCodec(),
            ChunkStoreCodec(),
            SeparatorSegmentsCodec(),
            LogSummaryCodec(),
            LogTemplatesCodec(),
            ShapeRowsCodec(),
            SchemaRowsCodec(),
            TreeDictCodec(),
            PathDictRowsCodec(),
            AtomDictCodec(),
            XmlShapeRowsCodec(),
            JsonTableCodec(self.config.delimiter_candidates),
            JsonPathCodec(),
            XmlPathCodec(),
            MetaTokensCodec(),
            TokenLzCodec(),
            GrammarCodec(),
            PatternHashCodec(),
            TransportDeflateCodec(self.config.enable_transport_compression),
            BinaryCodec(),
            ExtractiveTextCodec(),
        ]
        candidates = []
        for codec in codecs:
            if not codec.can_handle(parsed):
                continue
            try:
                result = codec.compress(parsed)
                if self.config.reversible_only and not result.reversible:
                    continue
                if result.reversible:
                    restored = codec.decompress(result.payload, result.metadata)
                    if restored != parsed:
                        continue
                stats = calculate_stats(raw, result.payload, self.config)
                if "[REDACTED_" in raw and "[REDACTED_" not in result.payload:
                    continue
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
        if "schema_rows" in marker:
            return SchemaRowsCodec().decompress(payload, metadata)
        if "shape_rows" in marker:
            return ShapeRowsCodec().decompress(payload, metadata)
        if "atom_dict" in marker:
            return AtomDictCodec().decompress(payload, metadata)
        if "xml_shape_rows" in marker:
            return XmlShapeRowsCodec().decompress(payload, metadata)
        if "transport_deflate" in marker:
            return TransportDeflateCodec(True).decompress(payload, metadata)
        if "chunk_store" in marker:
            return ChunkStoreCodec().decompress(payload, metadata)
        if "code_tokens" in marker:
            return CodeTokensCodec().decompress(payload, metadata)
        if "domain_table" in marker:
            return DomainTableCodec().decompress(payload, metadata)
        if "log_templates" in marker:
            return LogTemplatesCodec().decompress(payload, metadata)
        if "dedupe" in marker:
            return DedupeCodec().decompress(payload, metadata)
        if "separator_segments" in marker:
            return SeparatorSegmentsCodec().decompress(payload, metadata)
        if "meta_tokens" in marker:
            return MetaTokensCodec().decompress(payload, metadata)
        if "token_lz" in marker:
            return TokenLzCodec().decompress(payload, metadata)
        if "grammar" in marker:
            return GrammarCodec().decompress(payload, metadata)
        if "path_dict_rows" in marker:
            return PathDictRowsCodec().decompress(payload, metadata)
        if "tree_dict" in marker:
            return TreeDictCodec().decompress(payload, metadata)
        if "session_delta" in marker:
            return SessionDeltaCodec().decompress(payload, metadata)
        if "sidecar_ref" in marker:
            return SidecarRefCodec().decompress(payload, metadata)
        if "pattern_hash" in marker:
            return PatternHashCodec().decompress(payload, metadata)
        if "binary" in marker:
            encoding = metadata.get("encoding") if isinstance(metadata.get("encoding"), str) else None
            return BinaryCodec(encoding).decompress(payload, metadata)
        raise ValueError("unsupported metadata marker for decompression")
