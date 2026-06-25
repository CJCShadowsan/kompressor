"""Harness adapters for LLM runtimes and agent frameworks."""

from __future__ import annotations

from kompressor.harnesses.base import HarnessAdapter, HarnessBundle
from kompressor.harnesses.claude import ClaudeHarnessAdapter
from kompressor.harnesses.codex import CodexHarnessAdapter
from kompressor.harnesses.gemini import GeminiHarnessAdapter
from kompressor.harnesses.generic import GenericHarnessAdapter
from kompressor.harnesses.hermes import HermesHarnessAdapter
from kompressor.harnesses.openai import OpenAIHarnessAdapter

_ADAPTERS = {
    "generic": GenericHarnessAdapter,
    "claude": ClaudeHarnessAdapter,
    "anthropic": ClaudeHarnessAdapter,
    "codex": CodexHarnessAdapter,
    "openai": OpenAIHarnessAdapter,
    "gemini": GeminiHarnessAdapter,
    "hermes": HermesHarnessAdapter,
}


def get_harness_adapter(name: str) -> HarnessAdapter:
    key = name.lower()
    try:
        return _ADAPTERS[key]()
    except KeyError as exc:
        choices = ", ".join(sorted(_ADAPTERS))
        raise ValueError(f"unknown harness {name!r}; choose one of: {choices}") from exc


__all__ = [
    "ClaudeHarnessAdapter",
    "CodexHarnessAdapter",
    "GeminiHarnessAdapter",
    "GenericHarnessAdapter",
    "HarnessAdapter",
    "HarnessBundle",
    "HermesHarnessAdapter",
    "OpenAIHarnessAdapter",
    "get_harness_adapter",
]
