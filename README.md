# Kompressor

Kompressor is a local-first LLM context optimization toolkit. It reduces avoidable input-token overhead by transforming verbose structured payloads into compact, reversible formats before a caller sends the context to an LLM harness or agent runtime.

Kompressor cannot modify any provider's internal tokenizer or pricing rules. Character-count token estimates are proxies, not exact billing measurements, unless a provider-specific live token-count estimator is explicitly run and recorded.

## Headline benchmark figures

Latest local vNext mixed-strategy benchmark: `artifacts/bench/2026-06-25-vnext-strategies`.

Latest lossless-suite benchmark: `artifacts/bench/2026-06-26-lossless-suite`.

| Metric | Mixed strategy result | Prompt/externalized lossless result | Local-decode lossless result |
|---|---:|---:|---:|
| Payloads / cases benchmarked | 520 | 520 | 520 |
| Strategies covered | mixed reversible + analytical | reversible-only, no lossy summaries | reversible-only + gated zlib/base85 local decode |
| Median character savings | 64.13% | 76.2881% | 93.1039% |
| Median `cl100k_base` token savings | 69.39% | 58.7480% | 88.8596% |
| Negative `cl100k_base` token-savings cases | 0 | 0 | 0 |
| Reversible round trips checked/passed | 80 / 80 | 520 / 520 | 520 / 520 |
| Synthetic secret-redaction checks passed | 6 / 6 | not applicable | not applicable |

Lossless-suite median `cl100k_base` token savings by selected strategy:

| Lossless strategy | Cases | Median token savings |
|---|---:|---:|
| `sidecar_ref` | 240 | 93.0385% |
| `schema_rows` | 80 | 58.1317% |
| `domain_table` | 80 | 34.6633% |
| `shape_rows` | 40 | 24.9692% |
| `token_lz` | 39 | 9.1837% |
| `transport_deflate` (local-decode mode) | 280 | 71.0619% |

Mixed-strategy median `cl100k_base` token savings by input kind:

| Input kind | Median token savings |
|---|---:|
| Blob/base64 payloads | 98.49% |
| CI output | 96.36% |
| Markdown documents | 98.70% |
| Source code outlines | 88.74% |
| HTML pages | 83.04% |
| OpenAPI specs | 71.90% |
| Terraform plans | 69.39% |
| Kubernetes YAML | 68.18% |
| JSON record lists | 55.77% |
| Logs | 49.59% |
| Nested JSON path fallback | 28.50% |
| XML path fallback | 0.00% |

These figures are from a synthetic local benchmark using `tiktoken` `cl100k_base`, not provider billing metadata. Provider-specific claims require provider token-count APIs or actual usage metadata.

## How Kompressor achieves compression

Kompressor chooses the smallest safe strategy from a codec registry. Reversible codecs preserve exact reconstruction; analytical codecs are explicitly marked lossy and preserve counts, indexes, exemplars, hashes, and selected evidence instead of pretending full reconstruction is possible.

The vNext strategy set combines:

Reversible strategies:

- `shape_rows`: Generalized nested JSON/dict-of-dicts row encoding with path dictionaries and column transforms.
- `schema_rows`: Typed columnar JSON rows with constant-column elision, enum dictionaries, integer sequences, and prefix transforms.
- `domain_table`: Exact domain indexes with embedded deflated source for OpenAPI/Terraform/Kubernetes/HTML/Markdown-style payloads.
- `xml_shape_rows`: Repeated XML sibling shape rows with exact parsed XML reconstruction.
- `atom_dict`: Global atom/string dictionaries for repeated scalar strings and keys.
- `chunk_store`: Repeated paragraph/line chunk dictionaries.
- `code_tokens`: Exact Python token-stream serialization for syntax-aware source-code compression experiments.
- `transport_deflate`: Explicitly gated zlib/base85 local-decode transport compression; disabled by default for prompt-readable mode.
- `meta_tokens`: Token-cost-scored LZ-style phrase dictionaries inspired by lossless meta-token compression.
- `token_lz`: Tokenizer-cost-aware repeated-span packing with exact local decompression.
- `separator_segments`: Exact dictionaries for repeated line/paragraph/document segments.
- `grammar`: Token-cost-scored Re-Pair-style reversible grammar rules for repeated adjacent token pairs.
- `path_dict_rows`: Path dictionaries plus value rows for nested JSON-like records.
- `tree_dict`: Repeated-subtree dictionaries for JSON/YAML-like object trees.
- `session_delta`: Hash/base-backed exact deltas for repeated session context.
- `sidecar_ref`: Hash-backed local sidecars for very large immutable payloads.
- `log_templates`: Reversible log template/variable encoding.
- `dedupe`: Repeated-block references.
- Existing `json_table`, `json_path`, `xml_path`, `pattern_hash`, and `binary` fallbacks.

Analytical/task-oriented strategies:

- `log_summary` and `log_templates`: log template extraction, level counts, repeated-pattern summaries, and exact template mode for reversible cases.
- `ci_output`: failed-test/error/warning extraction with passed-line counts.
- `openapi`: operation/schema indexes for API specs.
- `terraform_plan`: action/resource summaries for plan JSON/text.
- `k8s_yaml`: resource/image/namespace summaries with noisy metadata omitted.
- `html_visible` and `markdown_outline`: visible headings, links, outlines, and selected document structure.
- `code_symbols`: import and symbol outlines for source files.
- `blob_ref`: base64/blob externalization to size/hash references.
- `dedupe`: repeated-block references.
- Existing `json_path`, `xml_path`, `pattern_hash`, and `binary` fallbacks.

## Context Gateway

Kompressor now includes a local context gateway that combines Kompressor's verified codec engine with Headroom-like deployment ergonomics: OpenAI/Anthropic-compatible proxying, retrieval-backed originals, raw-text-free stats, agent wrappers, and offline proof/benchmark scripts.

```bash
kompressor gateway serve --host 127.0.0.1 --port 8787 --upstream https://api.openai.com --mode strict
kompressor wrap agent claudish --print-only --json -- --model ollama@qwen2.5:3b
python scripts/gateway_proof.py --out artifacts/proof/gateway-offline.json
python scripts/gateway_benchmark.py --out artifacts/bench/gateway
```

The gateway is strict by default: prompt-readable reversible compression is allowed, retrieval-backed externalization requires retrieval support, local-decode compression is explicit, and lossy analytical summaries are opt-in. Gateway stats are character-count estimates unless provider usage metadata is explicitly collected. See `docs/context-gateway.md` and `docs/comparison-headroom.md`.

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

## Installation

Kompressor requires Python 3.10 or newer. Choose the installer that matches how you want the `kompressor` CLI to be managed.

### End-user CLI install

Recommended with `uv`:

```bash
uv tool install kompressor
kompressor hermes install --prove
```

Equivalent `pipx` install:

```bash
pipx install kompressor
kompressor hermes install --prove
```

One-off execution without installing a persistent tool:

```bash
uvx kompressor --help
uvx kompressor hermes install --prove
```

### Install from a source checkout

For local editable work with `uv`:

```bash
git clone https://github.com/CJCShadowsan/kompressor.git
cd kompressor
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e '.[dev]'
kompressor hermes install --prove
```

For local editable work with standard `pip`:

```bash
git clone https://github.com/CJCShadowsan/kompressor.git
cd kompressor
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
kompressor hermes install --prove
```

After installing the Hermes plugin, start a new Hermes session. Check status any time with:

```bash
kompressor hermes status
```

## Quickstart for development

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e '.[dev]'
python -m pytest
python -m ruff check .
kompressor --help
```

If you are not using `uv`, replace the environment and install steps with `python3.11 -m venv .venv` and `python -m pip install -e '.[dev]'`.

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

Install Claude Code / claudish one-shot shims:

```bash
kompressor claude-code install --target both --mode shim --prove
kompressor claude-code status
kompressor claude-code prove
kompressor claude-code run tests/fixtures/logs.json --target claudish --model ollama@qwen2.5:3b --task "Find auth failures"
```

Install Claude Code / claudish Anthropic request-proxy wrappers:

```bash
kompressor claude-code install --target both --mode proxy --port 8765
kompressor-claude-proxy -p "Summarize this project"
```

Or run the proxy directly and point Claude Code at it:

```bash
kompressor claude-code proxy --port 8765 --upstream https://api.anthropic.com
ANTHROPIC_BASE_URL=http://127.0.0.1:8765 claude -p "Summarize this project"
```

The proxy rewrites Anthropic `/v1/messages` requests before provider dispatch, compressing large user/tool-result text blocks while preserving tool schemas, assistant tool-use blocks, images, and non-text content. The one-shot shim remains useful for local/claudish stdin workflows. See `docs/claude-code-integration.md` for installation details and native hook API findings.

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

Codex note: `kompressor-codex` is explicit packaging unless Codex is routed
through a request-rewrite/base-url integration that the gateway can observe.
Installing an MCP server or prompt hook alone does not transparently shrink every
stock Codex GUI/CLI ChatGPT-auth turn, because those hooks cannot replace the
submitted prompt.

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

Reversible/default-safe strategies:

- `shape_rows`: Generalized nested structure rows for homogeneous dict/list shapes.
- `schema_rows`: Typed columnar JSON records with enum dictionaries, constants, integer sequences, and prefix transforms.
- `domain_table`: Reversible domain index plus embedded deflated source for common structured documents.
- `xml_shape_rows`: Repeated XML element shape rows.
- `atom_dict`: Global repeated atom/string dictionaries.
- `chunk_store`: Repeated paragraph/line chunk references.
- `code_tokens`: Exact Python token stream representation.
- `transport_deflate`: Gated zlib/base85 local-decode transport compression.
- `meta_tokens`: Token-cost-scored textual meta-token dictionaries.
- `token_lz`: Tokenizer-cost-aware repeated-span packing.
- `separator_segments`: Repeated separator-delimited segment dictionaries.
- `grammar`: Token-cost-scored reversible grammar rules.
- `path_dict_rows`: Nested path dictionaries and value rows.
- `tree_dict`: Repeated-subtree references for JSON-like trees.
- `session_delta`: Base-context plus exact delta patches; requires local base metadata.
- `sidecar_ref`: Hash-backed local sidecar references for large immutable payloads.
- `json_table`: Reversible table format for list-of-dict JSON payloads.
- `log_templates`: Reversible template/variable encoding for repeated log lines.
- `dedupe`: Reversible repeated-block references.
- `json_path`: JSONPath/value representation for nested JSON. Exact local decompression uses Python metadata.
- `xml_path`: XML path/value representation. Exact local decompression uses Python metadata.
- `pattern_hash`: Dictionary replacement for repeated log lines.
- `binary`: Disabled by default for prompt compression; explicit base64/base85 are available through the API.

Analytical/task-oriented strategies:

- `log_summary`: Level counts, template counts, and error/warning exemplars.
- `ci_output`: Failed-test/error/warning summaries for build logs.
- `openapi`: Operation/schema index for OpenAPI specs.
- `terraform_plan`: Resource-action summaries for Terraform plans.
- `k8s_yaml`: Kubernetes resource/image/namespace summaries.
- `html_visible`: Visible headings and links from HTML.
- `markdown_outline`: Section outlines and document structure.
- `code_symbols`: Import and symbol outlines for source code.
- `tool_output`: Error/diff/line-selected summaries for agent tool output.
- `blob_ref`: Base64/blob replacement with size/hash references.
- `extractive`: Extractive paragraph selection for long natural-language text.

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
