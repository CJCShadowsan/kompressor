# Claude Context Optimization Engine Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build Kompressor, a client-side context optimization proxy and toolkit that reduces Claude input-token usage by transforming verbose structured inputs into reversible, model-readable dense payloads before Anthropic API submission.

**Architecture:** Kompressor is a local-first Python package with a core optimization engine, measurable token/cost estimators, reversible flattening codecs, a Claude system-prompt decompression contract, a CLI, and optional integration adapters. It must treat “30%–40% savings” as a measured target, not a guaranteed claim; every optimizer needs benchmark coverage against representative JSON, logs, XML, code, and binary fixtures.

**Tech Stack:** Python 3.10+, Typer CLI, Pydantic configuration models, pytest, hypothesis, ruff, mypy/pyright optional, Anthropic SDK integration behind an optional extra, browser extension planned as a later TypeScript package.

---

## Product Definition

### Target users

1. Individual developers pasting large logs, traces, config files, and code snippets into Claude.
2. Enterprise platform teams routing large diagnostic payloads through Claude APIs.
3. Power users who want local pre-flight previews of estimated token and dollar savings before sending data.

### User-facing outcomes

1. `kompressor analyze input.json` reports baseline size, optimized size, estimated tokens, cost delta, optimizer strategy, and reversibility status.
2. `kompressor compress input.json --format claude` emits a dense payload plus the matching Claude system prompt.
3. `kompressor proxy` accepts Anthropic-compatible request payloads, compresses eligible context fields, injects decompression instructions, forwards the request, and returns the Claude response.
4. Python users can import `ClaudeTokenSaver`/`KompressorEngine` and call stable APIs from applications and CI pipelines.
5. Teams can run benchmark reports that prove whether a workload actually saves tokens before deploying the proxy.

### Non-goals for the first production release

1. Do not claim access to or control over Claude’s internal tokenizer.
2. Do not mutate user meaning; compression must be either reversible or explicitly marked lossy.
3. Do not hide benchmark uncertainty. Character-per-token estimates are only a fallback proxy.
4. Do not implement browser-extension interception until the core engine and API contracts are stable.
5. Do not default to Base122/binary mappings for Claude text inputs until empirical token measurements prove value; byte-dense encodings can increase LLM token count.

---

## Architecture Overview

```text
Raw user data / code / logs
        |
        v
Input classifier
        |
        +--> JSON table flattening codec
        +--> XML path flattening codec
        +--> Log template/pattern hashing codec
        +--> Text/code deduplication codec
        +--> Binary attachment strategy
        |
        v
Dense payload + metadata envelope
        |
        +--> Token/cost estimator
        +--> Reversibility validator
        +--> Claude system prompt generator
        |
        v
CLI / Python API / Anthropic proxy / future browser extension
```

### Core components

1. `kompressor.engine.KompressorEngine`
   - Orchestrates classification, strategy selection, compression, validation, and metrics.
   - Returns a typed `OptimizationResult` with payload, stats, warnings, and decompression instructions.

2. `kompressor.codecs.*`
   - `JsonTableCodec`: converts homogeneous object arrays into delimited table format.
   - `JsonPathCodec`: converts nested JSON into path/value lines when table shape is not safe.
   - `XmlPathCodec`: strips XML tag bloat while preserving element paths and attributes.
   - `PatternHashCodec`: detects repeated log/event substrings and replaces them with local dictionary references.
   - `BinaryCodec`: initially emits a warning and uses base64/base85 only when requested; Base122 is experimental behind a feature flag.

3. `kompressor.prompts.ClaudePromptBuilder`
   - Produces a concise system prompt explaining the dense payload format.
   - Includes codec-specific parsing rules and a safety instruction not to expose compression details unless asked.

4. `kompressor.estimation.TokenEstimator`
   - Supports pluggable estimators:
     - `CharProxyEstimator`: deterministic fallback, default `chars_per_token=4.0`.
     - `AnthropicCountTokensEstimator`: optional live API count-token integration when `ANTHROPIC_API_KEY` is available.
     - `FixtureBaselineEstimator`: test-only estimator for deterministic regression tests.

5. `kompressor.cli`
   - `analyze`, `compress`, `decompress`, `bench`, and `proxy` commands.

6. `kompressor.proxy`
   - Lightweight local HTTP proxy compatible with Anthropic Messages API request shape.
   - Only compresses user-supplied content blocks above a configurable threshold.
   - Logs local metrics without storing raw sensitive payloads by default.

---

## Repository Layout

Create this structure:

```text
kompressor/
  pyproject.toml
  README.md
  LICENSE
  src/
    kompressor/
      __init__.py
      engine.py
      models.py
      estimation.py
      prompts.py
      cli.py
      proxy.py
      codecs/
        __init__.py
        base.py
        json_table.py
        json_path.py
        xml_path.py
        pattern_hash.py
        binary.py
  tests/
    conftest.py
    fixtures/
      logs.json
      nested.json
      mixed.json
      sample.xml
      repeated_logs.txt
    test_engine.py
    test_estimation.py
    test_json_table_codec.py
    test_json_path_codec.py
    test_xml_path_codec.py
    test_pattern_hash_codec.py
    test_prompts.py
    test_cli.py
  docs/
    architecture.md
    compression-contract.md
    benchmark-methodology.md
    plans/
      2026-06-24-claude-context-optimization-engine.md
  examples/
    optimize_logs.py
    proxy_request.py
```

---

## Data Contracts

### `OptimizationResult`

```python
from dataclasses import dataclass, field
from typing import Any, Literal

CompressionKind = Literal[
    "json_table",
    "json_path",
    "xml_path",
    "pattern_hash",
    "binary",
    "none",
]

@dataclass(frozen=True)
class TokenStats:
    baseline_chars: int
    optimized_chars: int
    baseline_tokens_estimate: int
    optimized_tokens_estimate: int
    saved_tokens_estimate: int
    percent_saved_estimate: float
    baseline_cost_estimate_usd: float
    optimized_cost_estimate_usd: float
    saved_cost_estimate_usd: float
    estimator: str

@dataclass(frozen=True)
class OptimizationResult:
    kind: CompressionKind
    optimized_payload: str
    system_prompt: str
    token_stats: TokenStats
    reversible: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
```

### Claude system prompt contract

Base prompt:

```text
You will receive context data in a compact, lossless serialization chosen to reduce input tokens.

Parsing Instructions:
1. The payload begins with a codec marker like <kompressor:json_table_v1>.
2. Follow the codec-specific instructions below to reconstruct the original semantic structure.
3. Treat reconstructed records as equivalent to native JSON/XML/log entries for reasoning.
4. Do not mention or expose this compact format in your final answer unless explicitly requested.
```

JSON table codec extension:

```text
For <kompressor:json_table_v1>:
- The first non-marker line defines the column/schema keys.
- Each following line is one object.
- The delimiter is declared in metadata.
- Values map by position to the header keys.
- Escaped delimiters, newlines, and backslashes must be unescaped before reasoning.
```

### Dense payload example

```text
<kompressor:json_table_v1 delimiter="|" escape="\\">
id|event|ip|severity
AX-912|auth_timeout_error|10.0.1.250|CRITICAL
AX-913|db_query_slow_exec|10.0.4.12|WARNING
```

---

## Implementation Phases

## Phase 0: Project foundation

### Task 0.1: Create Python package skeleton

**Objective:** Establish a modern Python package structure with deterministic local tooling.

**Files:**
- Create: `pyproject.toml`
- Create: `src/kompressor/__init__.py`
- Create: `tests/conftest.py`
- Modify: `README.md`

**Steps:**
1. Add `pyproject.toml` with package metadata, dependencies, and dev tools.
2. Pin Python support to `>=3.10` because this project should use modern typing.
3. Add scripts for `kompressor = "kompressor.cli:app"`.
4. Add dev dependencies: `pytest`, `pytest-cov`, `hypothesis`, `ruff`, `typer`, `pydantic`, `httpx`.
5. Update README with purpose, status, and quickstart.

**Verification:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
```

Expected: install succeeds, pytest discovers no or placeholder tests, ruff passes.

**Commit:**

```bash
git add pyproject.toml README.md src tests
git commit -m "chore: initialize kompressor python package"
```

---

## Phase 1: Core models and estimation

### Task 1.1: Add result and configuration models

**Objective:** Define stable typed contracts before implementing codecs.

**Files:**
- Create: `src/kompressor/models.py`
- Test: `tests/test_models.py`

**Implementation details:**
- Add `TokenStats`, `OptimizationResult`, and `KompressorConfig`.
- Include validation for positive costs and token estimates.
- Keep defaults configurable:
  - `cost_per_million_input_usd=3.00`
  - `chars_per_token_proxy=4.0`
  - `minimum_chars_to_optimize=200`
  - `delimiter_candidates=("|", "\t", "¦", "~")`

**Test cases:**
1. Defaults instantiate successfully.
2. Negative cost raises validation error.
3. Result can serialize to JSON-friendly dict.

**Verification:**

```bash
python -m pytest tests/test_models.py -v
```

Expected: all model tests pass.

### Task 1.2: Implement token/cost estimator

**Objective:** Provide deterministic savings calculations with explicit estimator labels.

**Files:**
- Create: `src/kompressor/estimation.py`
- Test: `tests/test_estimation.py`

**Implementation details:**
- Implement `CharProxyEstimator.estimate_tokens(text: str) -> int`.
- Implement `calculate_stats(raw: str, optimized: str, config: KompressorConfig)`.
- Round percentages and costs consistently.
- Never return negative savings percentages as a success; mark compression as expanded when optimized is larger.

**Test cases:**
1. Empty string estimates to 1 token only when required for cost display, or 0 if configured.
2. A 400-character string estimates to 100 tokens with default proxy.
3. Optimized larger than raw produces negative savings and a warning.
4. Cost math uses configurable dollars per million tokens.

**Verification:**

```bash
python -m pytest tests/test_estimation.py -v
```

---

## Phase 2: JSON table flattening codec

### Task 2.1: Implement codec interface

**Objective:** Define a reusable interface for compression strategies.

**Files:**
- Create: `src/kompressor/codecs/base.py`
- Create: `src/kompressor/codecs/__init__.py`
- Test: `tests/test_engine.py`

**Interface sketch:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class CodecResult:
    payload: str
    reversible: bool
    metadata: dict[str, object]
    warnings: list[str]

class Codec(ABC):
    name: str

    @abstractmethod
    def can_handle(self, value: object) -> bool: ...

    @abstractmethod
    def compress(self, value: object) -> CodecResult: ...

    @abstractmethod
    def decompress(self, payload: str, metadata: dict[str, object]) -> object: ...
```

**Verification:**

```bash
python -m pytest tests/test_engine.py -v
```

Expected initially: tests verify interface import and no concrete behavior yet.

### Task 2.2: Implement homogeneous JSON array detection

**Objective:** Safely identify list-of-dict payloads that can become compact tables.

**Files:**
- Create: `src/kompressor/codecs/json_table.py`
- Test: `tests/test_json_table_codec.py`

**Rules:**
1. Input must be a non-empty list.
2. Every element must be a dict.
3. Object keys may vary, but header order is the stable union of first-seen keys.
4. Values must be scalar or converted with JSON encoding; nested dict/list values need escaping or fallback to `JsonPathCodec`.
5. Codec must declare whether output is fully reversible.

**Test cases:**
1. Homogeneous flat objects are accepted.
2. Empty lists are rejected or return empty non-optimized result.
3. Mixed scalar/list/dict values do not silently lose structure.
4. Missing keys produce empty cells and round-trip to missing-vs-empty according to documented policy.

### Task 2.3: Add escaping and delimiter selection

**Objective:** Prevent structural breakage when values contain pipes, tabs, slashes, or newlines.

**Files:**
- Modify: `src/kompressor/codecs/json_table.py`
- Test: `tests/test_json_table_codec.py`

**Rules:**
1. Pick the delimiter with the fewest collisions from configured candidates.
2. Escape backslash first, then delimiter, then newline.
3. Decompress must recover original strings exactly.
4. Include delimiter and escape metadata in payload header.

**Test cases:**
1. Value `"a|b"` round-trips.
2. Value containing newline round-trips.
3. Unicode strings round-trip.
4. Collision-heavy data picks a better delimiter.

### Task 2.4: Port and harden the brief’s `ClaudeTokenSaver`

**Objective:** Preserve the simple user-facing API from the brief while backing it with production code.

**Files:**
- Create: `src/kompressor/legacy.py` or expose in `src/kompressor/__init__.py`
- Test: `tests/test_legacy_api.py`

**Compatibility API:**

```python
class ClaudeTokenSaver:
    def estimate_tokens(self, text: str) -> int: ...
    def flatten_json_context(self, data_list: list, delimiter: str = "|") -> str: ...
    def calculate_savings(self, raw_data: list) -> dict: ...
```

**Hardening changes:**
1. Fix formatting/import issues from the brief (`import osimport json` is invalid).
2. Use shared estimator and JSON table codec internally.
3. Add warnings when data is not a list of flat dicts.
4. Do not promise exact Anthropic token counts from character proxy.

**Verification:**

```bash
python -m pytest tests/test_legacy_api.py tests/test_json_table_codec.py -v
```

---

## Phase 3: Engine orchestration

### Task 3.1: Implement `KompressorEngine.optimize`

**Objective:** Choose the best available codec and return a complete `OptimizationResult`.

**Files:**
- Create: `src/kompressor/engine.py`
- Test: `tests/test_engine.py`

**Behavior:**
1. Accept `str`, `bytes`, `dict`, `list`, or parsed data.
2. If string looks like JSON, parse and route to JSON codecs.
3. If string looks like XML, route to XML codec once implemented.
4. If string/log text has repeated lines or substrings, route to pattern hashing once implemented.
5. If no strategy saves tokens, return `kind="none"` and original payload with warning.
6. Always compute baseline vs optimized stats.
7. Always include system prompt when compression is used.

**Test cases:**
1. JSON array uses `json_table`.
2. Small payload below threshold returns no optimization.
3. Invalid JSON string falls back to text/pattern strategy later or none now.
4. Optimizer does not choose a larger payload unless `allow_expansion=True`.

### Task 3.2: Add decompression validation loop

**Objective:** Prove reversible codecs do not corrupt data.

**Files:**
- Modify: `src/kompressor/engine.py`
- Test: `tests/test_engine.py`

**Behavior:**
1. If codec claims reversible, call `decompress` immediately after `compress`.
2. Compare canonicalized original vs decompressed values.
3. If validation fails, reject the codec and fall back to original payload.
4. Include warning with failure reason.

**Verification:**

```bash
python -m pytest tests/test_engine.py -v
```

---

## Phase 4: Claude system prompt generation

### Task 4.1: Implement prompt builder

**Objective:** Generate concise, codec-specific decompression instructions for Claude.

**Files:**
- Create: `src/kompressor/prompts.py`
- Test: `tests/test_prompts.py`
- Create: `docs/compression-contract.md`

**Behavior:**
1. Base prompt must be stable and snapshot-tested.
2. JSON table instructions must mention header row, delimiter, escaping, and row-to-object mapping.
3. Pattern hashing instructions must mention dictionary expansion order.
4. Prompt builder must support `verbosity="minimal" | "standard" | "debug"`.

**Test cases:**
1. Prompt contains the codec marker.
2. Prompt contains delimiter metadata.
3. Minimal prompt is below a target character budget.
4. Debug prompt includes examples.

### Task 4.2: Add prompt+payload packaging

**Objective:** Make the CLI and proxy return exactly what a Claude API call needs.

**Files:**
- Modify: `src/kompressor/engine.py`
- Modify: `src/kompressor/prompts.py`
- Test: `tests/test_engine.py`

**Output formats:**
1. `payload_only`
2. `system_prompt_only`
3. `claude_messages_json`:

```json
{
  "system": "...decompression prompt...",
  "messages": [
    {"role": "user", "content": "...dense payload...\n\nUser task: ..."}
  ]
}
```

**Verification:**

```bash
python -m pytest tests/test_prompts.py tests/test_engine.py -v
```

---

## Phase 5: Additional codecs

### Task 5.1: Implement JSON path codec

**Objective:** Support nested JSON that cannot safely flatten to a table.

**Files:**
- Create: `src/kompressor/codecs/json_path.py`
- Test: `tests/test_json_path_codec.py`

**Format example:**

```text
<kompressor:json_path_v1>
$.users[0].id=AX-912
$.users[0].event=auth_timeout_error
$.users[1].id=AX-913
```

**Rules:**
1. Preserve arrays and object paths.
2. Use compact JSON values for strings/numbers/bools/null.
3. Round-trip nested fixtures.
4. Benchmark against raw minified JSON; only select when smaller.

### Task 5.2: Implement XML path codec

**Objective:** Remove repetitive XML tag bloat while preserving hierarchy and attributes.

**Files:**
- Create: `src/kompressor/codecs/xml_path.py`
- Test: `tests/test_xml_path_codec.py`

**Format example:**

```text
<kompressor:xml_path_v1>
/root/server[0]/@id=s1
/root/server[0]/ip=10.0.1.250
/root/server[0]/severity=CRITICAL
```

**Rules:**
1. Use Python stdlib XML parser by default.
2. Disable external entity resolution; do not parse unsafe XML features.
3. Preserve text, attributes, and sibling order.
4. Include warnings for comments/processing instructions if not preserved.

### Task 5.3: Implement repeating pattern hashing codec

**Objective:** Compress repeated log patterns with a local dictionary.

**Files:**
- Create: `src/kompressor/codecs/pattern_hash.py`
- Test: `tests/test_pattern_hash_codec.py`
- Fixture: `tests/fixtures/repeated_logs.txt`

**Format example:**

```text
<kompressor:pattern_hash_v1>
@dict
#0 auth_timeout_error from {ip}
#1 db_query_slow_exec on {db} took {ms}ms
@rows
#0 ip=10.0.1.250
#1 db=users ms=913
```

**Implementation approach:**
1. Start with exact repeated line dictionary compression.
2. Add optional regex/template extraction later.
3. Use short stable IDs, not cryptographic hashes, for token efficiency.
4. Keep SHA-256 hashes only in metadata if integrity checks are needed.

**Test cases:**
1. Repeated exact lines compress and round-trip.
2. Mostly unique lines do not compress.
3. Dictionary overhead is included in savings calculation.
4. IDs cannot collide.

### Task 5.4: Treat binary/Base122 as experimental

**Objective:** Avoid shipping a misleading binary optimizer until measured.

**Files:**
- Create: `src/kompressor/codecs/binary.py`
- Test: `tests/test_binary_codec.py`
- Docs: `docs/benchmark-methodology.md`

**Policy:**
1. Default behavior for bytes: report that binary should usually be summarized, extracted, or attached outside the text prompt.
2. Provide base64/base85 only as explicit `--binary-encoding` options.
3. Gate Base122 behind `--experimental-base122`.
4. Add benchmark tests proving it is disabled by default.

---

## Phase 6: CLI

### Task 6.1: Implement `kompressor analyze`

**Objective:** Give users a safe dry-run savings report.

**Files:**
- Create: `src/kompressor/cli.py`
- Test: `tests/test_cli.py`

**Command:**

```bash
kompressor analyze tests/fixtures/logs.json --cost-per-million 3.00
```

**Output:**

```text
Input: tests/fixtures/logs.json
Strategy: json_table
Reversible: yes
Baseline estimate: 12,345 tokens
Optimized estimate: 7,890 tokens
Estimated savings: 36.1%
Estimated input cost delta: $0.013365
Warnings: char-proxy estimate; use --anthropic-count-tokens for live count
```

**Test cases:**
1. CLI exits 0 for valid JSON.
2. CLI returns non-zero for unreadable file.
3. `--json` emits machine-readable stats.

### Task 6.2: Implement `kompressor compress`

**Objective:** Emit dense payload and optional system prompt.

**Command examples:**

```bash
kompressor compress logs.json --output logs.kompressed.txt
kompressor compress logs.json --include-system-prompt --format claude
kompressor compress logs.json --task "Find critical auth failures"
```

**Verification:**

```bash
kompressor compress tests/fixtures/logs.json --include-system-prompt --format claude > /tmp/request.txt
test -s /tmp/request.txt
```

### Task 6.3: Implement `kompressor decompress`

**Objective:** Let users verify reversible payloads locally.

**Command:**

```bash
kompressor decompress logs.kompressed.txt --metadata logs.metadata.json
```

**Acceptance criteria:**
1. JSON table payload decompresses to canonical JSON.
2. Round-trip command can compare against original and exit non-zero on mismatch.

### Task 6.4: Implement `kompressor bench`

**Objective:** Measure savings across fixtures and user-provided corpora.

**Command:**

```bash
kompressor bench tests/fixtures --format markdown --output docs/benchmarks.md
```

**Metrics:**
1. Raw bytes/chars.
2. Minified baseline bytes/chars for JSON/XML.
3. Estimated tokens.
4. Optional Anthropic count-token results.
5. Runtime.
6. Reversibility status.
7. Compression selected or rejected.

---

## Phase 7: Anthropic integration

### Task 7.1: Add optional Anthropic token-count estimator

**Objective:** Replace character proxy with live API counts when credentials exist.

**Files:**
- Modify: `src/kompressor/estimation.py`
- Test: `tests/test_estimation.py`
- Docs: `docs/benchmark-methodology.md`

**Behavior:**
1. Optional dependency group: `anthropic`.
2. Read `ANTHROPIC_API_KEY` from environment.
3. Count raw and optimized messages with the same model.
4. If credentials are missing, skip live tests and fall back to proxy estimate.
5. Clearly label estimates as `anthropic_count_tokens` vs `char_proxy`.

**Verification:**

```bash
python -m pytest tests/test_estimation.py -v
ANTHROPIC_API_KEY=... kompressor analyze logs.json --anthropic-count-tokens --model claude-3-5-sonnet-latest
```

### Task 7.2: Implement local Anthropic-compatible proxy

**Objective:** Provide drop-in request optimization for API users.

**Files:**
- Create: `src/kompressor/proxy.py`
- Test: `tests/test_proxy.py`

**Behavior:**
1. Expose local endpoint like `POST /v1/messages`.
2. Accept Anthropic Messages-style JSON.
3. Compress only large `user` content blocks.
4. Inject or prepend system prompt safely.
5. Forward request to Anthropic with `httpx`.
6. Return upstream response unchanged, plus optional local metrics header.

**Safety:**
1. Do not log raw payloads unless `--log-payloads` is explicitly set.
2. Redact API keys in logs.
3. Provide `--dry-run` mode that never forwards.
4. Add max payload size and timeout controls.

**Verification:**

```bash
kompressor proxy --dry-run --port 8765
curl -s http://localhost:8765/healthz
```

Expected: health endpoint returns status ok. Proxy tests mock Anthropic HTTP calls.

---

## Phase 8: Developer workflows and integrations

### Task 8.1: Git hook integration

**Objective:** Support developers compressing logs/configs before Claude debugging requests.

**Files:**
- Create: `examples/git-hook/pre-claude-context`
- Docs: `docs/developer-cli-integration.md`

**Workflow:**
1. Developer stages or captures diagnostic files.
2. Hook runs `kompressor analyze` and writes a compact context bundle.
3. Hook refuses to include files matching secret patterns unless `--allow-sensitive` is set.

**Acceptance criteria:**
1. Example hook runs locally.
2. Hook never mutates repository files by default.
3. Docs explain installation and rollback.

### Task 8.2: CI/deployment pipeline integration

**Objective:** Let teams publish compressed diagnostic bundles as CI artifacts.

**Files:**
- Create: `examples/ci/github-actions.yml`
- Docs: `docs/ci-integration.md`

**Acceptance criteria:**
1. Example GitHub Action compresses test failure logs.
2. Artifacts contain payload, system prompt, and metrics JSON.
3. Sensitive environment values are redacted.

### Task 8.3: Browser extension feasibility spike

**Objective:** Design the Claude.ai paste interception layer without building it prematurely.

**Files:**
- Create: `docs/browser-extension-design.md`

**Questions to answer:**
1. Can a content script safely intercept paste events in Claude.ai text areas?
2. What user consent UI is required before replacing pasted content?
3. How will compression happen fully locally?
4. How will the extension expose the system prompt injection requirement in a web chat where no API `system` field exists?
5. What are the risks of Claude.ai DOM changes breaking the extension?

**Likely MVP:**
1. User pastes JSON/log payload.
2. Extension detects structure and shows a preview modal.
3. User clicks “Replace with compressed context”.
4. Extension inserts both decompression instructions and dense payload into the chat box.

---

## Phase 9: Security, privacy, and correctness hardening

### Task 9.1: Add secret detection and redaction

**Objective:** Prevent accidental compression/transmission of credentials.

**Files:**
- Create: `src/kompressor/security.py`
- Test: `tests/test_security.py`

**Rules:**
1. Detect common API keys, private keys, bearer tokens, AWS credentials, database URLs.
2. Default behavior: warn and refuse proxy forwarding unless `--allow-sensitive` is explicit.
3. Provide `--redact-secrets` to replace secrets before compression.
4. Ensure redaction runs before pattern hashing so dictionaries do not preserve secrets.

### Task 9.2: Add property-based round-trip tests

**Objective:** Prove codecs are robust across weird strings and structures.

**Files:**
- Modify: `tests/test_json_table_codec.py`
- Modify: `tests/test_json_path_codec.py`

**Use Hypothesis to generate:**
1. Strings with delimiters, escapes, Unicode, and newlines.
2. Lists of dicts with missing keys.
3. Nested JSON structures.

**Verification:**

```bash
python -m pytest tests/test_json_table_codec.py tests/test_json_path_codec.py -v
```

### Task 9.3: Add benchmark truthfulness gates

**Objective:** Prevent marketing claims from exceeding measured evidence.

**Files:**
- Create: `tests/test_benchmark_claims.py`
- Modify: `README.md`
- Modify: `docs/benchmark-methodology.md`

**Acceptance criteria:**
1. README says “up to 40% on measured structured fixtures” only after benchmark artifacts prove it.
2. If benchmark median is below 30%, README must use measured lower wording.
3. Binary/Base122 remains documented as experimental unless live token counts prove savings.

---

## Phase 10: Documentation and release

### Task 10.1: Write architecture docs

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/compression-contract.md`
- Create: `docs/benchmark-methodology.md`

**Content requirements:**
1. Explain why Claude’s tokenizer cannot be modified externally.
2. Explain client-side pre-flight optimization proxy design.
3. Document every codec format and reversibility guarantee.
4. Document estimator limitations.
5. Include privacy/security model.

### Task 10.2: Expand README

**README sections:**
1. What Kompressor does.
2. What it does not do.
3. Quickstart.
4. CLI examples.
5. Python API examples.
6. Anthropic proxy examples.
7. Benchmark results table.
8. Security/privacy notes.
9. Roadmap.

### Task 10.3: Prepare first tagged release

**Steps:**
1. Run full verification.
2. Build package.
3. Install package from wheel in a clean virtualenv.
4. Run smoke CLI.
5. Tag `v0.1.0` only after all checks pass.

**Verification:**

```bash
python -m pytest --cov=kompressor
python -m ruff check .
python -m ruff format --check .
python -m build
python -m venv /tmp/kompressor-smoke
/tmp/kompressor-smoke/bin/python -m pip install dist/*.whl
/tmp/kompressor-smoke/bin/kompressor --help
```

---

## Acceptance Criteria for MVP

The MVP is complete when all of the following are true:

1. `kompressor analyze` works for flat JSON arrays and reports measured estimates.
2. `kompressor compress --format claude` emits a dense payload and matching system prompt.
3. JSON table compression is reversible and property-tested.
4. Engine refuses optimizations that increase estimated token count by default.
5. README includes honest limitations about proxy token estimation.
6. Benchmarks show actual savings on at least three representative fixtures.
7. The brief’s operational verification example is ported into `examples/optimize_logs.py` and runs successfully.
8. Full local verification passes:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

---

## Benchmark Plan

### Fixture categories

1. Flat repeated JSON logs: expected best case for table flattening.
2. Nested JSON traces: expected moderate savings using JSON path codec.
3. XML config: expected moderate-to-high savings if tags repeat.
4. Repeated plaintext logs: expected savings only when templates repeat.
5. Source code: expected low savings; compression may harm readability.
6. Binary bytes: expected no default text-token savings; should be rejected or summarized.

### Metrics to publish

```text
fixture,strategy,reversible,baseline_chars,optimized_chars,baseline_tokens,optimized_tokens,percent_saved,estimator,warnings
```

### Claim policy

1. “Up to 40%” may appear only if at least one representative, non-synthetic fixture proves it.
2. “Typical savings” must use median across the benchmark suite.
3. Any result based on `chars_per_token_proxy` must be labeled “estimated”.
4. Anthropic live count-token results must include model name and date.

---

## Major Risks and Mitigations

### Risk: Character count is a weak proxy for Claude tokens

**Mitigation:** Implement live Anthropic token-count estimator and label proxy results clearly.

### Risk: Dense payload confuses Claude

**Mitigation:** Keep codec markers, concise decompression prompts, and eval tasks that compare Claude answers on raw vs compressed payloads.

### Risk: Delimiter flattening corrupts data

**Mitigation:** Escape rigorously, property-test round trips, and validate decompression inside the engine before returning results.

### Risk: Compression overhead exceeds savings

**Mitigation:** Include system prompt and dictionary overhead in token estimates. Reject expansions by default.

### Risk: Base122/binary mapping increases tokens

**Mitigation:** Disable by default; treat as experimental until measured with live count-token API.

### Risk: Proxy logs sensitive data

**Mitigation:** No raw payload logging by default, redaction before compression, and explicit `--log-payloads` opt-in.

### Risk: Browser extension cannot set true Claude system prompts

**Mitigation:** Browser extension MVP inserts decompression instructions directly into the chat text; API proxy remains the preferred system-prompt path.

---

## Suggested Implementation Order

1. Phase 0: package skeleton.
2. Phase 1: typed models and estimator.
3. Phase 2: JSON table codec and legacy API.
4. Phase 3: engine orchestration and validation.
5. Phase 4: Claude prompt builder.
6. Phase 6: CLI analyze/compress/decompress.
7. Phase 10 docs for MVP.
8. Phase 5 additional codecs.
9. Phase 7 API proxy.
10. Phase 8 integrations.
11. Phase 9 hardening.

---

## Immediate Next Step

Start with Task 0.1 and create the Python package skeleton. Do not implement all codecs at once. The first reviewable PR should contain only project setup, models, estimator, JSON table codec, CLI `analyze`, and enough tests to prove reversible compression and honest savings estimates for the mock log payload from the brief.
