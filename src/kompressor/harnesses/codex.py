"""Codex/OpenAI agent harness adapter."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult


class CodexHarnessAdapter:
    """Package context for Codex-style OpenAI coding-agent sessions."""

    name = "codex"

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle:
        user_content = result.optimized_payload if not task else f"{result.optimized_payload}\n\nUser task:\n{task}"
        data = {
            "instructions": result.system_prompt,
            "input": user_content,
            "messages": [
                {"role": "developer", "content": result.system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        content = f"CODEX_DEVELOPER_INSTRUCTIONS:\n{result.system_prompt}\n\nCODEX_INPUT:\n{user_content}"
        return HarnessBundle(self.name, content, data)
