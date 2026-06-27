"""Typed contracts for the Kompressor context gateway."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

GatewayMode = Literal["strict", "externalized", "local_decode", "lossy_allowed"]
RequestFormat = Literal["anthropic", "openai", "unknown"]
ContentSource = Literal["user_text", "tool_result", "developer_text", "system_text"]
ReversibilityClass = Literal[
    "none",
    "prompt_readable_reversible",
    "externalized_reversible",
    "local_decode_reversible",
    "lossy_analytical",
]


@dataclass(frozen=True)
class GatewayConfig:
    """Runtime configuration for request rewriting through the gateway."""

    mode: GatewayMode = "strict"
    threshold_chars: int = 512
    store_dir: str | None = None
    allow_sensitive: bool = False
    redact: bool = False
    allow_lossy: bool = False
    enable_transport_compression: bool = False
    inject_retrieval_instructions: bool = True
    inject_parsing_instructions: bool = True
    stable_instruction_anchor: Literal["end", "beginning"] = "end"
    output_shaping: bool = False
    verbosity_hint: Literal["none", "terse", "normal"] = "none"
    effort_routing: bool = False

    def __post_init__(self) -> None:
        if self.threshold_chars < 0:
            raise ValueError("threshold_chars must be non-negative")
        if self.mode == "lossy_allowed" and not self.allow_lossy:
            object.__setattr__(self, "allow_lossy", True)
        if self.mode == "local_decode" and not self.enable_transport_compression:
            object.__setattr__(self, "enable_transport_compression", True)


@dataclass(frozen=True)
class StoredOriginal:
    digest: str
    chars: int
    content_type: str
    source: ContentSource
    created_at: str
    preview: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GatewayRewrite:
    path: str
    source: ContentSource
    strategy: str
    original_chars: int
    rewritten_chars: int
    saved_chars: int
    reversibility_class: ReversibilityClass
    stored_digest: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GatewayTelemetry:
    request_format: RequestFormat
    rewrite_count: int
    rewrites: tuple[GatewayRewrite, ...]
    warnings: tuple[str, ...]
    system_prompt_added: bool
    retrieval_available: bool
    policy_rejections: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_format": self.request_format,
            "rewrite_count": self.rewrite_count,
            "rewrites": [rewrite.to_dict() for rewrite in self.rewrites],
            "warnings": list(self.warnings),
            "system_prompt_added": self.system_prompt_added,
            "retrieval_available": self.retrieval_available,
            "policy_rejections": list(self.policy_rejections),
        }
