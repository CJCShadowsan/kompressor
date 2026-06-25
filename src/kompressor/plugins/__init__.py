"""Plugin registry for transparent Kompressor harness integrations."""

from __future__ import annotations

from typing import Any

from kompressor.plugins.base import BaseKompressorPlugin, KompressorPlugin, PluginManifest, PluginResult
from kompressor.plugins.builtin import (
    ClaudeKompressorPlugin,
    CodexKompressorPlugin,
    GeminiKompressorPlugin,
    GenericKompressorPlugin,
    HermesKompressorPlugin,
    OpenAIKompressorPlugin,
)

_PLUGIN_CLASSES: dict[str, type[BaseKompressorPlugin]] = {
    "generic": GenericKompressorPlugin,
    "claude": ClaudeKompressorPlugin,
    "anthropic": ClaudeKompressorPlugin,
    "openai": OpenAIKompressorPlugin,
    "gemini": GeminiKompressorPlugin,
    "hermes": HermesKompressorPlugin,
    "codex": CodexKompressorPlugin,
}


def available_plugins() -> tuple[str, ...]:
    """Return canonical plugin names."""

    return tuple(name for name in _PLUGIN_CLASSES if name != "anthropic")


def get_plugin(name: str, **kwargs: Any) -> BaseKompressorPlugin:
    """Instantiate a built-in plugin by harness or alias."""

    key = name.lower()
    try:
        plugin_class = _PLUGIN_CLASSES[key]
    except KeyError as exc:
        choices = ", ".join(sorted(_PLUGIN_CLASSES))
        raise ValueError(f"unknown plugin {name!r}; choose one of: {choices}") from exc
    return plugin_class(**kwargs)


def plugin_manifests() -> dict[str, PluginManifest]:
    """Return manifests for canonical built-in plugins."""

    return {name: get_plugin(name).manifest for name in available_plugins()}


__all__ = [
    "BaseKompressorPlugin",
    "ClaudeKompressorPlugin",
    "CodexKompressorPlugin",
    "GeminiKompressorPlugin",
    "GenericKompressorPlugin",
    "HermesKompressorPlugin",
    "KompressorPlugin",
    "OpenAIKompressorPlugin",
    "PluginManifest",
    "PluginResult",
    "available_plugins",
    "get_plugin",
    "plugin_manifests",
]
