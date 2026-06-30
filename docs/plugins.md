# Kompressor Plugins

Kompressor plugins make compression transparent when a harness exposes pre-send, tool-output, or request-rewrite hooks.

The plugin layer is separate from codecs and harness adapters:

- codecs decide whether a payload can be compacted safely
- harness adapters package an optimized payload for a runtime
- plugins attach that packaging to a harness lifecycle hook

## Built-in plugins

Every supported harness has a plugin entrypoint:

| Harness | Plugin | Entrypoint | Intended mode |
|---|---|---|---|
| generic | `kompressor-generic` | `kompressor.plugins.builtin:GenericKompressorPlugin` | portable pre-send hook |
| claude | `kompressor-claude` | `kompressor.plugins.builtin:ClaudeKompressorPlugin` | Anthropic request middleware or Claude wrapper |
| openai | `kompressor-openai` | `kompressor.plugins.builtin:OpenAIKompressorPlugin` | OpenAI-compatible middleware/base-url proxy |
| gemini | `kompressor-gemini` | `kompressor.plugins.builtin:GeminiKompressorPlugin` | Gemini client middleware |
| hermes | `kompressor-hermes` | `kompressor.plugins.builtin:HermesKompressorPlugin` | native agent pre-message/pre-tool-result hook |
| codex | `kompressor-codex` | `kompressor.plugins.builtin:CodexKompressorPlugin` | Codex one-shot wrapper or request middleware |

Inspect them locally:

```bash
kompressor plugin list
kompressor plugin show hermes
kompressor plugin show codex --json
```

Run a pre-send hook manually:

```bash
kompressor plugin preflight hermes tests/fixtures/logs.json --task "Find auth failures"
```

## Hermes transparent plugin path

The preferred Hermes integration is native, not a PTY shim.

Hook placement:

```text
Hermes user message
  -> Hermes secret redaction / safety checks
  -> KompressorHermesPlugin.prepare_user_input
  -> Hermes model request builder

Hermes tool result
  -> Hermes secret redaction
  -> KompressorHermesPlugin.prepare_tool_output
  -> model-visible tool result content
```

Rules:

- run after secret redaction and before model dispatch
- do not compress tool-call JSON envelopes
- do not compress tool schemas
- do not mutate durable memory
- do not change role alternation
- keep decompression instructions task-local

Python hook example:

```python
from kompressor.plugins import get_plugin

plugin = get_plugin("hermes", threshold_chars=512, redact=True)
prepared = plugin.prepare_user_input(large_payload, task="Analyze failures")
content_for_model = prepared.content if prepared.changed else large_payload
```

## Claude / Anthropic transparent plugin path

Use `ClaudeKompressorPlugin` as request middleware where a Claude client exposes outgoing request hooks. If only a CLI is available, run it behind a wrapper that rewrites the initial prompt before invoking the real CLI.

```python
from kompressor.plugins import get_plugin

plugin = get_plugin("claude", threshold_chars=512)
request = plugin.prepare_request({"messages": [{"role": "user", "content": large_payload}]})
```

## OpenAI transparent plugin path

OpenAI-compatible harnesses should install the plugin as middleware or route through a base-url proxy.

```python
from kompressor.plugins import get_plugin

plugin = get_plugin("openai", threshold_chars=512)
request = plugin.prepare_request({"messages": [{"role": "user", "content": large_payload}]})
```

## Codex integration status

`CodexKompressorPlugin` can package compressed input for explicit one-shot use, and
OpenAI-compatible Codex deployments can be routed through the gateway when their
model requests use `/v1/responses`, `/v1/chat/completions`, or `/v1/messages`.

Stock Codex GUI/CLI ChatGPT-auth sessions are different: installing an MCP server
or registering a user-prompt hook does not, by itself, replace the prompt that
Codex sends to the model. The current Codex `UserPromptSubmit` hook can add
context or block a prompt, but it cannot mutate the submitted prompt, so it cannot
transparently reduce input tokens for every session turn. For that path,
Kompressor needs a real request-rewrite/base-url integration that is proven by
gateway stats before it should be called transparent.

## Gemini transparent plugin path

Gemini clients should use `GeminiKompressorPlugin` before `generate_content` calls so instructions can be placed in `system_instruction` and compressed payload in `contents`.

## Wrapper fallback

For harnesses without plugin hooks, a wrapper can still be transparent for one-shot invocations:

```bash
kompressor plugin preflight hermes logs.json --task "Analyze logs" > /tmp/context.txt
hermes chat -q "$(cat /tmp/context.txt)"
```

A wrapper is less powerful than a native plugin because it cannot reliably intercept later interactive turns or internal tool outputs.
