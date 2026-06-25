# Kompressor

Kompressor is a local-first LLM context optimization toolkit. It reduces avoidable input-token overhead by transforming verbose structured payloads into compact, reversible formats before a caller sends the context to an LLM harness or agent runtime.

Kompressor cannot modify any provider's internal tokenizer or pricing rules. Character-count token estimates are proxies, not exact billing measurements, unless a provider-specific live token-count estimator is explicitly run and recorded.

## Headline benchmark figures

Latest local vNext mixed-strategy benchmark: `artifacts/bench/2026-06-25-vnext-strategies`.

Latest reversible-strategy benchmark: `artifacts/bench/2026-06-25-reversible-strategies`.

| Metric | Mixed strategy result | Reversible-only result |
|---|---:|---:|
| Payloads / cases benchmarked | 520 | 320 |
| Strategies covered | mixed reversible + analytical | 8 reversible |
| Median character savings | 64.13% | 65.28% |
| p25 / p75 character savings | 50.20% / 90.82% | not reported |
| Median `cl100k_base` token savings | 69.39% | 55.20% |
| p25 / p75 `cl100k_base` token savings | 55.31% / 88.78% | not reported |
| Negative character-savings cases | 0 | 0 in strategy medians |
| Negative `cl100k_base` token-savings cases | 0 | 0 |
| Reversible round trips checked/passed | 80 / 80 | 320 / 320 |
| Synthetic secret-redaction checks passed | 6 / 6 | not applicable |

Reversible-only median `cl100k_base` token savings by strategy:

| Reversible strategy | Median token savings |
|---|---:|
| `sidecar_ref` | 97.73% |
| `grammar` | 93.64% |
| `session_delta` | 71.21% |
| `meta_tokens` | 61.01% |
| `path_dict_rows` | 49.39% |
| `tree_dict` | 45.73% |
| `separator_segments` | 22.73% |
| `token_lz` | 9.07% |

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

- `schema_rows`: typed columnar JSON rows with constant-column elision and enum dictionaries.
- `meta_tokens`: LZ-style phrase dictionaries inspired by lossless meta-token compression.
- `token_lz`: tokenizer-proxy repeated-span packing with exact local decompression.
- `separator_segments`: exact dictionaries for repeated line/paragraph/document segments.
- `grammar`: Re-Pair-style reversible grammar rules for repeated adjacent token pairs.
- `path_dict_rows`: path dictionaries plus value rows for nested JSON-like records.
- `tree_dict`: repeated-subtree dictionaries for JSON/YAML-like object trees.
- `session_delta`: hash/base-backed exact deltas for repeated session context.
- `sidecar_ref`: hash-backed local sidecars for very large immutable payloads.
- `log_templates`: reversible log template/variable encoding.
- `dedupe`: repeated-block references.
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

Reversible/default-safe strategies:

- `schema_rows`: Typed columnar JSON records with enum dictionaries and constant-column elision.
- `meta_tokens`: LZ-style textual meta-token dictionaries.
- `token_lz`: tokenizer-proxy repeated-span packing.
- `separator_segments`: Repeated separator-delimited segment dictionaries.
- `grammar`: Re-Pair-style reversible grammar rules.
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
