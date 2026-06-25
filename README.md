# Kompressor

Kompressor is a local-first LLM context optimization toolkit. It reduces avoidable input-token overhead by transforming verbose structured payloads into compact, reversible formats before a caller sends the context to an LLM harness or agent runtime.

Kompressor cannot modify any provider's internal tokenizer or pricing rules. Character-count token estimates are proxies, not exact billing measurements, unless a provider-specific live token-count estimator is explicitly run and recorded.

## Status

Implementation covers the first multi-harness release surface:

- Python package and CLI
- Reversible JSON table compression
- JSON path and XML path readable compaction
- Repeating-line pattern dictionary compression
- Safe-by-default binary handling
- Generic decompression prompt generation
- Harness adapters for `generic`, `claude`, `openai`, `gemini`, `hermes`, and `codex`
- Transparent plugin entrypoints for every supported harness
- Dry-run proxy helpers
- Secret detection/redaction
- Benchmark command and documentation

## Install for Hermes users

Recommended end-user install:

```bash
pipx install kompressor
kompressor hermes install --prove
```

From a source checkout:

```bash
git clone https://github.com/CJCShadowsan/kompressor.git
cd kompressor
python -m pip install -e .
kompressor hermes install --prove
```

After install, start a new Hermes session. Check status any time with:

```bash
kompressor hermes status
```

## Quickstart for development

```bash
/Users/ccoates/.local/bin/python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
kompressor --help
```

## CLI examples

Analyze a fixture:

```bash
kompressor analyze tests/fixtures/logs.json
```

Create a generic compressed prompt bundle:

```bash
kompressor compress tests/fixtures/logs.json --harness generic
```

Create a harness-specific bundle:

```bash
kompressor compress tests/fixtures/logs.json --harness claude
kompressor compress tests/fixtures/logs.json --harness openai --json
kompressor compress tests/fixtures/logs.json --harness gemini --json
kompressor compress tests/fixtures/logs.json --harness hermes
kompressor compress tests/fixtures/logs.json --harness codex
```

Backward-compatible Claude formatting remains available:

```bash
kompressor compress tests/fixtures/logs.json --format claude --include-system-prompt
```

Run a benchmark report:

```bash
kompressor bench tests/fixtures --format markdown --output docs/benchmarks.md
```

Inspect transparent harness plugins:

```bash
kompressor plugin list
kompressor plugin show hermes
kompressor plugin preflight codex tests/fixtures/logs.json --task "Find auth failures"
```

Install Kompressor into Hermes as a native plugin:

```bash
kompressor hermes install --prove
kompressor hermes status
kompressor hermes prove
```

## Python API example

```python
from kompressor.engine import KompressorEngine
from kompressor.harnesses import get_harness_adapter

payload = [{"id": "AX-912", "event": "auth_timeout_error"}]
result = KompressorEngine().optimize(payload)
bundle = get_harness_adapter("hermes").package(result, "Find auth failures")
print(bundle.content)
```

## Harness adapters

The compression engine is provider-neutral. Harness adapters only decide where parsing instructions and payload should go.

- `generic`: plain text instructions and payload.
- `claude` / `anthropic`: Anthropic-style `system` plus user message shape.
- `openai`: developer message plus user message shape.
- `gemini`: `system_instruction` plus `contents` shape.
- `hermes`: task-local parsing rules suitable for `hermes chat -q` or project workflows.
- `codex`: Codex/OpenAI-agent developer instructions plus compressed input.

## Transparent plugins

Each harness has a plugin entrypoint under `kompressor.plugins.builtin`:

- `GenericKompressorPlugin`
- `ClaudeKompressorPlugin`
- `OpenAIKompressorPlugin`
- `GeminiKompressorPlugin`
- `HermesKompressorPlugin`
- `CodexKompressorPlugin`

Plugins expose `prepare_user_input`, `prepare_tool_output`, and `prepare_request` hooks. Native harness hooks are preferred for full-session transparency; wrapper shims can only transparently rewrite initial one-shot prompts.

See `docs/plugins.md` for hook placement and integration guidance.

## Hermes Codex compatibility patch

Kompressor never edits Hermes during package installation. For Hermes versions whose Codex app-server runtime bypasses `llm_request` middleware, use the explicit reversible patch command:

```bash
kompressor hermes patch status
kompressor hermes patch apply
kompressor hermes patch prove
kompressor hermes patch uninstall
```

The patch is marker-bounded, backed up under `~/.kompressor/patches/hermes/`, syntax-checked, and becomes a no-op once Hermes upstream contains an equivalent middleware bridge. See `docs/hermes-codex-patch.md`.

## Compression strategies

- `json_table`: Reversible table format for list-of-dict JSON payloads.
- `json_path`: JSONPath/value representation for nested JSON. Exact local decompression uses Python metadata.
- `xml_path`: XML path/value representation. Exact local decompression uses Python metadata.
- `pattern_hash`: Dictionary replacement for repeated log lines.
- `binary`: Disabled by default for prompt compression; explicit base64/base85 are available through the API.

## Security and privacy

Proxy helpers do not log raw payloads. Suspected secrets cause proxy preparation to fail unless redaction or explicit override is selected. Redaction should run before compression so dictionaries do not preserve secrets.

## Limits and claim policy

- Kompressor cannot alter provider tokenizers or pricing.
- Default savings are estimates from the deterministic `char_proxy` estimator.
- Provider-specific token counters must label provider, model, and date.
- Claims such as typical savings or up-to-40-percent savings must be backed by `kompressor bench` artifacts or live provider count-token measurements.
- Binary/Base122-style prompt compression remains experimental until benchmark evidence proves savings.

## Planning artifacts

- Goal: `docs/goals/implement-all-slices.md`
- Plan: `docs/plans/2026-06-24-claude-context-optimization-engine.md`
- Loop: `docs/loops/implement-goal-loop.md`
- Implementation log: `docs/loops/implementation-log.md`
- Plugins: `docs/plugins.md`
