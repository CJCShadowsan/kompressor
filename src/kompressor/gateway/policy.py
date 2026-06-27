"""Gateway policy gates for safe codec use."""

from __future__ import annotations

from dataclasses import dataclass

from kompressor.gateway.models import GatewayConfig, ReversibilityClass
from kompressor.models import OptimizationResult

EXTERNALIZED_KINDS = {"sidecar_ref", "session_delta", "blob_ref"}
LOCAL_DECODE_KINDS = {"transport_deflate"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    reversibility_class: ReversibilityClass


def classify_result(result: OptimizationResult) -> ReversibilityClass:
    kind = str(result.kind)
    if kind == "none":
        return "none"
    explicit = getattr(result, "reversibility_class", None)
    if explicit in {
        "none",
        "prompt_readable_reversible",
        "externalized_reversible",
        "local_decode_reversible",
        "lossy_analytical",
    }:
        return explicit  # type: ignore[return-value]
    if kind in LOCAL_DECODE_KINDS:
        return "local_decode_reversible"
    if kind in EXTERNALIZED_KINDS:
        return "externalized_reversible"
    if result.reversible:
        return "prompt_readable_reversible"
    return "lossy_analytical"


def decide_gateway_use(
    result: OptimizationResult,
    config: GatewayConfig,
    *,
    retrieval_available: bool,
    local_decode_available: bool,
) -> PolicyDecision:
    cls = classify_result(result)
    if result.kind == "none" or cls == "none":
        return PolicyDecision(False, "no_optimization", cls)
    if cls == "prompt_readable_reversible":
        return PolicyDecision(True, "prompt_readable_reversible_allowed", cls)
    if cls == "externalized_reversible":
        if config.mode in {"externalized", "local_decode", "lossy_allowed"} and retrieval_available:
            return PolicyDecision(True, "externalized_reversible_allowed", cls)
        return PolicyDecision(False, "externalized_requires_retrieval", cls)
    if cls == "local_decode_reversible":
        if config.mode == "local_decode" and local_decode_available:
            return PolicyDecision(True, "local_decode_available", cls)
        return PolicyDecision(False, "local_decode_not_available", cls)
    if cls == "lossy_analytical":
        if config.allow_lossy or config.mode == "lossy_allowed":
            return PolicyDecision(True, "lossy_explicitly_allowed", cls)
        return PolicyDecision(False, "lossy_not_allowed", cls)
    return PolicyDecision(False, "unsupported_policy_class", cls)
