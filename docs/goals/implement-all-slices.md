# Goal: Implement All Kompressor Slices

## Mission

Implement every slice in `docs/plans/2026-06-24-claude-context-optimization-engine.md`, then generalize Kompressor into a verified, documented, release-ready multi-harness LLM Context Optimization Engine.

Kompressor must be a local-first Python toolkit that compresses large structured context before it is sent to LLM providers or agent harnesses, including Claude, OpenAI, Gemini, and Hermes, while preserving meaning, measuring savings honestly, and refusing unsafe or misleading optimizations by default.

## Source of Truth

Primary implementation plan:

- `docs/plans/2026-06-24-claude-context-optimization-engine.md`

The implementer must follow that plan slice-by-slice. If implementation discovers that a slice is outdated, incomplete, unsafe, or technically wrong, update the plan and this goal before continuing.

## Required End State

The repository must contain a working Python package with:

1. Core package skeleton and project tooling.
2. Typed models for optimization results, token stats, configuration, and codec metadata.
3. Token and cost estimation with explicit estimator labels.
4. Reversible JSON table compression.
5. JSON path compression for nested JSON.
6. XML path compression for XML payloads.
7. Repeating-pattern compression for logs and repeated text.
8. Binary handling that is safe by default and treats Base122-style dense encodings as experimental until measured.
9. Provider-neutral decompression prompt generation.
10. Engine orchestration that selects the best safe codec and rejects expansions by default.
11. CLI commands: `analyze`, `compress`, `decompress`, `bench`, and `proxy`.
12. Optional provider-specific token-count integrations, starting with Anthropic.
13. Harness adapters for generic text, Claude, OpenAI, Gemini, and Hermes, plus dry-run proxy helpers with safe logging defaults.
14. Developer integration examples for git hooks and CI.
15. Browser-extension feasibility/design documentation.
16. Security scanning and redaction for sensitive values.
17. Property-based round-trip tests for reversible codecs.
18. Benchmark truthfulness gates that prevent unsupported marketing claims.
19. Complete user and architecture documentation.
20. A clean, verified first-release path.

## Non-Negotiable Product Constraints

1. Do not claim to modify any provider's internal tokenizer.
2. Do not claim exact token savings when only character-proxy estimates were used.
3. Do not claim “30%–40% savings” unless repository benchmark artifacts prove that claim for representative fixtures.
4. Do not silently use lossy compression.
5. Do not choose an optimized payload that is larger than the baseline unless the user explicitly opts in.
6. Do not enable Base122/binary prompt compression by default.
7. Do not log raw user payloads in the proxy unless explicitly configured.
8. Do not transmit suspected secrets by default through the proxy.
9. Do not ship a codec as reversible unless round-trip tests and engine validation prove it.
10. Do not leave CLI, docs, and examples inconsistent with implemented behavior.

## Implementation Slices

### Slice 0: Foundation

Status: Verified complete on 2026-06-24. See `docs/loops/implementation-log.md` for command output summary.

Implement the package skeleton and development tooling.

Deliverables:

- `pyproject.toml`
- `src/kompressor/__init__.py`
- `tests/conftest.py`
- Updated `README.md`
- Working editable install
- Passing initial `pytest` and `ruff` checks

Acceptance:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
```

### Slice 1: Models and estimation

Status: Verified complete on 2026-06-24. Models, estimators, and focused tests are implemented.

Implement typed contracts and deterministic token/cost estimation.

Deliverables:

- `src/kompressor/models.py`
- `src/kompressor/estimation.py`
- `tests/test_models.py`
- `tests/test_estimation.py`

Acceptance:

- Model defaults instantiate successfully.
- Invalid cost/token settings fail validation.
- Character-proxy estimator labels itself clearly.
- Cost math is covered by tests.
- Expansion cases are represented honestly as negative savings or warnings.

### Slice 2: JSON table codec and legacy API

Status: Verified complete on 2026-06-24. JSON table codec, property tests, and legacy API are implemented.

Implement the high-value flat JSON compression path and preserve the user-facing API from the project brief.

Deliverables:

- `src/kompressor/codecs/base.py`
- `src/kompressor/codecs/json_table.py`
- `src/kompressor/legacy.py` or equivalent public export
- `tests/test_json_table_codec.py`
- `tests/test_legacy_api.py`

Acceptance:

- Flat list-of-dict payloads compress to delimited tables.
- Delimiters, backslashes, Unicode, and newlines round-trip correctly.
- Missing keys have a documented and tested policy.
- The brief's mock log payload example runs successfully.
- The implementation fixes the invalid `import osimport json` sample from the brief.

### Slice 3: Engine orchestration and validation

Status: Verified complete on 2026-06-24. Engine selection, validation, and safe fallback tests are implemented.

Implement strategy selection, savings comparison, and decompression validation.

Deliverables:

- `src/kompressor/engine.py`
- `tests/test_engine.py`

Acceptance:

- JSON arrays route to `json_table`.
- Small payloads can be skipped by threshold.
- Invalid or unsupported payloads return `kind="none"` safely.
- Reversible codecs are decompressed and compared before the result is accepted.
- Codecs that expand the payload are rejected by default.

### Slice 4: Provider-neutral prompt contract

Status: Verified complete on 2026-06-24. Prompt builder, tests, and compression contract docs are implemented.

Implement codec-specific decompression prompt generation that can be packaged for multiple harnesses.

Deliverables:

- `src/kompressor/prompts.py`
- `tests/test_prompts.py`
- `docs/compression-contract.md`

Acceptance:

- Prompt includes stable codec markers.
- JSON table prompt explains header row, delimiter, escaping, and row mapping.
- Pattern hashing prompt explains dictionary expansion.
- Prompt supports minimal, standard, and debug variants.
- Snapshot or equivalent tests prevent accidental prompt drift.

### Slice 5: Additional codecs

Status: Verified complete on 2026-06-24. JSON path, XML path, pattern hash, binary codec, fixtures, and tests are implemented.

Implement non-table compression paths.

Deliverables:

- `src/kompressor/codecs/json_path.py`
- `src/kompressor/codecs/xml_path.py`
- `src/kompressor/codecs/pattern_hash.py`
- `src/kompressor/codecs/binary.py`
- Matching tests and fixtures

Acceptance:

- Nested JSON round-trips through path/value representation.
- XML hierarchy, text, attributes, and sibling order are preserved or warnings document what is not preserved.
- Pattern hashing compresses repeated lines and refuses mostly unique text.
- Binary handling is safe by default and does not imply token savings without evidence.

### Slice 6: CLI

Status: Verified complete on 2026-06-24. analyze/compress/decompress/bench/proxy commands and CLI tests are implemented.

Implement user-facing command-line workflows.

Deliverables:

- `src/kompressor/cli.py`
- `tests/test_cli.py`

Commands:

- `kompressor analyze`
- `kompressor compress`
- `kompressor decompress`
- `kompressor bench`
- `kompressor proxy` entrypoint or stub wired to the proxy slice

Acceptance:

- Valid fixture inputs exit 0.
- Bad paths or invalid options exit non-zero with useful errors.
- `--json` output is machine-readable.
- `compress --harness hermes`, `--harness openai`, `--harness gemini`, and backward-compatible `--format claude` emit usable prompt+payload bundles.
- `decompress --compare-original` can prove round-trip equivalence.
- `bench` writes repeatable CSV/Markdown/JSON metrics.

### Slice 7: Anthropic integration and proxy

Status: Verified complete on 2026-06-24. Optional Anthropic estimator and dry-run proxy helpers/tests are implemented; live token counting was not run because ANTHROPIC_API_KEY is absent.

Implement optional live token counting and local proxy behavior.

Deliverables:

- Anthropic estimator in `src/kompressor/estimation.py`
- `src/kompressor/proxy.py`
- `tests/test_proxy.py`
- Proxy documentation

Acceptance:

- Missing `ANTHROPIC_API_KEY` skips or falls back cleanly.
- Live count-token mode labels model name and estimator source.
- Proxy exposes a health endpoint.
- Proxy dry-run never forwards requests.
- Proxy redacts keys in logs.
- Proxy compresses only eligible user content blocks.
- Tests mock upstream Anthropic calls; no live API is required for normal CI.

### Slice 8: Developer integrations

Status: Verified complete on 2026-06-24. Git-hook, CI example, and browser-extension design docs are implemented.

Add examples for real workflows without making them mandatory.

Deliverables:

- `examples/git-hook/pre-claude-context`
- `examples/ci/github-actions.yml`
- `docs/developer-cli-integration.md`
- `docs/ci-integration.md`
- `docs/browser-extension-design.md`

Acceptance:

- Git-hook example runs locally and does not mutate repository files by default.
- CI example compresses diagnostic artifacts and writes metrics.
- Browser extension doc honestly explains the limitation that Claude.ai web chat cannot set a true API `system` field.

### Slice 9: Security and correctness hardening

Status: Verified complete on 2026-06-24. Secret detection/redaction, proxy fail-closed tests, property tests, and benchmark claim gates are implemented.

Add secret detection, redaction, property-based testing, and benchmark claim enforcement.

Deliverables:

- `src/kompressor/security.py`
- `tests/test_security.py`
- Hypothesis tests for JSON codecs
- `tests/test_benchmark_claims.py`
- Updated README and benchmark docs

Acceptance:

- Common secrets are detected.
- Proxy refuses suspected secrets unless explicitly overridden.
- `--redact-secrets` redacts before compression.
- Property tests cover delimiters, escapes, Unicode, newlines, missing keys, and nested structures.
- README claims are tied to benchmark evidence.

### Slice 10: Documentation and release readiness

Status: Verified complete on 2026-06-24. Architecture, benchmark, release, README, examples, wheel build, smoke install, and benchmark artifacts are verified.

Make the project usable and reviewable.

Deliverables:

- `docs/architecture.md`
- `docs/benchmark-methodology.md`
- Complete `README.md`
- `examples/optimize_logs.py`
- Release checklist

Acceptance:

- Docs explain what Kompressor does and does not do.
- Docs explain provider tokenizer limitations and harness packaging boundaries.
- Docs explain all codec formats and reversibility guarantees.
- Docs include privacy/security model.
- Example from the project brief runs successfully.
- Package builds and installs from a wheel in a clean virtualenv.

## Global Verification Gate

Before calling the implementation complete, run and record the exact output of:

```bash
python -m pytest --cov=kompressor
python -m ruff check .
python -m ruff format --check .
python -m build
python -m venv /tmp/kompressor-smoke
/tmp/kompressor-smoke/bin/python -m pip install dist/*.whl
/tmp/kompressor-smoke/bin/kompressor --help
kompressor bench tests/fixtures --format markdown --output docs/benchmarks.md
```

If `ANTHROPIC_API_KEY` is available, also run one live token-count verification and record the model/date in the benchmark output. If it is not available, explicitly state that live token counts were not run.

## Definition of Done

All slices are done only when:

1. Every deliverable listed above exists.
2. All tests pass locally.
3. CLI commands work from an installed wheel.
4. Reversible codecs have round-trip tests.
5. Benchmark artifacts exist and match README claims.
6. Security defaults are fail-closed.
7. The proxy has dry-run coverage.
8. Documentation matches actual behavior.
9. `git status --short` contains only intentional project files.
10. The repository is ready for a first review PR or `v0.1.0` release tag.

## Recommended Execution Discipline

Implement in small verified slices. For each slice:

1. Inspect current repository state.
2. Write or update tests first where practical.
3. Implement the smallest code needed.
4. Run focused tests.
5. Run broader project checks when the slice touches shared behavior.
6. Update docs/examples if behavior changed.
7. Record any deviations from the plan.
8. Commit only intentional files if asked to package the work.

## Stop Conditions

Stop and ask for direction if:

1. A required side-effecting dependency install or network call is denied.
2. Anthropic API behavior cannot be verified without credentials and the slice requires live verification.
3. Benchmarks fail to support expected savings and README/product claims need repositioning.
4. A codec cannot be made reversible without materially changing the payload contract.
5. Browser-extension implementation is requested before the core engine is stable.

## First Implementation Target

The first reviewable implementation milestone should include slices 0 through 4 plus enough of slice 6 to run:

```bash
kompressor analyze tests/fixtures/logs.json
kompressor compress tests/fixtures/logs.json --harness hermes
kompressor compress tests/fixtures/logs.json --format claude --include-system-prompt
python examples/optimize_logs.py
```

This milestone should prove the core product loop before expanding into XML, pattern hashing, proxying, browser design, and release hardening.


## Multi-Harness Generalization Addendum

Status: Verified complete on 2026-06-24. Kompressor now treats Claude as one harness adapter, not the product boundary.

Deliverables:

- `src/kompressor/harnesses/base.py`
- `src/kompressor/harnesses/generic.py`
- `src/kompressor/harnesses/claude.py`
- `src/kompressor/harnesses/openai.py`
- `src/kompressor/harnesses/gemini.py`
- `src/kompressor/harnesses/hermes.py`
- `tests/test_harnesses.py`
- `docs/harnesses.md`
- README and architecture updates describing provider-neutral compression and harness-specific packaging.

Acceptance:

- Core codecs and engine remain provider-neutral.
- `kompressor compress --harness generic` emits a plain prompt bundle.
- `kompressor compress --harness claude` packages Anthropic-style `system` plus user content.
- `kompressor compress --harness openai --json` packages developer/user messages.
- `kompressor compress --harness gemini --json` packages Gemini-style `system_instruction` plus contents.
- `kompressor compress --harness hermes` emits task-local Hermes parsing rules and payload.
- Backward-compatible `--format claude --include-system-prompt` still works.


## Transparent Plugin Addendum

Status: Verified complete on 2026-06-24. Every supported harness now has a Kompressor plugin entrypoint in addition to a harness adapter.

Supported plugins:

- generic: `kompressor.plugins.builtin:GenericKompressorPlugin`
- Claude/Anthropic: `kompressor.plugins.builtin:ClaudeKompressorPlugin`
- OpenAI: `kompressor.plugins.builtin:OpenAIKompressorPlugin`
- Gemini: `kompressor.plugins.builtin:GeminiKompressorPlugin`
- Hermes: `kompressor.plugins.builtin:HermesKompressorPlugin`
- Codex: `kompressor.plugins.builtin:CodexKompressorPlugin`

Acceptance:

- `kompressor plugin list` enumerates all canonical plugins.
- `kompressor plugin show <harness>` prints hook names and install guidance.
- `kompressor plugin preflight <harness> <file>` runs a real pre-send compression hook.
- Plugins expose `prepare_user_input`, `prepare_tool_output`, and `prepare_request` surfaces for native harness integration.
- Secret detection remains fail-closed unless redaction or explicit override is selected.
- Codex is supported as both a harness adapter and plugin.
