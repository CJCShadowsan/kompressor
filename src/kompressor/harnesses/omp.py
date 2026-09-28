"""OMP (agent runtime) harness adapter."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult


class OMPHarnessAdapter:
    """Packages optimized context for omp agent runtimes."""

    name = "omp"

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle:
        instruction = result.system_prompt or "Use the payload directly."
        parts = [
            "KOMPRESSOR_INSTRUCTIONS:",
            instruction,
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
            {"instructions": instruction, "payload": result.optimized_payload, "task": task},
        )

    def prepare_user_input(self, content: str, *, task: str = "") -> str:
        """Hook: compress user input before model dispatch."""
        return content

    def prepare_tool_output(self, content: str, *, tool_name: str = "") -> str:
        """Hook: compress tool output before model dispatch."""
        return content

    def prepare_request(self, request: dict) -> dict:
        """Hook: rewrite request before provider dispatch."""
        return request