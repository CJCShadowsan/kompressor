"""Harness adapter contracts for packaging optimized context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from kompressor.models import OptimizationResult


@dataclass(frozen=True)
class HarnessBundle:
    """A harness-specific prompt/request package."""

    harness: str
    content: str
    data: dict[str, Any]


class HarnessAdapter(Protocol):
    name: str

    def package(self, result: OptimizationResult, task: str = "") -> HarnessBundle: ...
