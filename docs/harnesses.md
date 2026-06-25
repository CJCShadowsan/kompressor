# Harness Adapters

Kompressor separates compression from harness packaging.

The core engine returns:

- optimized payload
- decompression instructions
- token/cost estimates
- codec metadata
- warnings

Harness adapters convert that neutral result into a target runtime shape.

## Supported harnesses

### generic

Plain text bundle with `KOMPRESSOR_CONTEXT_INSTRUCTIONS` and `KOMPRESSOR_PAYLOAD` sections.

### claude / anthropic

Anthropic Messages-style shape:

```json
{"system": "...", "messages": [{"role": "user", "content": "..."}]}
```

### openai

OpenAI Chat/Responses-style shape using a developer message:

```json
{"messages": [{"role": "developer", "content": "..."}, {"role": "user", "content": "..."}]}
```

### gemini

Gemini-style `system_instruction` and `contents` shape.

### hermes

A single task-local prompt that tells Hermes to treat Kompressor instructions as parsing rules and not durable memory. Example:

```bash
kompressor compress logs.json --harness hermes --output /tmp/context.txt
hermes chat -q "$(cat /tmp/context.txt)"
```

### codex

Codex/OpenAI-agent style developer instructions plus compressed user input. Use this when launching Codex through a wrapper or when a Codex-compatible client accepts OpenAI-style request middleware.

```bash
kompressor compress logs.json --harness codex
```

## Plugin entrypoints

Every harness also has a transparent plugin entrypoint:

- `generic`: `kompressor.plugins.builtin:GenericKompressorPlugin`
- `claude`: `kompressor.plugins.builtin:ClaudeKompressorPlugin`
- `openai`: `kompressor.plugins.builtin:OpenAIKompressorPlugin`
- `gemini`: `kompressor.plugins.builtin:GeminiKompressorPlugin`
- `hermes`: `kompressor.plugins.builtin:HermesKompressorPlugin`
- `codex`: `kompressor.plugins.builtin:CodexKompressorPlugin`

Use `kompressor plugin list` and `kompressor plugin show <harness>` to inspect hook names and install hints.

## Rule

Compression codecs should stay provider-neutral. Add provider/harness behavior only in `src/kompressor/harnesses/` or provider-specific estimators.
