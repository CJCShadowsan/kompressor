"""Codec interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CodecResult:
    payload: str
    reversible: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class Codec(ABC):
    name: str

    @abstractmethod
    def can_handle(self, value: object) -> bool: ...

    @abstractmethod
    def compress(self, value: object) -> CodecResult: ...

    @abstractmethod
    def decompress(self, payload: str, metadata: dict[str, Any]) -> object: ...
