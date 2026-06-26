# Lossless Token-Sequence Compression for Local-First LLM Contexts

Chris Coates / Kompressor Project
26 June 2026

## Abstract

Large language model applications repeatedly resend verbose structured context: JSON records, Kubernetes resources, logs, source files, generated artifacts, XML, HTML, Markdown, and session state. Kompressor implements local-first lossless context compression: prompt-readable reversible codecs when possible, externalized-reversible sidecars when local metadata is available, and an explicitly gated local-decode transport fallback for runtimes that can inflate compressed bytes before model reasoning. This revision extends the original reversible strategy set with generalized nested shape rows, transformed column rows, tokenizer-cost-aware LZ/meta-token scoring, XML shape rows, zlib/base85 local-decode transport compression, global atom dictionaries, repeated chunk stores, exact code token streams, improved grammar scoring, and reversible domain-table payloads for common OpenAPI/Terraform/Kubernetes/HTML/Markdown-style documents. On the 520-payload vNext corpus, prompt-or-externalized reversible mode round-tripped 520 / 520 cases with 58.748% median `cl100k_base` token savings and zero negative token-savings cases. With explicitly enabled local-decode transport compression, the same corpus round-tripped 520 / 520 cases with 88.8596% median `cl100k_base` token savings and zero negative token-savings cases.

## 1. Introduction

LLM context windows are increasingly large, but prompt and tool-output inflation remains a practical bottleneck. Agentic systems repeatedly transmit structured records, logs, code, build artifacts, generated reports, and configuration graphs whose surface form contains redundancy: repeated keys, paths, paragraphs, line templates, object shapes, token spans, base context, and domain-specific scaffolding.

Kompressor focuses on a strict systems question:

Can a client-side agent reduce ordinary prompt input while preserving exact reconstruction?

The answer depends on where decompression happens. Some formats are compact and model-readable enough to be passed directly to an LLM with parsing instructions. Others are genuinely lossless but should be decompressed by the local runtime, not by the model. This paper separates those classes rather than reporting opaque byte compression as if it were always prompt-readable.

## 2. Related work

Harvill et al., "Lossless Token Sequence Compression via Meta-Tokens" (arXiv:2506.00307), motivates task-agnostic repeated token-span compression. Kompressor adapts that idea in provider-neutral text form and now scores repeated spans with a local tokenizer when available. SepLLM (arXiv:2412.12094) motivates separator-aware condensation, which Kompressor implements conservatively through explicit reversible separator and chunk dictionaries. Traditional codecs such as zlib, Brotli, zstd, LZMA, and bzip2 remain strong lossless baselines; Kompressor now includes a zlib/base85 transport codec, but gates it behind local runtime decompression because it is not a useful model-readable prompt format by itself.

## 3. Reversibility classes

Kompressor reports three distinct classes:

1. Prompt-readable reversible: the payload carries enough structure for local exact decompression and gives the model a compact representation it can reason over.
2. Externalized reversible: exact reconstruction depends on local base/sidecar/chunk metadata that is hash-checked or carried in runtime metadata.
3. Local-decode reversible: exact reconstruction depends on runtime decompression of embedded compressed bytes before model reasoning.

Lossy analytical summaries remain available in Kompressor for task-specific optimization, but they are excluded from the lossless benchmark mode by `KompressorConfig(reversible_only=True)`.

## 4. Implemented lossless strategies

### 4.1 `schema_rows_v1` with column transforms

`schema_rows` encodes homogeneous record lists as typed columns with constants and enum dictionaries. This revision adds exact column transforms for integer sequences and repeated string prefixes. For example, event IDs and monotonically increasing numeric fields can be represented as a base/step or prefix plus residuals.

### 4.2 `shape_rows_v1`

`shape_rows` generalizes table encoding beyond flat `items` lists. It detects homogeneous nested collections, including dict-of-dicts service maps, stores leaf paths once, hoists constants, applies column transforms, and stores value rows. This targets nested JSON structures that previously fell through to `none` or weak path encodings.

### 4.3 `token_lz_v1` and `meta_tokens_v1`

The LZ/meta-token candidate scorer now uses local `cl100k_base` token cost when `tiktoken` is available, falling back to a character proxy. This keeps the codec provider-neutral while making dictionary selection sensitive to BPE boundaries.

### 4.4 `grammar_v1`

The Re-Pair-style grammar codec now considers up to 96 rules and chooses repeated pairs by estimated token-cost gain rather than raw frequency alone. The codec remains exactly reversible by expanding rules in reverse order.

### 4.5 `xml_shape_rows_v1`

`xml_shape_rows` parses repeated sibling XML element shapes, stores the first element as a template, records variable attribute/text paths as rows, and reconstructs exact parsed XML text with ElementTree serialization. It improves repeated XML record handling beyond path/value flattening.

### 4.6 `transport_deflate_v1`

`transport_deflate` is an explicitly gated zlib/base85 local-decode fallback. It is disabled by default and only considered when `KompressorConfig(enable_transport_compression=True)` is set. It is lossless and often much smaller, but the model should not be expected to decode it; the runtime must inflate it before exact reasoning.

### 4.7 `atom_dict_v1`

`atom_dict` builds a global dictionary for repeated scalar strings and keys. It is a broad fallback for repeated identifiers, namespaces, image names, paths, labels, and other atoms that occur across nested structures.

### 4.8 `chunk_store_v1`

`chunk_store` dictionary-encodes repeated paragraphs or lines and stores a sequence of chunk IDs. It is useful for repeated tool outputs, repeated context blocks, and long text with recurring sections.

### 4.9 `code_tokens_v1`

`code_tokens` uses Python's tokenizer to encode exact source code token streams with identifier/string dictionaries. It preserves exact reconstruction through `tokenize.untokenize`. It is reviewable groundwork for syntax-aware code compression; the engine still rejects it when overhead expands the payload.

### 4.10 `domain_table_v1`

`domain_table` provides reversible domain payloads for common OpenAPI, Terraform, Kubernetes, Markdown, HTML, and related documents by combining a compact visible index with embedded deflated source. The visible index helps high-level reasoning; exact reconstruction uses the embedded deflated source.

### 4.11 Existing reversible strategies

Kompressor continues to support `separator_segments`, `path_dict_rows`, `tree_dict`, `session_delta`, `sidecar_ref`, `json_table`, `json_path`, `xml_path`, `pattern_hash`, `binary`, `log_templates`, and `dedupe`.

## 5. Methodology

The updated benchmark is implemented in:

```text
scripts/lossless_suite_benchmark.py
```

It evaluates the existing 520-payload vNext corpus in:

```text
artifacts/bench/2026-06-25-vnext-strategies/corpus
```

Two modes are measured:

1. `prompt_or_externalized_reversible`: `KompressorConfig(reversible_only=True)`.
2. `local_decode_reversible`: `KompressorConfig(reversible_only=True, enable_transport_compression=True)`.

For each payload, the benchmark records baseline characters, optimized characters, local `cl100k_base` token counts via `tiktoken` when available, exact round-trip status through the engine decompressor for every non-`none` reversible candidate, and negative token-savings counts.

Artifacts for this run are in:

```text
artifacts/bench/2026-06-26-lossless-suite/
```

Reproduce with:

```bash
cd /Users/ccoates/Documents/kompressor
source .venv/bin/activate
python scripts/lossless_suite_benchmark.py \
  --out artifacts/bench/2026-06-26-lossless-suite
python -m pytest tests/test_lossless_ext_codecs.py tests/test_reversible_research_codecs.py tests/test_advanced_codecs.py -q
```

## 6. Results

### 6.1 Summary

| Mode | Payloads | Round trips | Median char savings | Median `cl100k_base` token savings | Negative token cases |
|---|---:|---:|---:|---:|---:|
| `prompt_or_externalized_reversible` | 520 | 520 / 520 | 76.2881% | 58.7480% | 0 |
| `local_decode_reversible` | 520 | 520 / 520 | 93.1039% | 88.8596% | 0 |

### 6.2 Prompt-or-externalized reversible by input kind

| Kind | Cases | Median `cl100k_base` token savings | Round trips |
|---|---:|---:|---:|
| blob | 40 | 0.0% | 40 / 40 |
| ci | 40 | 88.8596% | 40 / 40 |
| code | 40 | 91.7706% | 40 / 40 |
| html | 40 | 94.6699% | 40 / 40 |
| json_table | 80 | 58.1317% | 80 / 80 |
| k8s | 40 | 92.4971% | 40 / 40 |
| logs | 40 | 94.5404% | 40 / 40 |
| markdown | 40 | 98.9969% | 40 / 40 |
| nested_json | 40 | 24.9692% | 40 / 40 |
| openapi | 40 | 46.5675% | 40 / 40 |
| terraform | 40 | 23.4888% | 40 / 40 |
| xml | 40 | 9.1837% | 40 / 40 |

### 6.3 Local-decode reversible by input kind

| Kind | Cases | Median `cl100k_base` token savings | Round trips |
|---|---:|---:|---:|
| blob | 40 | 97.9372% | 40 / 40 |
| ci | 40 | 88.8596% | 40 / 40 |
| code | 40 | 91.7706% | 40 / 40 |
| html | 40 | 94.6699% | 40 / 40 |
| json_table | 80 | 69.6754% | 80 / 80 |
| k8s | 40 | 92.4971% | 40 / 40 |
| logs | 40 | 94.5404% | 40 / 40 |
| markdown | 40 | 98.9969% | 40 / 40 |
| nested_json | 40 | 52.2755% | 40 / 40 |
| openapi | 40 | 72.3513% | 40 / 40 |
| terraform | 40 | 78.4686% | 40 / 40 |
| xml | 40 | 29.6521% | 40 / 40 |

## 7. Discussion

The added lossless suite addresses the largest gaps found in the previous repository audit. Nested JSON now has a dedicated `shape_rows` path instead of falling through to no compression in reversible-only mode. JSON-table payloads benefit from column transforms. XML gains a structural codec. Domain-shaped files can be represented as exact reversible payloads rather than only lossy summaries. The gated transport codec confirms that traditional entropy compression is much stronger on many structured payloads when local decode is available, but Kompressor keeps that mode explicit so claims do not conflate byte compression with model-readable prompt compression.

The benchmark also shows honest limits. Blob payloads in prompt-or-externalized reversible mode still show 0.0% median token savings because the strict reversible-only engine does not use lossy blob externalization there unless a reversible codec wins. XML remains weaker than JSON/table/log/code cases in prompt-readable mode. `code_tokens` is implemented and round-trip tested, but current serialization overhead means the engine usually prefers `sidecar_ref` for large code until a more compact token-stream encoding lands.

## 8. Limitations

- `cl100k_base` token savings are local tokenizer measurements, not provider billing metadata.
- `sidecar_ref`, `session_delta`, and chunk/local metadata modes require local runtime state and should not be represented as self-contained prompt payloads.
- `transport_deflate` is lossless but opaque to the model unless the harness inflates it before model reasoning.
- The benchmark corpus is synthetic and structured; external real-world corpora are required for publication-grade generality.
- XML reconstruction uses ElementTree serialization, so it is exact for parsed element/attribute/text content but not a byte-for-byte preservation of irrelevant source formatting.

## 9. Conclusion

Kompressor now includes a broader lossless compression suite covering the ordered recommendations from the repository audit: generalized shape rows, transformed rows, tokenizer-cost-aware LZ, XML shape rows, gated local-decode entropy compression, atom dictionaries, chunk stores, code token streams, improved grammar scoring, and reversible domain tables. The updated benchmark demonstrates exact round trips across 520 / 520 corpus payloads, 58.7480% median local-token savings in prompt-or-externalized reversible mode, and 88.8596% median local-token savings when local-decode transport compression is explicitly enabled.
