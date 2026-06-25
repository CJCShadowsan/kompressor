"""Anthropic Claude harness adapter."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult


class ClaudeHarnessAdapter:
    name = "claude"

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle:
        user_content = result.optimized_payload if not task else f"{result.optimized_payload}\n\nUser task:\n{task}"
        data = {
            "system": result.system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }
        content = f"SYSTEM:\n{result.system_prompt}\n\nPAYLOAD:\n{result.optimized_payload}"
        if task:
            content += f"\n\nUSER TASK:\n{task}"
        return HarnessBundle(self.name, content, data)
