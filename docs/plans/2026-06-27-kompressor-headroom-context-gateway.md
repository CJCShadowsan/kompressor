# Kompressor Context Gateway Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn Kompressor from a verified codec engine into a Headroom-like local context gateway while preserving Kompressor's stricter reversibility, traceability, and benchmark discipline.

**Architecture:** Keep Kompressor's provider-neutral codecs as the core engine. Add a thin gateway layer that rewrites OpenAI/Anthropic-compatible requests, stores originals in a hash-addressed local content store, exposes retrieval/statistics endpoints and optional MCP tools, and supports agent wrappers without mutating transcripts. Product ergonomics come from the gateway; correctness claims come from codec round-trip tests, request-rewrite proof telemetry, and eval artifacts.

**Tech Stack:** Python 3.10+, stdlib HTTP server initially, httpx, Typer, Pydantic/dataclasses, pytest, existing Kompressor codecs/harness adapters, optional MCP packaging later.

---

## Executive design

The target is not to clone Headroom feature-for-feature. The target is a Kompressor-native architecture that borrows the useful product shape:

1. Local proxy/gateway for drop-in usage.
2. Content routing over structured, code, log, markdown, HTML, and blob payloads.
3. Retrieval-backed externalization for large originals.
4. Cross-session local cache/stats.
5. Agent wrapper commands.
6. Optional output shaping, behind explicit flags.
7. Reproducible proof that the gateway rewrites real in-session requests and preserves answer quality.

Non-negotiables:

- Provider-neutral core stays separate from harness/proxy code.
- Prompt-readable, externalized-reversible, local-decode-reversible, and lossy analytical modes remain distinct.
- No silent lossy compression in default mode.
- No raw secret logging. Redact or fail closed before storing/compressing.
- Do not mutate durable chat history unless explicitly requested.
- No marketing savings claim without benchmark artifact and estimator label.

---

## Current repository anchors

Observed live files:

- Core engine: `src/kompressor/engine.py`
- Config/result contracts: `src/kompressor/models.py`
- Codec interface: `src/kompressor/codecs/base.py`
- Advanced codecs: `src/kompressor/codecs/advanced.py`
- Harness plugin base: `src/kompressor/plugins/base.py`
- Anthropic request rewrite: `src/kompressor/proxy.py`
- Anthropic HTTP proxy: `src/kompressor/anthropic_proxy.py`
- CLI: `src/kompressor/cli.py`
- Hermes plugin installer: `src/kompressor/hermes_install/`
- Existing proxy tests: `tests/test_proxy.py`, `tests/test_anthropic_proxy.py`
- Existing codec/engine tests: `tests/test_engine.py`, `tests/test_lossless_ext_codecs.py`, `tests/test_advanced_codecs.py`, `tests/test_reversible_research_codecs.py`

Current gap:

- Kompressor can compress and rewrite Anthropic-style messages, but it does not yet have a general gateway abstraction, local content-addressed store, retrieval endpoint/tool, OpenAI-compatible proxy path, cache/stats dashboard primitives, cache-aligned stable prompt insertion, agent wrapper surface, or gateway-level proof/eval harness.

---

## Target architecture

```text
agent/app/client
  │
  │ OpenAI-compatible / Anthropic-compatible request
  ▼
Kompressor Gateway
  ├─ request shape detector
  ├─ secret gate / redaction
  ├─ message + tool-result extractor
  ├─ content router
  │    └─ KompressorEngine / codec registry
  ├─ original content store
  │    ├─ content-addressed blobs
  │    ├─ metadata index
  │    └─ optional TTL/prune
  ├─ retrieval reference injector
  ├─ parsing/retrieval instructions injector
  ├─ telemetry/stats recorder
  └─ upstream provider proxy
       │
       ▼
LLM provider

Optional side channels:
  - `kompressor gateway stats`
  - `GET /v1/kompressor/stats`
  - `GET /v1/kompressor/retrieve/{sha256}`
  - MCP tools: `kompressor_retrieve`, `kompressor_stats`, `kompressor_compress`
```

Default compression policy:

```text
mode = strict
- prefer prompt-readable reversible codecs
- allow externalized reversible refs only when retrieval endpoint/tool is available in the same integration
- disable local-decode transport unless the runtime proves it will inflate before model reasoning
- disable lossy analytical codecs unless `--allow-lossy` is set
```

---

## Data contracts to add

Create `src/kompressor/gateway/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GatewayMode = Literal["strict", "externalized", "local_decode", "lossy_allowed"]
RequestFormat = Literal["anthropic", "openai", "unknown"]
ContentSource = Literal["user_text", "tool_result", "developer_text", "system_text"]

@dataclass(frozen=True)
class GatewayConfig:
    mode: GatewayMode = "strict"
    threshold_chars: int = 512
    store_dir: str | None = None
    allow_sensitive: bool = False
    redact: bool = False
    allow_lossy: bool = False
    enable_transport_compression: bool = False
    inject_retrieval_instructions: bool = True
    inject_parsing_instructions: bool = True
    stable_instruction_anchor: Literal["end", "beginning"] = "end"

@dataclass(frozen=True)
class StoredOriginal:
    digest: str
    chars: int
    content_type: str
    source: ContentSource
    created_at: str
    preview: str
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class GatewayRewrite:
    path: str
    source: ContentSource
    strategy: str
    original_chars: int
    rewritten_chars: int
    saved_chars: int
    reversible_class: str
    stored_digest: str | None = None
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class GatewayTelemetry:
    request_format: RequestFormat
    rewrite_count: int
    rewrites: tuple[GatewayRewrite, ...]
    warnings: tuple[str, ...]
    system_prompt_added: bool
    retrieval_available: bool
```

Add tests before implementation in `tests/test_gateway_models.py`.

---

## Implementation phases

### Phase 0: Baseline and branch discipline

Objective: Start from clean main and capture current behavior.

Steps:

1. Run:
   ```bash
   cd /Users/ccoates/Documents/kompressor
   git status --short --branch
   git pull --ff-only origin main
   git checkout -b feat/context-gateway
   python -m pytest -q
   ```
2. Expected:
   - clean or only known unrelated dirt before branch
   - tests pass before changes
3. If tests fail on main, stop and record blocker in this plan before implementing.

Acceptance:

- Dedicated branch exists.
- Baseline tests recorded.

---

### Phase 1: Introduce gateway package and typed contracts

Objective: Add provider-neutral gateway contracts without changing existing proxy behavior.

Files:

- Create: `src/kompressor/gateway/__init__.py`
- Create: `src/kompressor/gateway/models.py`
- Create: `tests/test_gateway_models.py`

Tests:

```python
from kompressor.gateway.models import GatewayConfig, GatewayTelemetry


def test_gateway_config_defaults_to_strict_mode():
    config = GatewayConfig()
    assert config.mode == "strict"
    assert config.allow_lossy is False
    assert config.enable_transport_compression is False


def test_gateway_telemetry_is_immutable_tuple_based():
    telemetry = GatewayTelemetry(
        request_format="openai",
        rewrite_count=0,
        rewrites=(),
        warnings=(),
        system_prompt_added=False,
        retrieval_available=False,
    )
    assert telemetry.rewrites == ()
```

Commands:

```bash
python -m pytest tests/test_gateway_models.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway tests/test_gateway_models.py
git commit -m "feat: add gateway data contracts"
```

---

### Phase 2: Add content-addressed original store

Objective: Store originals locally by SHA-256 with metadata, enabling reversible externalization and retrieval.

Files:

- Create: `src/kompressor/gateway/store.py`
- Create: `tests/test_gateway_store.py`

Design:

- Default store path: `~/.kompressor/store` unless config overrides.
- Blob path: `<store>/blobs/sha256/<first2>/<digest>.txt`
- Metadata path: `<store>/index/<digest>.json`
- Write atomically via temp file + rename.
- Refuse to store content with suspected secrets unless `allow_sensitive` or `redact` has already handled it upstream.

Public API:

```python
class OriginalStore:
    def __init__(self, root: Path): ...
    def put_text(self, text: str, *, source: ContentSource, content_type: str, metadata: dict[str, Any] | None = None) -> StoredOriginal: ...
    def get_text(self, digest: str) -> str: ...
    def get_metadata(self, digest: str) -> StoredOriginal: ...
    def has(self, digest: str) -> bool: ...
```

Tests:

```python
def test_store_round_trips_text(tmp_path):
    store = OriginalStore(tmp_path)
    stored = store.put_text("hello", source="user_text", content_type="text/plain")
    assert store.get_text(stored.digest) == "hello"
    assert store.get_metadata(stored.digest).chars == 5


def test_store_dedupes_by_digest(tmp_path):
    store = OriginalStore(tmp_path)
    one = store.put_text("same", source="user_text", content_type="text/plain")
    two = store.put_text("same", source="tool_result", content_type="text/plain")
    assert one.digest == two.digest
```

Commands:

```bash
python -m pytest tests/test_gateway_store.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/store.py tests/test_gateway_store.py
git commit -m "feat: add content-addressed original store"
```

---

### Phase 3: Add reversible-class classification

Objective: Make codec outputs explicitly classifiable at gateway policy boundaries.

Files:

- Modify: `src/kompressor/models.py`
- Modify: `src/kompressor/engine.py`
- Create: `tests/test_reversibility_classes.py`

Design:

Add a `reversibility_class` field to `OptimizationResult`, defaulting from metadata when available:

```python
ReversibilityClass = Literal[
    "none",
    "prompt_readable_reversible",
    "externalized_reversible",
    "local_decode_reversible",
    "lossy_analytical",
]
```

Mapping:

- reversible codec, not sidecar/session/transport/domain-table deflate: `prompt_readable_reversible`
- `sidecar_ref`, `session_delta`, `blob_ref`: `externalized_reversible`
- `transport_deflate`: `local_decode_reversible`
- non-reversible analytical codecs: `lossy_analytical`
- no-op: `none`

Tests:

```python
def test_schema_rows_is_prompt_readable_reversible():
    rows = [{"a": i, "b": "x"} for i in range(5)]
    result = KompressorEngine().optimize(rows)
    assert result.kind == "schema_rows"
    assert result.reversibility_class == "prompt_readable_reversible"


def test_transport_deflate_is_local_decode_when_enabled():
    text = "abcdef" * 1000
    result = KompressorEngine(KompressorConfig(enable_transport_compression=True, reversible_only=True)).optimize(text)
    if result.kind == "transport_deflate":
        assert result.reversibility_class == "local_decode_reversible"
```

Compatibility:

- Keep `OptimizationResult.to_dict()` backward-compatible by including the new field but not changing existing names.
- If too invasive, implement classification in `src/kompressor/gateway/policy.py` first and defer model field to a later commit.

Commands:

```bash
python -m pytest tests/test_reversibility_classes.py -q
python -m pytest tests/test_engine.py tests/test_models.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/models.py src/kompressor/engine.py tests/test_reversibility_classes.py
git commit -m "feat: classify optimization reversibility modes"
```

---

### Phase 4: Add gateway policy engine

Objective: Enforce strict/default policy independently from individual codecs.

Files:

- Create: `src/kompressor/gateway/policy.py`
- Create: `tests/test_gateway_policy.py`

Policy rules:

- `strict`: allow only prompt-readable reversible and no-op.
- `externalized`: allow prompt-readable + externalized, but require store/retrieval availability.
- `local_decode`: allow local-decode only if the integration declares runtime decode support.
- `lossy_allowed`: allow lossy analytical only when `allow_lossy=True`.

Public API:

```python
@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def decide_gateway_use(result: OptimizationResult, config: GatewayConfig, *, retrieval_available: bool, local_decode_available: bool) -> PolicyDecision: ...
```

Tests:

```python
def test_strict_rejects_lossy_result(fake_lossy_result): ...
def test_externalized_requires_retrieval_available(fake_sidecar_result): ...
def test_local_decode_requires_runtime_support(fake_transport_result): ...
```

Commands:

```bash
python -m pytest tests/test_gateway_policy.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/policy.py tests/test_gateway_policy.py
git commit -m "feat: enforce gateway compression policy"
```

---

### Phase 5: Generalize request shape detection

Objective: Support both Anthropic and OpenAI-compatible request shapes in a shared gateway rewriter.

Files:

- Create: `src/kompressor/gateway/shapes.py`
- Create: `tests/test_gateway_shapes.py`

Request shapes:

Anthropic:

```json
{
  "system": "...",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "user", "content": [{"type":"text","text":"..."}, {"type":"tool_result","content":"..."}]}
  ]
}
```

OpenAI-compatible:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "tool", "content": "..."},
    {"role": "user", "content": [{"type":"text","text":"..."}]}
  ]
}
```

API:

```python
def detect_request_format(request: dict[str, Any]) -> RequestFormat: ...
def iter_text_targets(request: dict[str, Any], request_format: RequestFormat) -> Iterable[TextTarget]: ...
def replace_text_target(request: dict[str, Any], target: TextTarget, text: str) -> dict[str, Any]: ...
def inject_instructions(request: dict[str, Any], request_format: RequestFormat, text: str, *, anchor: str = "end") -> tuple[dict[str, Any], bool]: ...
```

Pitfalls:

- Do not rewrite assistant tool-call envelopes or tool schemas.
- Do not rewrite images/audio/document binary blocks.
- Preserve role order and all unknown fields.
- System/developer compression should be disabled by default; focus on user/tool text.

Commands:

```bash
python -m pytest tests/test_gateway_shapes.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/shapes.py tests/test_gateway_shapes.py
git commit -m "feat: add gateway request shape adapters"
```

---

### Phase 6: Implement GatewayRewriter

Objective: Replace ad-hoc proxy rewrite logic with a reusable gateway rewriter.

Files:

- Create: `src/kompressor/gateway/rewriter.py`
- Modify: `src/kompressor/proxy.py` to call the gateway for Anthropic requests while preserving existing public function names.
- Create: `tests/test_gateway_rewriter.py`
- Update: `tests/test_proxy.py`

API:

```python
class GatewayRewriter:
    def __init__(self, config: GatewayConfig, store: OriginalStore | None = None): ...
    def rewrite_request(self, request: dict[str, Any]) -> tuple[dict[str, Any], GatewayTelemetry]: ...
```

Implementation outline:

1. Detect request format.
2. Deep-copy request.
3. Iterate text targets.
4. Skip already compressed payloads.
5. Apply secret gate/redaction.
6. Store original if mode requires retrieval or if configured for audit metadata.
7. Run `KompressorEngine` with config-derived settings.
8. Ask `policy.decide_gateway_use` whether to use result.
9. Replace target text only when allowed and result saves tokens/chars.
10. Inject instructions once per request.
11. Return telemetry with no raw payloads.

Instruction shape:

```text
KOMPRESSOR_GATEWAY_INSTRUCTIONS
Some context blocks are compact Kompressor payloads. Parse them according to their marker.
If a block contains `kompressor://sha256/<digest>` and you need exact original text, call the configured retrieval tool or endpoint for that digest.
Do not invent content that was externalized but not retrieved.
```

Tests:

```python
def test_gateway_rewrites_openai_user_text_and_preserves_metadata(): ...
def test_gateway_rewrites_anthropic_tool_result_text(): ...
def test_gateway_does_not_rewrite_tool_schema(): ...
def test_gateway_stores_original_without_exposing_raw_in_telemetry(tmp_path): ...
def test_gateway_rejects_lossy_in_strict_mode(): ...
```

Commands:

```bash
python -m pytest tests/test_gateway_rewriter.py tests/test_proxy.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/rewriter.py src/kompressor/proxy.py tests/test_gateway_rewriter.py tests/test_proxy.py
git commit -m "feat: add reusable gateway request rewriter"
```

---

### Phase 7: Add OpenAI-compatible gateway proxy

Objective: Add a proxy path for `/v1/chat/completions` and `/v1/responses` while keeping Anthropic support.

Files:

- Create: `src/kompressor/gateway/http.py`
- Modify: `src/kompressor/anthropic_proxy.py` or deprecate it behind the shared HTTP gateway.
- Modify: `src/kompressor/cli.py`
- Create: `tests/test_gateway_http.py`

Design:

- Keep stdlib `ThreadingHTTPServer` for minimal dependencies now.
- Support:
  - `GET /healthz`
  - `GET /v1/kompressor/stats`
  - `GET /v1/kompressor/retrieve/{digest}`
  - `POST /v1/messages` for Anthropic
  - `POST /v1/chat/completions` for OpenAI-compatible clients
  - `POST /v1/responses` for newer OpenAI-compatible clients if shape is messages/input-like
- Forward all other paths unchanged.

CLI:

```bash
kompressor gateway serve \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream https://api.openai.com \
  --format auto \
  --mode strict \
  --store-dir ~/.kompressor/store
```

Tests:

- Use a local fake upstream HTTP server.
- Assert upstream receives rewritten body and `x-kompressor-rewrite-count`.
- Assert retrieve endpoint returns exact original by digest.
- Assert stats endpoint includes counts, not raw text.

Commands:

```bash
python -m pytest tests/test_gateway_http.py -q
python -m pytest tests/test_anthropic_proxy.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/http.py src/kompressor/cli.py tests/test_gateway_http.py
git commit -m "feat: serve multi-provider context gateway"
```

---

### Phase 8: Add stats/telemetry store

Objective: Track savings and decisions locally without recording raw payloads.

Files:

- Create: `src/kompressor/gateway/stats.py`
- Modify: `src/kompressor/gateway/http.py`
- Create: `tests/test_gateway_stats.py`

Stats fields:

```json
{
  "requests": 12,
  "rewrites": 31,
  "baseline_chars": 123456,
  "rewritten_chars": 45678,
  "saved_chars": 77778,
  "by_strategy": {"schema_rows": {"count": 10, "saved_chars": 10000}},
  "by_reversibility_class": {"prompt_readable_reversible": {"count": 10}},
  "policy_rejections": {"lossy_not_allowed": 5},
  "estimator": "chars, not provider billing"
}
```

Rules:

- Never store raw text.
- Store request IDs only if generated locally or provided safely.
- Expose JSON via CLI and HTTP.

CLI:

```bash
kompressor gateway stats --store-dir ~/.kompressor/store --json
kompressor gateway retrieve <digest> --store-dir ~/.kompressor/store
```

Commands:

```bash
python -m pytest tests/test_gateway_stats.py tests/test_gateway_http.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/stats.py src/kompressor/gateway/http.py src/kompressor/cli.py tests/test_gateway_stats.py
git commit -m "feat: add gateway stats and retrieval commands"
```

---

### Phase 9: Add MCP retrieval/stats tools

Objective: Let models retrieve exact originals through a tool instead of relying only on HTTP endpoints.

Files:

- Create: `src/kompressor/mcp_server.py`
- Modify: `pyproject.toml`
- Create: `tests/test_mcp_server.py`
- Docs: `docs/mcp-integration.md`

CLI/script:

```toml
[project.scripts]
kompressor = "kompressor.cli:app"
kompressor-mcp = "kompressor.mcp_server:main"
```

Tools:

- `kompressor_retrieve(digest: str) -> {digest, content, metadata}`
- `kompressor_stats() -> stats json`
- `kompressor_compress(text: str, mode: str = "strict") -> compact payload + telemetry`

Dependency decision:

- Prefer no mandatory MCP dependency. Add optional extra:
  ```toml
  [project.optional-dependencies]
  mcp = ["mcp>=1.0"]
  ```
- If MCP dependency is absent, `kompressor-mcp` prints a clear install hint and exits non-zero.

Tests:

- Unit-test tool functions directly without starting a real MCP client.
- Add optional integration test skipped when `mcp` package is unavailable.

Commands:

```bash
python -m pytest tests/test_mcp_server.py -q
python -m pytest -q
python -m build
```

Commit:

```bash
git add src/kompressor/mcp_server.py docs/mcp-integration.md pyproject.toml tests/test_mcp_server.py
git commit -m "feat: expose Kompressor retrieval over MCP"
```

---

### Phase 10: Add agent wrappers

Objective: Provide Headroom-style ergonomics without mixing wrapper logic into core compression.

Files:

- Create: `src/kompressor/gateway/wrap.py`
- Modify: `src/kompressor/cli.py`
- Create: `tests/test_gateway_wrap.py`
- Docs: `docs/gateway-wrappers.md`

CLI:

```bash
kompressor wrap claude -- --model sonnet
kompressor wrap codex -- --model gpt-5.1-codex
kompressor wrap aider -- --model openai/gpt-4.1
kompressor wrap cursor --print-settings
```

Behavior:

- Start gateway on a free loopback port unless `--reuse` finds a compatible gateway.
- Set provider base URL env vars for child process only.
- Do not mutate global shell config by default.
- Print exact env/settings for Cursor rather than trying to modify Cursor app config.
- Shutdown gateway when child exits unless `--daemon` is set.

Tests:

- Test generated child environment for each supported wrapper.
- Test `--print-settings` does not launch child process.
- Test invalid agent gives actionable error.

Commands:

```bash
python -m pytest tests/test_gateway_wrap.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/wrap.py src/kompressor/cli.py docs/gateway-wrappers.md tests/test_gateway_wrap.py
git commit -m "feat: add gateway agent wrappers"
```

---

### Phase 11: Add cache-aligned instruction injection

Objective: Minimize provider KV-cache churn caused by changing compression metadata.

Files:

- Modify: `src/kompressor/gateway/shapes.py`
- Modify: `src/kompressor/gateway/rewriter.py`
- Create: `tests/test_gateway_cache_alignment.py`

Rules:

- Stable global instructions go at a deterministic position.
- Per-request volatile retrieval digests go near the compressed block or at the end, not ahead of stable system/developer prompts.
- Never prepend changing telemetry to the system prompt.

Test:

```python
def test_stable_instruction_prefix_does_not_change_when_digest_changes():
    # Two requests with different content should share the same injected instruction prefix.
    ...
```

Commands:

```bash
python -m pytest tests/test_gateway_cache_alignment.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/shapes.py src/kompressor/gateway/rewriter.py tests/test_gateway_cache_alignment.py
git commit -m "feat: stabilize gateway instruction injection"
```

---

### Phase 12: Add explicit output shaping as opt-in

Objective: Borrow Headroom's useful output-token controls without default behavioral surprises.

Files:

- Create: `src/kompressor/gateway/output_shaping.py`
- Modify: `src/kompressor/gateway/rewriter.py`
- Modify: `src/kompressor/gateway/models.py`
- Create: `tests/test_output_shaping.py`

Config:

```python
output_shaping: bool = False
verbosity_hint: Literal["none", "terse", "normal"] = "none"
effort_routing: bool = False
```

Rules:

- Off by default.
- Append stable terse-output hint only when enabled.
- For providers with explicit reasoning/effort fields, only lower effort on tool-continuation requests when configured.
- Do not claim measured output savings without control/holdout instrumentation.

Tests:

- Off means request unchanged.
- On injects stable instruction.
- Effort routing changes only supported request fields.

Commands:

```bash
python -m pytest tests/test_output_shaping.py -q
python -m pytest -q
```

Commit:

```bash
git add src/kompressor/gateway/output_shaping.py src/kompressor/gateway/rewriter.py src/kompressor/gateway/models.py tests/test_output_shaping.py
git commit -m "feat: add opt-in output shaping"
```

---

### Phase 13: Build proof harness

Objective: Prove the gateway actually rewrites raw in-session requests and answer quality is preserved on small reproducible tasks.

Files:

- Create: `scripts/gateway_proof.py`
- Create: `tests/test_gateway_proof_script.py`
- Docs: `docs/gateway-proof.md`

Proof cases:

1. Structured JSON rows: ask for count/filter value that survives `schema_rows`.
2. Logs: ask for first/last error template using reversible log templates or strict mode fallback.
3. Code snippet: ask for symbol/import summary using strict reversible mode where possible; lossy mode must be labeled if used.
4. Externalized large blob: ask model to retrieve exact text through endpoint/tool; if no live model/tool call, script proves retrieval endpoint and marks semantic model proof skipped.

Proof output JSON:

```json
{
  "gateway_rewrite_proof": true,
  "raw_input_sent_to_gateway": true,
  "upstream_received_rewritten": true,
  "rewrite_count": 1,
  "retrieval_round_trip": true,
  "semantic_model_check": "skipped_no_api_key|pass|fail",
  "claims_supported": [...],
  "claims_not_supported": [...]
}
```

Commands:

```bash
python scripts/gateway_proof.py --offline --out artifacts/proof/gateway-offline.json
python -m pytest tests/test_gateway_proof_script.py -q
python -m pytest -q
```

Commit:

```bash
git add scripts/gateway_proof.py docs/gateway-proof.md tests/test_gateway_proof_script.py
git commit -m "test: add gateway proof harness"
```

---

### Phase 14: Benchmark gateway workloads

Objective: Produce honest Headroom-comparable but Kompressor-labeled benchmark artifacts.

Files:

- Create: `scripts/gateway_benchmark.py`
- Create: `tests/test_gateway_benchmark.py`
- Docs: `docs/gateway-benchmarks.md`
- Artifacts: `artifacts/bench/<date>-gateway/`

Workloads:

- Code search results
- SRE incident logs
- GitHub issue triage JSON
- Codebase exploration snippets
- RAG chunks / markdown docs
- Tool outputs with mixed JSON/text

Metrics:

- baseline chars
- rewritten chars
- local token estimate when tiktoken available
- strategy distribution
- reversibility class distribution
- policy rejection counts
- retrieval references emitted
- exact round-trip count for all reversible payloads
- negative-savings count

Do not report provider billing savings unless actual provider usage metadata is collected.

Commands:

```bash
python scripts/gateway_benchmark.py --out artifacts/bench/$(date +%F)-gateway
python -m pytest tests/test_gateway_benchmark.py -q
python -m pytest -q
```

Commit:

```bash
git add scripts/gateway_benchmark.py docs/gateway-benchmarks.md tests/test_gateway_benchmark.py artifacts/bench/<date>-gateway
git commit -m "bench: add gateway workload benchmark"
```

---

### Phase 15: Documentation and README positioning

Objective: Explain the Kompressor + Headroom-style synthesis without overclaiming.

Files:

- Modify: `README.md`
- Create: `docs/context-gateway.md`
- Create: `docs/comparison-headroom.md`
- Update: `docs/reversible-token-compression-paper.md` only if benchmark artifacts justify new claims.

README sections:

- `Kompressor Gateway`
- `Strict by default`
- `Proxy/wrap/MCP usage`
- `Retrieval-backed originals`
- `Claims and limits`

Positioning language:

```text
Kompressor Gateway gives Kompressor Headroom-like deployment ergonomics while preserving Kompressor's explicit reversibility classes and benchmark discipline. It is not a provider tokenizer replacement and does not claim provider billing savings without provider usage metadata.
```

Commands:

```bash
python -m pytest -q
python -m build
```

Commit:

```bash
git add README.md docs/context-gateway.md docs/comparison-headroom.md docs/reversible-token-compression-paper.md
git commit -m "docs: document Kompressor context gateway"
```

---

### Phase 16: Release-readiness hardening

Objective: Ensure package installs cleanly and gateway commands work from a wheel.

Commands:

```bash
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m pytest -q
python -m build
python -m venv /tmp/kompressor-wheel-smoke
/tmp/kompressor-wheel-smoke/bin/python -m pip install dist/kompressor-*.whl
/tmp/kompressor-wheel-smoke/bin/kompressor --version
/tmp/kompressor-wheel-smoke/bin/kompressor gateway --help
/tmp/kompressor-wheel-smoke/bin/kompressor gateway serve --help
/tmp/kompressor-wheel-smoke/bin/kompressor wrap --help
```

Acceptance:

- All tests pass.
- Wheel install succeeds.
- CLI commands import packaged resources correctly.
- No raw payloads appear in stats/proof artifacts.

Commit:

```bash
git add pyproject.toml README.md docs tests src scripts
 git commit -m "chore: harden gateway release packaging"
```

---

## Acceptance criteria

The feature is done when all are true:

1. `kompressor gateway serve` can proxy Anthropic and OpenAI-compatible requests.
2. Gateway rewrites large user/tool text through KompressorEngine in strict mode by default.
3. Gateway stores originals by digest and exposes retrieval through CLI and HTTP.
4. MCP retrieval/stats tools are available behind an optional dependency.
5. Wrappers exist for at least Claude, Codex, and generic OpenAI-compatible clients.
6. Telemetry reports strategy, size deltas, reversibility class, and policy decisions without raw text.
7. Strict mode never silently uses lossy analytical compression.
8. Local-decode compression is never sent to a model unless the integration proves runtime inflation.
9. Tests cover OpenAI and Anthropic request shapes, tool-result handling, retrieval, policy, stats, wrappers, and cache-aligned instructions.
10. Offline proof demonstrates raw input enters gateway and rewritten input reaches fake upstream.
11. Optional live proof is available when API credentials are present, but absence of credentials does not block offline verification.
12. Benchmark artifacts label estimator source and do not imply provider billing measurements.
13. Wheel smoke install passes.

---

## Risks and mitigations

Risk: Model fails to reason over compact reversible payloads.
Mitigation: Use strict benchmark/eval cases; fallback to externalized retrieval when compact format is not semantically usable.

Risk: Retrieval references make models hallucinate unretrieved details.
Mitigation: Instruction explicitly says not to invent externalized content; proof tasks check retrieval behavior.

Risk: Proxy rewrites provider metadata/tool schemas.
Mitigation: Shape adapters enumerate text targets; tests assert tool schemas and tool-call envelopes are unchanged.

Risk: Secret leakage into store/stats.
Mitigation: Reuse `find_secrets` and `redact_secrets`; no raw payloads in telemetry; fail closed by default.

Risk: Claims drift into marketing language.
Mitigation: Benchmark docs include estimator labels, negative-savings counts, round-trip counts, and unsupported claims.

Risk: Too many features in one PR.
Mitigation: Land as separate PRs by phase: contracts/store/policy, gateway rewriter, HTTP proxy, retrieval/stats, MCP/wrappers, proof/bench/docs.

---

## Suggested PR breakdown

PR 1: Gateway foundation
- Phases 1-4
- Contracts, store, reversibility classification, policy

PR 2: Shared rewriter
- Phases 5-6
- Request shapes and GatewayRewriter

PR 3: HTTP gateway and stats
- Phases 7-8
- Multi-provider proxy, retrieval endpoint, stats CLI

PR 4: MCP and wrappers
- Phases 9-10
- MCP tools and `kompressor wrap`

PR 5: Cache/output controls
- Phases 11-12
- Cache-aligned prompts and opt-in output shaping

PR 6: Proof, benchmarks, docs
- Phases 13-16
- Proof script, gateway benchmark, docs, wheel smoke

---

## First implementation slice

Start with PR 1 only. Do not touch HTTP proxy behavior until the policy/store contracts are tested.

Exact first command sequence:

```bash
cd /Users/ccoates/Documents/kompressor
git status --short --branch
git pull --ff-only origin main
git checkout -b feat/context-gateway-foundation
python -m pytest -q
```

Then implement Phase 1 with RED-GREEN-REFACTOR.
