"""Hermes Agent harness adapter."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult


class HermesHarnessAdapter:
    name = "hermes"

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle:
        instruction = result.system_prompt or "Use the payload directly."
        content = "\n".join(
            [
                "Hermes: treat the following Kompressor instructions as task-local parsing rules.",
                "Do not save them as durable memory unless explicitly asked.",
                "",
                "KOMPRESSOR_INSTRUCTIONS:",
                instruction,
                "",
                "KOMPRESSOR_PAYLOAD:",
                result.optimized_payload,
            ]
        )
        if task:
            content += f"\n\nUSER_TASK:\n{task}"
        data = {
            "hermes_prompt": content,
            "suggested_invocation": 'hermes chat -q "$(cat kompressor-context.txt)"',
            "instructions": instruction,
            "payload": result.optimized_payload,
            "task": task,
        }
        return HarnessBundle(self.name, content, data)
