"""Optional output-token shaping for gateway requests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from kompressor.gateway.models import GatewayConfig, RequestFormat
from kompressor.gateway.shapes import inject_instructions


def apply_output_shaping(
    request: dict[str, Any], request_format: RequestFormat, config: GatewayConfig
) -> tuple[dict[str, Any], bool]:
    if not config.output_shaping or config.verbosity_hint == "none":
        return request, False
    hint = "Answer concisely. Do not restate compact context unless needed. Preserve exact values when asked."
    shaped, changed = inject_instructions(request, request_format, hint, anchor=config.stable_instruction_anchor)
    if config.effort_routing:
        shaped = deepcopy(shaped)
        if "reasoning_effort" in shaped:
            shaped["reasoning_effort"] = "low"
        elif "reasoning" in shaped and isinstance(shaped["reasoning"], dict):
            shaped["reasoning"] = {**shaped["reasoning"], "effort": "low"}
    return shaped, changed
