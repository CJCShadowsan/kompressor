# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from kompressor.codecs import (
    GrammarCodec,
    MetaTokensCodec,
    PathDictRowsCodec,
    SeparatorSegmentsCodec,
    SessionDeltaCodec,
    SidecarRefCodec,
    TokenLzCodec,
    TreeDictCodec,
)


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _token_count(text: str) -> int:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _pct(base: int, opt: int) -> float:
    return round(100 * (base - opt) / base, 4) if base else 0.0


def _repeated_text(i: int) -> str:
    return (f"tenant-{i % 5} metadata namespace default service auth route /api/v1/resource status ready\n" * 160) + (
        f"unique-tail-{i}\n"
    )


def _token_text(i: int) -> str:
    return "".join(
        f"resource/{j % 7}/metadata/name/default namespace service account tenant-{i % 3}\n" for j in range(260)
    )


def _segments(i: int) -> str:
    block = f"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  namespace: default\n  labels:\n    app: svc-{i % 4}\n"
    return "\n\n".join([block, "unique: one", block, block, "unique: two", block, block, block])


def _grammar(i: int) -> str:
    return ("apiVersion kind metadata namespace default labels managed-by kompressor " * 260) + str(i)


def _nested(i: int) -> dict[str, Any]:
    return {
        "cluster": f"cluster-{i}",
        "items": [
            {
                "metadata": {
                    "name": f"pod-{i}-{j}",
                    "namespace": "default",
                    "labels": {"app": "api", "tier": "backend"},
                },
                "spec": {
                    "containers": [{"name": "api", "image": f"ghcr.io/acme/api:v{i}", "env": {"LOG_LEVEL": "info"}}]
                },
                "status": {"phase": "Running", "ready": True},
            }
            for j in range(32)
        ],
    }


def _tree(i: int) -> dict[str, Any]:
    subtree = {
        "resources": {"limits": {"cpu": "1", "memory": "1Gi"}},
        "labels": {"managed-by": "kompressor", "tier": "backend"},
    }
    return {"items": [{"name": f"svc-{i}-{j}", "template": subtree, "ports": [80, 443]} for j in range(64)]}


def _session(i: int) -> dict[str, str]:
    base = "\n".join(f"line {j}: service api status ok value {j % 5}" for j in range(220)) + "\n"
    current_lines = base.splitlines()
    for j in range(i % 10, 220, 37):
        current_lines[j] = current_lines[j].replace("ok", "changed")
    current_lines.append(f"line new: rollout {i}")
    return {"base": base, "current": "\n".join(current_lines) + "\n"}


def _sidecar(i: int) -> str:
    return (f"large immutable artifact {i} sha-backed exact sidecar payload\n" * 500) + "end\n"


CASES = [
    ("meta_tokens", MetaTokensCodec, _repeated_text),
    ("token_lz", TokenLzCodec, _token_text),
    ("separator_segments", SeparatorSegmentsCodec, _segments),
    ("grammar", GrammarCodec, _grammar),
    ("path_dict_rows", PathDictRowsCodec, _nested),
    ("tree_dict", TreeDictCodec, _tree),
    ("session_delta", SessionDeltaCodec, _session),
    ("sidecar_ref", SidecarRefCodec, _sidecar),
]


def run(count_per_strategy: int, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for strategy, codec_cls, fixture in CASES:
        codec = codec_cls()
        for i in range(count_per_strategy):
            value = fixture(i)
            raw = _text(value["current"] if strategy == "session_delta" else value)
            result = codec.compress(value)
            restored = codec.decompress(result.payload, result.metadata)
            expected = value["current"] if strategy == "session_delta" else value
            ok = restored == expected
            row = {
                "id": f"{strategy}-{i:04d}",
                "strategy": strategy,
                "reversible": result.reversible,
                "round_trip_pass": ok,
                "baseline_chars": len(raw),
                "optimized_chars": len(result.payload),
                "char_savings_pct": _pct(len(raw), len(result.payload)),
                "baseline_tokens_cl100k": _token_count(raw),
                "optimized_tokens_cl100k": _token_count(result.payload),
            }
            row["token_savings_pct_cl100k"] = _pct(row["baseline_tokens_cl100k"], row["optimized_tokens_cl100k"])
            rows.append(row)
    (out_dir / "reversible_strategy_results.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    by_strategy = {}
    for strategy, *_ in CASES:
        vals = [r for r in rows if r["strategy"] == strategy]
        by_strategy[strategy] = {
            "cases": len(vals),
            "round_trip_passed": sum(1 for r in vals if r["round_trip_pass"]),
            "median_char_savings_pct": round(statistics.median(r["char_savings_pct"] for r in vals), 4),
            "median_token_savings_pct_cl100k": round(statistics.median(r["token_savings_pct_cl100k"] for r in vals), 4),
            "negative_token_savings_count": sum(1 for r in vals if r["token_savings_pct_cl100k"] < 0),
        }
    summary = {
        "strategies": len(CASES),
        "cases": len(rows),
        "round_trip_passed": sum(1 for r in rows if r["round_trip_pass"]),
        "round_trip_pass_rate": round(sum(1 for r in rows if r["round_trip_pass"]) / len(rows), 4),
        "median_char_savings_pct": round(statistics.median(r["char_savings_pct"] for r in rows), 4),
        "median_token_savings_pct_cl100k": round(statistics.median(r["token_savings_pct_cl100k"] for r in rows), 4),
        "negative_token_savings_count": sum(1 for r in rows if r["token_savings_pct_cl100k"] < 0),
        "by_strategy": by_strategy,
    }
    (out_dir / "reversible_strategy_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    report = "# Reversible Strategy Benchmark\n\n```json\n" + json.dumps(summary, indent=2) + "\n```\n"
    (out_dir / "reversible_strategy_report.md").write_text(report)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/bench/reversible-strategies"))
    parser.add_argument("--count-per-strategy", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(run(args.count_per_strategy, args.out), indent=2))


if __name__ == "__main__":
    main()
