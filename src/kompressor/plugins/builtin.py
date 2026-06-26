"""Built-in Kompressor plugins for supported harnesses."""

from __future__ import annotations

from kompressor.plugins.base import BaseKompressorPlugin, PluginManifest


class GenericKompressorPlugin(BaseKompressorPlugin):
    manifest = PluginManifest(
        name="kompressor-generic",
        harness="generic",
        entrypoint="kompressor.plugins.builtin:GenericKompressorPlugin",
        mode="portable-pre-send",
        hooks=("pre_user_input", "pre_tool_output", "request_rewrite"),
        transparent=False,
        install_hint=(
            "Use through `kompressor plugin show generic` or call the Python plugin entrypoint from any harness hook."
        ),
        notes=("Generic plugin emits plain text instructions and payload for harnesses without native APIs.",),
    )


class ClaudeKompressorPlugin(BaseKompressorPlugin):
    manifest = PluginManifest(
        name="kompressor-claude",
        harness="claude",
        entrypoint="kompressor.plugins.builtin:ClaudeKompressorPlugin",
        mode="anthropic-compatible-request-rewrite",
        hooks=("pre_user_input", "pre_tool_output", "messages_request"),
        transparent=True,
        install_hint=(
            "Use `kompressor claude-code install` for Claude Code / claudish shims, "
            "or install as Anthropic request middleware where available."
        ),
        notes=(
            "Injects decompression instructions into the system/developer side of the request "
            "when the host exposes it.",
        ),
    )


class OpenAIKompressorPlugin(BaseKompressorPlugin):
    manifest = PluginManifest(
        name="kompressor-openai",
        harness="openai",
        entrypoint="kompressor.plugins.builtin:OpenAIKompressorPlugin",
        mode="openai-compatible-request-rewrite",
        hooks=("pre_user_input", "pre_tool_output", "chat_or_responses_request"),
        transparent=True,
        install_hint=(
            "Install as OpenAI-compatible middleware or configure a base_url proxy when the client supports it."
        ),
        notes=("Packages instructions as developer-message content for OpenAI-style harnesses.",),
    )


class GeminiKompressorPlugin(BaseKompressorPlugin):
    manifest = PluginManifest(
        name="kompressor-gemini",
        harness="gemini",
        entrypoint="kompressor.plugins.builtin:GeminiKompressorPlugin",
        mode="gemini-request-rewrite",
        hooks=("pre_user_input", "pre_tool_output", "generate_content_request"),
        transparent=True,
        install_hint="Install as Gemini client middleware where request hooks are available.",
        notes=("Packages instructions into Gemini system_instruction and contents shapes.",),
    )


class HermesKompressorPlugin(BaseKompressorPlugin):
    manifest = PluginManifest(
        name="kompressor-hermes",
        harness="hermes",
        entrypoint="kompressor.plugins.builtin:HermesKompressorPlugin",
        mode="native-agent-hook",
        hooks=("pre_user_message", "pre_tool_result", "pre_model_request"),
        transparent=True,
        install_hint=(
            "Install as a Hermes plugin/hook so Hermes compresses large structured user messages and tool results "
            "before model requests. Wrapper fallback: `kompressor plugin show hermes` plus a khermes shim."
        ),
        notes=(
            "Must run after Hermes secret redaction and before model dispatch.",
            "Must not compress tool-call JSON envelopes or tool schemas.",
            "Must not save decompression instructions to durable memory.",
        ),
    )


class CodexKompressorPlugin(BaseKompressorPlugin):
    manifest = PluginManifest(
        name="kompressor-codex",
        harness="codex",
        entrypoint="kompressor.plugins.builtin:CodexKompressorPlugin",
        mode="codex-wrapper-or-openai-middleware",
        hooks=("pre_user_input", "pre_tool_output", "responses_request"),
        transparent=True,
        install_hint=(
            "Install as a Codex/OpenAI-compatible middleware or launch Codex through a Kompressor wrapper shim."
        ),
        notes=("Codex packaging uses developer instructions plus compressed user input.",),
    )
