"""Plugin contracts for transparent harness integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from kompressor.engine import KompressorEngine
from kompressor.harnesses import get_harness_adapter
from kompressor.harnesses.base import HarnessBundle
from kompressor.models import OptimizationResult
from kompressor.security import find_secrets, redact_secrets


@dataclass(frozen=True)
class PluginManifest:
    """User-facing capabilities for a Kompressor harness plugin."""

    name: str
    harness: str
    entrypoint: str
    mode: str
    hooks: tuple[str, ...]
    transparent: bool
    install_hint: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginResult:
    """Result returned by a plugin preflight hook."""

    changed: bool
    content: str
    result: OptimizationResult | None
    bundle: HarnessBundle | None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class KompressorPlugin(Protocol):
    manifest: PluginManifest

    def prepare_user_input(self, content: str, *, task: str = "") -> PluginResult: ...

    def prepare_tool_output(self, content: str, *, tool_name: str = "") -> PluginResult: ...

    def prepare_request(self, request: dict[str, Any]) -> dict[str, Any]: ...


class BaseKompressorPlugin:
    """Reusable implementation for pre-send and request-rewrite hooks."""

    manifest: PluginManifest

    def __init__(self, *, threshold_chars: int = 512, allow_sensitive: bool = False, redact: bool = False) -> None:
        self.threshold_chars = threshold_chars
        self.allow_sensitive = allow_sensitive
        self.redact = redact
        self.engine = KompressorEngine()

    @property
    def harness(self) -> str:
        return self.manifest.harness

    def _secure_content(self, content: str) -> tuple[str, list[str]]:
        findings = find_secrets(content)
        if findings and not self.allow_sensitive and not self.redact:
            raise ValueError("suspected secrets found; use redaction or explicit override")
        if findings and self.redact:
            return redact_secrets(content), ["suspected secrets were redacted before compression"]
        return content, []

    def _prepare(self, content: str, *, task: str = "", source: str) -> PluginResult:
        if len(content) < self.threshold_chars:
            return PluginResult(False, content, None, None, metadata={"source": source, "reason": "below_threshold"})
        safe_content, warnings = self._secure_content(content)
        result = self.engine.optimize(safe_content)
        if result.kind == "none":
            return PluginResult(
                False,
                safe_content,
                result,
                None,
                tuple(warnings),
                {"source": source, "reason": "no_codec"},
            )
        bundle = get_harness_adapter(self.harness).package(result, task)
        return PluginResult(
            True,
            bundle.content,
            result,
            bundle,
            tuple([*warnings, *result.warnings]),
            {"source": source, "strategy": result.kind, "harness": self.harness},
        )

    def prepare_user_input(self, content: str, *, task: str = "") -> PluginResult:
        return self._prepare(content, task=task, source="user_input")

    def prepare_tool_output(self, content: str, *, tool_name: str = "") -> PluginResult:
        task = (
            f"Interpret compressed output from tool {tool_name!r}."
            if tool_name
            else "Interpret compressed tool output."
        )
        return self._prepare(content, task=task, source="tool_output")

    def prepare_request(self, request: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(request)
        messages = []
        plugin_metadata: list[dict[str, Any]] = []
        for message in request.get("messages", []):
            msg = dict(message)
            content = msg.get("content")
            if msg.get("role") in {"user", "tool"} and isinstance(content, str):
                transformed = (
                    self.prepare_user_input(content) if msg.get("role") == "user" else self.prepare_tool_output(content)
                )
                if transformed.changed:
                    msg["content"] = transformed.content
                    plugin_metadata.append(transformed.metadata)
            messages.append(msg)
        if messages:
            prepared["messages"] = messages
        prepared["_kompressor_plugin"] = {
            "name": self.manifest.name,
            "harness": self.harness,
            "rewrites": plugin_metadata,
        }
        return prepared
