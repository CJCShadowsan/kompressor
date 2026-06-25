"""Google Gemini harness adapter."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult


class GeminiHarnessAdapter:
    name = "gemini"

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle:
        user_content = result.optimized_payload if not task else f"{result.optimized_payload}\n\nUser task:\n{task}"
        data = {
            "system_instruction": {"parts": [{"text": result.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        }
        content = f"SYSTEM_INSTRUCTION:\n{result.system_prompt}\n\nCONTENT:\n{user_content}"
        return HarnessBundle(self.name, content, data)
