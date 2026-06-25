"""OpenAI chat/responses harness adapter."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult


class OpenAIHarnessAdapter:
    name = "openai"

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle:
        user_content = result.optimized_payload if not task else f"{result.optimized_payload}\n\nUser task:\n{task}"
        data = {
            "messages": [
                {"role": "developer", "content": result.system_prompt},
                {"role": "user", "content": user_content},
            ]
        }
        content = f"DEVELOPER:\n{result.system_prompt}\n\nUSER:\n{user_content}"
        return HarnessBundle(self.name, content, data)
