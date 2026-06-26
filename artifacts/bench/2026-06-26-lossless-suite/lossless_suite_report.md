# Lossless Suite Benchmark

Local tokenizer: `cl100k_base` via `tiktoken` when available; otherwise chars/4 proxy.

## prompt_or_externalized_reversible

Payloads: 520
Round trips: 520 / 520
Median character savings: 76.2881%
Median cl100k token savings: 58.748%
Negative token-savings cases: 0

| Kind | Cases | Median cl100k token savings | Round trips |
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

## local_decode_reversible

Payloads: 520
Round trips: 520 / 520
Median character savings: 93.1039%
Median cl100k token savings: 88.8596%
Negative token-savings cases: 0

| Kind | Cases | Median cl100k token savings | Round trips |
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
