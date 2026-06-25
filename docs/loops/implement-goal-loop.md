# Loop: Implement All Kompressor Slices

## Purpose

Run a bounded implementation loop that repeatedly advances `docs/goals/implement-all-slices.md` until every slice is implemented, verified, documented, and ready for review or release.

This loop is intentionally not an autonomous schedule. Run it when asked to continue implementation. Each iteration must make one review-sized, verified improvement or stop with a clear blocker/no-op result.

## Source Artifacts

Read these at the start of every loop iteration:

1. `docs/goals/implement-all-slices.md`
2. `docs/plans/2026-06-24-claude-context-optimization-engine.md`
3. `git status --short --branch`
4. Current test/verification output relevant to the next slice

## Loop Prompt

> Continue implementing Kompressor from `docs/goals/implement-all-slices.md`. First re-read the goal, plan, and current git status. Select the next highest-value incomplete slice, implement one review-sized TDD change, run focused verification plus the relevant broader checks, update docs/examples/goal status if behavior changed, and preserve unrelated dirty files. Stop only when the slice is verified, no safe progress remains, a command/credential approval is required, or the goal is complete. Do not claim token-savings, reversibility, proxy safety, or release readiness without executable evidence.

## Iteration Cycle

### 1. Observe fresh state

Run:

```bash
git status --short --branch
find . -maxdepth 3 -type f | sort
```

Then read:

```bash
sed -n '1,220p' docs/goals/implement-all-slices.md
sed -n '1,260p' docs/plans/2026-06-24-claude-context-optimization-engine.md
```

If files are large, use targeted reads for the next candidate slice.

Record:

- Current branch
- Dirty/untracked files
- Which files are intentional project work
- Which goal slices appear complete, partial, or untouched
- Last known verification result, if any

### 2. Choose one bounded slice

Pick the first incomplete slice that can be safely advanced in the current repo state.

Selection order:

1. Fix broken verification before adding new features.
2. Complete partially implemented slice before starting a new slice.
3. Prefer earlier foundational slices over later dependent slices.
4. Prefer reversible, testable work over broad docs-only claims.
5. Avoid touching unrelated dirty files.

A single iteration should usually target one of these units:

- One model/estimator behavior plus tests
- One codec behavior plus round-trip tests
- One CLI command path plus tests
- One documentation update tied to implemented behavior
- One security/proxy guardrail plus tests
- One benchmark truthfulness gate plus fixtures

Do not implement multiple large slices in one iteration unless they are inseparable and can still be verified together.

### 3. Create/update loop todos

Use a short checklist for the current iteration:

1. Write or update failing test.
2. Run focused test and confirm failure when practical.
3. Implement minimal code/docs to satisfy the test.
4. Run focused verification.
5. Run relevant broader verification.
6. Update docs/goal status if needed.
7. Inspect diff and report exact files changed.

### 4. Act with TDD discipline

For code slices:

1. Add the smallest failing test that encodes the goal acceptance criterion.
2. Run the focused test.
3. Implement the smallest passing change.
4. Run the focused test again.
5. Refactor only while tests stay green.

For docs/design slices:

1. Update the exact documented contract or design file.
2. Ensure docs do not overclaim implemented behavior.
3. If possible, add a test that enforces the documented contract.

For benchmark/claim slices:

1. Add representative fixture or benchmark case.
2. Run the benchmark or test gate.
3. Update README claims to match measured output only.

### 5. Verify

Use focused checks first, then broader checks appropriate to the slice.

Minimum checks by slice type:

#### Python/model/codec/engine/security changes

```bash
python -m pytest <focused-test-file> -v
python -m pytest
python -m ruff check .
```

#### CLI changes

```bash
python -m pytest tests/test_cli.py -v
python -m pytest
python -m ruff check .
python -m kompressor.cli --help || kompressor --help
```

Use the command that matches the package state. Do not fabricate CLI output if the package is not installable yet.

#### Proxy changes

```bash
python -m pytest tests/test_proxy.py -v
python -m pytest
python -m ruff check .
```

Proxy tests must mock Anthropic calls unless credentials and explicit live verification are available.

#### Documentation-only changes

```bash
git diff --check
```

If docs reference commands that now exist, run those commands.

#### Release-readiness changes

```bash
python -m pytest --cov=kompressor
python -m ruff check .
python -m ruff format --check .
python -m build
python -m venv /tmp/kompressor-smoke
/tmp/kompressor-smoke/bin/python -m pip install dist/*.whl
/tmp/kompressor-smoke/bin/kompressor --help
```

### 6. Record state

At the end of every iteration, update or create an implementation log if useful:

- `docs/loops/implementation-log.md`

Log format:

```markdown
## YYYY-MM-DD — Slice N: short title

Changed:
- path: behavior changed

Verification:
- `command` — PASS/FAIL with short result

Remaining:
- next gap or blocker
```

Do not mark a slice complete in the goal unless its acceptance criteria are actually verified.

### 7. Decide repeat vs stop

Continue to the next iteration only when:

- The current iteration is verified.
- The working tree state is understood.
- The next incomplete slice is clear and safe.
- No approval-gated command, missing credential, or unresolved failing check blocks progress.

Stop with a clear handoff when any of these occur:

1. A command is denied by approval layer.
2. A dependency install, network call, or API credential is required and unavailable.
3. Tests fail and the root cause is not safely fixable in the current iteration.
4. Benchmarks do not support current README/product claims.
5. A codec cannot be made reversible under the documented contract.
6. There is no high-confidence safe next slice.
7. All goal slices satisfy the definition of done.

## Subagent Execution Pattern

Use subagents for large or independent implementation slices. For each slice:

1. Dispatch an implementer with the exact slice text, relevant plan excerpt, files in scope, and required verification commands.
2. After implementation, dispatch an independent spec-compliance reviewer.
3. Fix any spec gaps.
4. Dispatch an independent code-quality reviewer.
5. Fix critical and important findings.
6. The controller must still run final verification locally before marking the slice complete.

Do not let implementers self-approve. Do not mark completion from subagent summaries alone.

## Guardrails

1. Preserve unrelated dirty files.
2. Do not sweep-stage all files unless all dirty files are intentional project work.
3. Do not log or commit secrets.
4. Do not add live Anthropic calls to normal tests.
5. Do not claim exact Claude token counts without Anthropic count-token evidence.
6. Do not claim typical or up-to-40-percent savings without benchmark artifacts.
7. Do not silently accept lossy compression.
8. Do not enable experimental Base122/binary prompt compression by default.
9. Do not leave docs, CLI help, and actual behavior inconsistent.
10. Do not create a cron/scheduled job for this loop unless explicitly requested.

## Completion Gate

The loop is complete only when `docs/goals/implement-all-slices.md` definition of done is satisfied and the global verification gate has been run or explicitly blocked with evidence.

Required final evidence:

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

If `ANTHROPIC_API_KEY` is available, run one live count-token verification and record model/date. If it is not available, state that live token counting was not run.

## First Loop Iteration Target

Start with the first reviewable milestone from the goal:

1. Slice 0 foundation
2. Slice 1 models and estimation
3. Slice 2 JSON table codec and legacy API
4. Slice 3 engine orchestration and validation
5. Slice 4 Claude prompt contract
6. Enough of Slice 6 to run:

```bash
kompressor analyze tests/fixtures/logs.json
kompressor compress tests/fixtures/logs.json --format claude --include-system-prompt
python examples/optimize_logs.py
```

Complete this milestone before expanding into XML, pattern hashing, proxying, browser design, and release hardening.
