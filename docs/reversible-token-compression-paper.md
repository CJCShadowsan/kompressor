# Reversible Token-Sequence Compression for Local-First LLM Contexts

Craig Coates / Kompressor Project
25 June 2026

## Abstract

Large language model applications often resend verbose structured context: JSON records, Kubernetes resources, logs, source files, generated artifacts, and repeated session state. Prior prompt-compression work frequently uses lossy pruning, model-internal KV-cache compression, or multimodal token reduction. Those techniques can reduce compute, but they do not satisfy a stricter systems requirement: the caller must be able to reconstruct the original input exactly. We introduce Kompressor's reversible strategy set: eight client-side codecs inspired by recent token-compression research, especially lossless meta-token sequence compression, separator-segment condensation, grammar compression, structural path dictionaries, tree dictionaries, session deltas, and hash-backed sidecars. Across 320 synthetic but structured benchmark cases, all codecs round-tripped exactly. The benchmark measured 65.28% median character savings and 55.20% median `cl100k_base` token savings, with zero negative token-savings cases in the benchmark corpus.

## 1. Introduction

LLM context windows are increasingly large, but prompt and tool-output inflation remains a practical bottleneck. Agentic systems repeatedly transmit structured records, logs, code, and build artifacts whose surface form contains redundancy: repeated keys, repeated paths, repeated paragraphs, repeated line templates, and repeated base context across turns.

The Aussie AI token-compression survey collects a broad set of research directions: pruning, token merging, separator-based compression, KV-cache compression, sparse attention, vision/video token reduction, and lossless meta-token compression. Most of these techniques reduce model-side work but either discard information or require model/runtime changes. Kompressor focuses on a complementary question:

Can a client-side agent compress ordinary prompt input while preserving exact reversibility?

## 2. Related work

The closest fit is Harvill et al., "Lossless Token Sequence Compression via Meta-Tokens" (arXiv:2506.00307), which reports task-agnostic LZ77-like lossless token-sequence compression with average input sequence reductions of 27% and 18% on evaluated tasks. Kompressor adopts the core insight — repeated token spans can be represented as reusable meta-tokens — but implements it as ordinary text payloads so it can run without provider tokenizer modification.

SepLLM (arXiv:2412.12094) observes that separator tokens can condense information from adjacent segments in model-internal inference. Kompressor adapts this idea conservatively: rather than relying on hidden model behavior, it builds explicit separator-segment dictionaries that are locally reversible.

Long-context and multimodal compression surveys motivate additional redundancy detectors, but pruning, token dropping, token merging, hidden-chain-of-thought shortening, KV-cache compression, sparse attention, and OCR-style visual compression are not treated as reversible prompt compression unless the original content is retained in a local sidecar.

## 3. Reversible strategies

Kompressor implements eight reversible research strategies.

### 3.1 `meta_tokens_v1`

A textual LZ-style dictionary extracts repeated spans and replaces them with compact symbols such as `§0§`. The compressed payload carries the full dictionary and body. Decompression replaces every symbol with its dictionary entry. This is the most direct adaptation of lossless meta-token compression to provider-neutral prompt text.

### 3.2 `token_lz_v1`

A tokenizer-aware approximation packs repeated textual-token spans. In the current implementation, tokenization is a provider-neutral textual proxy; the benchmark additionally measures `cl100k_base` savings. A future implementation can plug in provider tokenizers directly during candidate selection.

### 3.3 `separator_segments_v1`

Repeated separator-delimited chunks are dictionary encoded. The codec supports paragraph, YAML-document, and line-oriented separators. It is exact when chunks repeat literally.

### 3.4 `grammar_v1`

A small Re-Pair-style grammar repeatedly replaces frequent adjacent token pairs with generated grammar symbols. The payload stores ordered rules plus a compressed body. Decompression expands rules in reverse order.

### 3.5 `path_dict_rows_v1`

Nested JSON-like structures are flattened into repeated path dictionaries and value rows. For common `items` lists, paths are stored once relative to each item and rows carry only values. This targets Kubernetes lists, OpenAPI-like objects, Graphify outputs, and inventory records.

### 3.6 `tree_dict_v1`

Repeated JSON/YAML-like subtrees are extracted into a dictionary and replaced by `$ref` markers. This is structural LZ over object trees rather than raw strings.

### 3.7 `session_delta_v1`

Interactive sessions often resend a large base context with small changes. This codec stores a unified diff from a hash-identified base. Exact reconstruction requires local base metadata, so it is categorized as externalized-reversible.

### 3.8 `sidecar_ref_v1`

Very large immutable payloads can be replaced by a hash, length, and preview while the full text remains in local metadata. This is exact for local/Hermes environments and intentionally marked as sidecar-backed rather than self-contained prompt-reversible.

## 4. Methodology

The benchmark is implemented in:

```text
scripts/reversible_strategy_benchmark.py
```

It generated 40 cases per strategy, 320 total cases. Each case was compressed, decompressed, and compared against the original target. The benchmark records:

- baseline characters
- compressed payload characters
- baseline `cl100k_base` tokens
- compressed `cl100k_base` tokens
- round-trip success
- per-strategy median savings
- negative token-savings counts

Artifacts are in:

```text
artifacts/bench/2026-06-25-reversible-strategies/
```

## 5. Results

Overall result:

| Metric | Result |
|---|---:|
| Strategies | 8 |
| Cases | 320 |
| Round-trip pass rate | 100.00% |
| Median character savings | 65.28% |
| Median `cl100k_base` token savings | 55.20% |
| Negative token-savings cases | 0 |

Per-strategy results:

| Strategy | Cases | Round trips | Median char savings | Median `cl100k_base` token savings | Negative token cases |
|---|---:|---:|---:|---:|---:|
| `meta_tokens` | 40 | 40 | 84.27% | 61.01% | 0 |
| `token_lz` | 40 | 40 | 28.96% | 9.07% | 0 |
| `separator_segments` | 40 | 40 | 30.98% | 22.73% | 0 |
| `grammar` | 40 | 40 | 97.79% | 93.64% | 0 |
| `path_dict_rows` | 40 | 40 | 57.48% | 49.39% | 0 |
| `tree_dict` | 40 | 40 | 57.34% | 45.73% | 0 |
| `session_delta` | 40 | 40 | 72.62% | 71.21% | 0 |
| `sidecar_ref` | 40 | 40 | 98.28% | 97.73% | 0 |

## 6. Discussion

The results show that reversible compression can produce meaningful token savings when redundancy is explicit. The strongest self-contained strategies were grammar compression and meta-token dictionaries. Structural path and tree dictionaries provide substantial gains for JSON-like inputs. Session deltas and sidecar references are powerful in local agent environments, but they depend on local base/sidecar metadata and should not be represented as fully self-contained prompt payloads.

The benchmark is synthetic and intentionally redundancy-rich. It establishes implementation correctness and benchmarkability, not universal real-world savings. Kompressor's engine still gates candidates and skips expansion by default. Provider billing savings require provider-specific token accounting or usage metadata; `cl100k_base` is a local tokenizer proxy.

## 7. Limitations

- The current `token_lz_v1` uses a textual-token proxy for phrase discovery, not direct provider BPE IDs.
- `session_delta_v1` and `sidecar_ref_v1` require local metadata to reconstruct the original.
- The benchmark is local and synthetic; broader corpora are needed for publication-grade external validity.
- Some model-facing compressed forms are exact but may be harder for an LLM to reason over than analytical lossy summaries.

## 8. Conclusion

Kompressor now supports a broad reversible compression suite inspired by contemporary token-compression research. The implementation proves exact reconstruction across all benchmarked cases and demonstrates that reversible prompt compression can materially reduce local tokenized input size without silently dropping information.

## Reproducibility

Run:

```bash
cd /Users/ccoates/Documents/kompressor
source .venv/bin/activate
python scripts/reversible_strategy_benchmark.py \
  --out artifacts/bench/2026-06-25-reversible-strategies \
  --count-per-strategy 40
python -m pytest tests/test_reversible_research_codecs.py -q
```
