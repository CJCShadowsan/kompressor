# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from kompressor.engine import KompressorEngine
from kompressor.models import KompressorConfig


def _token_count(text: str) -> int:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _pct(base: int, opt: int) -> float:
    return round(100 * (base - opt) / base, 4) if base else 0.0


def _load(path: Path) -> object:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        return json.loads(text)
    return text


def _baseline(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _kind(path: Path) -> str:
    name = path.stem
    for suffix in ("nested-json", "json-table"):
        if name.startswith(suffix):
            return suffix.replace("-", "_")
    return name.split("-", 1)[0]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, list[dict[str, Any]]] = {}
    by_strategy: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_kind.setdefault(row["kind"], []).append(row)
        by_strategy.setdefault(row["strategy"], []).append(row)

    def group_summary(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "cases": len(group),
            "round_trip_passed": sum(1 for r in group if r["round_trip_pass"]),
            "median_char_savings_pct": round(statistics.median(r["char_savings_pct"] for r in group), 4),
            "median_token_savings_pct_cl100k": round(statistics.median(r["token_savings_pct_cl100k"] for r in group), 4),
            "negative_token_savings_count": sum(1 for r in group if r["token_savings_pct_cl100k"] < 0),
        }

    return {
        "payloads": len(rows),
        "round_trip_passed": sum(1 for r in rows if r["round_trip_pass"]),
        "round_trip_pass_rate": round(sum(1 for r in rows if r["round_trip_pass"]) / len(rows), 4) if rows else 0,
        "median_char_savings_pct": round(statistics.median(r["char_savings_pct"] for r in rows), 4) if rows else 0,
        "median_token_savings_pct_cl100k": round(statistics.median(r["token_savings_pct_cl100k"] for r in rows), 4) if rows else 0,
        "negative_token_savings_count": sum(1 for r in rows if r["token_savings_pct_cl100k"] < 0),
        "by_kind": {kind: group_summary(group) for kind, group in sorted(by_kind.items())},
        "by_strategy": {strategy: group_summary(group) for strategy, group in sorted(by_strategy.items())},
    }


def run(corpus: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    engines = {
        "prompt_or_externalized_reversible": KompressorEngine(KompressorConfig(reversible_only=True)),
        "local_decode_reversible": KompressorEngine(KompressorConfig(reversible_only=True, enable_transport_compression=True)),
    }
    all_summaries: dict[str, Any] = {}
    for mode, engine in engines.items():
        rows = []
        for path in sorted(p for p in corpus.iterdir() if p.is_file()):
            value = _load(path)
            raw = _baseline(value)
            result = engine.optimize(value)
            restored_ok = True
            if result.reversible and result.kind != "none":
                try:
                    restored_ok = engine.decompress(result.optimized_payload, result.metadata) == value
                except Exception:
                    restored_ok = False
            base_chars = len(raw)
            opt_chars = len(result.optimized_payload)
            base_tokens = _token_count(raw)
            opt_tokens = _token_count(result.optimized_payload)
            rows.append(
                {
                    "id": path.name,
                    "kind": _kind(path),
                    "mode": mode,
                    "strategy": result.kind,
                    "reversible": result.reversible,
                    "round_trip_pass": restored_ok,
                    "baseline_chars": base_chars,
                    "optimized_chars": opt_chars,
                    "char_savings_pct": _pct(base_chars, opt_chars),
                    "baseline_tokens_cl100k": base_tokens,
                    "optimized_tokens_cl100k": opt_tokens,
                    "token_savings_pct_cl100k": _pct(base_tokens, opt_tokens),
                    "warnings": result.warnings,
                }
            )
        (out / f"{mode}_results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        all_summaries[mode] = summarize(rows)
    (out / "lossless_suite_summary.json").write_text(json.dumps(all_summaries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = ["# Lossless Suite Benchmark", "", "Local tokenizer: `cl100k_base` via `tiktoken` when available; otherwise chars/4 proxy.", ""]
    for mode, summary in all_summaries.items():
        report.extend(
            [
                f"## {mode}",
                "",
                f"Payloads: {summary['payloads']}",
                f"Round trips: {summary['round_trip_passed']} / {summary['payloads']}",
                f"Median character savings: {summary['median_char_savings_pct']}%",
                f"Median cl100k token savings: {summary['median_token_savings_pct_cl100k']}%",
                f"Negative token-savings cases: {summary['negative_token_savings_count']}",
                "",
                "| Kind | Cases | Median cl100k token savings | Round trips |",
                "|---|---:|---:|---:|",
            ]
        )
        for kind, payload in summary["by_kind"].items():
            report.append(f"| {kind} | {payload['cases']} | {payload['median_token_savings_pct_cl100k']}% | {payload['round_trip_passed']} / {payload['cases']} |")
        report.append("")
    while report and report[-1] == "":
        report.pop()
    (out / "lossless_suite_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return all_summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("artifacts/bench/2026-06-25-vnext-strategies/corpus"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/bench/lossless-suite"))
    args = parser.parse_args()
    print(json.dumps(run(args.corpus, args.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
