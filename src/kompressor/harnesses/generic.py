"""Generic plain-text harness adapter."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult


class GenericHarnessAdapter:
    name = "generic"

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle:
        parts = [
            "KOMPRESSOR_CONTEXT_INSTRUCTIONS:",
            result.system_prompt or "No decompression instructions are required.",
            "",
            "KOMPRESSOR_PAYLOAD:",
            result.optimized_payload,
        ]
        if task:
            parts.extend(["", "USER_TASK:", task])
        content = "\n".join(parts)
        return HarnessBundle(
            self.name,
            content,
            {"instructions": result.system_prompt, "payload": result.optimized_payload, "task": task},
        )
