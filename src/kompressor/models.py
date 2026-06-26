"""Typed data contracts for Kompressor."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CompressionKind = Literal[
    "json_table",
    "schema_rows",
    "json_path",
    "xml_path",
    "pattern_hash",
    "meta_tokens",
    "token_lz",
    "separator_segments",
    "grammar",
    "path_dict_rows",
    "tree_dict",
    "session_delta",
    "sidecar_ref",
    "log_templates",
    "log_summary",
    "ci_output",
    "blob_ref",
    "openapi",
    "terraform_plan",
    "k8s_yaml",
    "markdown_outline",
    "html_visible",
    "code_symbols",
    "tool_output",
    "dedupe",
    "extractive",
    "binary",
    "shape_rows",
    "atom_dict",
    "xml_shape_rows",
    "transport_deflate",
    "chunk_store",
    "code_tokens",
    "domain_table",
    "none",
]


@dataclass(frozen=True)
class KompressorConfig:
    """Runtime configuration for optimization and estimation."""

    cost_per_million_input_usd: float = 3.00
    chars_per_token_proxy: float = 4.0
    minimum_chars_to_optimize: int = 0
    delimiter_candidates: tuple[str, ...] = ("|", "\t", "¦", "~")
    allow_expansion: bool = False
    enable_transport_compression: bool = False
    reversible_only: bool = False

    def __post_init__(self) -> None:
        if self.cost_per_million_input_usd < 0:
            raise ValueError("cost_per_million_input_usd must be non-negative")
        if self.chars_per_token_proxy <= 0:
            raise ValueError("chars_per_token_proxy must be positive")
        if self.minimum_chars_to_optimize < 0:
            raise ValueError("minimum_chars_to_optimize must be non-negative")
        if not self.delimiter_candidates:
            raise ValueError("at least one delimiter candidate is required")


@dataclass(frozen=True)
class TokenStats:
    baseline_chars: int
    optimized_chars: int
    baseline_tokens_estimate: int
    optimized_tokens_estimate: int
    saved_tokens_estimate: int
    percent_saved_estimate: float
    baseline_cost_estimate_usd: float
    optimized_cost_estimate_usd: float
    saved_cost_estimate_usd: float
    estimator: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptimizationResult:
    kind: CompressionKind
    optimized_payload: str
    system_prompt: str
    token_stats: TokenStats
    reversible: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["token_stats"] = self.token_stats.to_dict()
        return data
