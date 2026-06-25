from __future__ import annotations

import argparse
import json
import os
import platform
import random
import re
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kompressor.codecs.json_table import JsonTableCodec
from kompressor.engine import KompressorEngine
from kompressor.security import find_secrets, redact_secrets

SEED = 20260625


@dataclass
class PayloadCase:
    id: str
    kind: str
    codec_expected: str
    data: Any
    task: dict[str, Any]


def _records(case_id: int, n: int) -> list[dict[str, Any]]:
    severities = ["CRITICAL", "WARNING", "INFO"]
    events = ["auth_timeout_error", "db_query_slow_exec", "api_gateway_success"]
    services = ["auth", "db", "gateway", "billing", "search"]
    out = []
    for i in range(n):
        sev = severities[(case_id + i) % len(severities)]
        event = events[(case_id * 3 + i) % len(events)]
        svc = services[(case_id + i * 2) % len(services)]
        out.append(
            {
                "id": f"evt-{case_id:04d}-{i:04d}",
                "timestamp": f"2026-06-25T{(i % 24):02d}:{(i * 7 % 60):02d}:00Z",
                "service": svc,
                "event": event,
                "severity": sev,
                "latency_ms": 50 + ((case_id * 17 + i * 31) % 950),
                "region": ["us-east-1", "us-west-2", "eu-central-1"][(case_id + i) % 3],
            }
        )
    return out


def _nested(case_id: int) -> dict[str, Any]:
    services = {}
    for svc_idx in range(6):
        svc = f"svc-{svc_idx}"
        services[svc] = {
            "replicas": 1 + ((case_id + svc_idx) % 5),
            "images": [f"registry.example.com/{svc}:v{case_id}.{j}" for j in range(3)],
            "limits": {"cpu": f"{1 + svc_idx}", "memory": f"{512 + svc_idx * 128}Mi"},
            "env": {f"VAR_{j}": f"value-{case_id}-{svc_idx}-{j}" for j in range(6)},
        }
    return {"cluster": f"cluster-{case_id}", "namespace": "benchmark", "services": services}


def _xml(case_id: int) -> str:
    root = ET.Element("testsuite", name=f"suite-{case_id}", tests="12")
    for i in range(12):
        case = ET.SubElement(root, "testcase", classname=f"Class{case_id}", name=f"test_{i}", time=str((i + 1) / 10))
        if (case_id + i) % 5 == 0:
            fail = ET.SubElement(case, "failure", message="assertion failed")
            fail.text = f"expected {i}, got {case_id}"
    return ET.tostring(root, encoding="unicode")


def _logs(case_id: int, n: int) -> str:
    lines = []
    levels = ["ERROR", "WARN", "INFO"]
    for i in range(n):
        lines.append(
            f"2026-06-25T{(i % 24):02d}:{(i * 13 % 60):02d}:00Z {levels[(case_id + i) % 3]} "
            f"service=svc-{i % 7} request=req-{case_id}-{i % 11} message=retryable timeout on upstream shard {i % 5}"
        )
    return "\n".join(lines)


def build_cases(count: int) -> list[PayloadCase]:
    cases: list[PayloadCase] = []
    for i in range(count):
        bucket = i % 5
        if bucket in {0, 1}:
            data = _records(i, 36 + (i % 30))
            counts = Counter(row["severity"] for row in data)
            cases.append(
                PayloadCase(
                    id=f"json-table-{i:04d}",
                    kind="json_list_records",
                    codec_expected="json_table",
                    data=data,
                    task={"total": len(data), "severity_counts": dict(counts)},
                )
            )
        elif bucket == 2:
            data = _nested(i)
            cases.append(
                PayloadCase(
                    id=f"nested-json-{i:04d}",
                    kind="nested_json",
                    codec_expected="json_path",
                    data=data,
                    task={"service_count": len(data["services"]), "cluster": data["cluster"]},
                )
            )
        elif bucket == 3:
            data = _xml(i)
            cases.append(
                PayloadCase(
                    id=f"xml-{i:04d}",
                    kind="xml",
                    codec_expected="xml_path",
                    data=data,
                    task={"failure_count": data.count("<failure")},
                )
            )
        else:
            data = _logs(i, 80 + (i % 40))
            counts = Counter(re.findall(r" (ERROR|WARN|INFO) ", data))
            cases.append(
                PayloadCase(
                    id=f"logs-{i:04d}",
                    kind="logs",
                    codec_expected="pattern_hash",
                    data=data,
                    task={"line_count": len(data.splitlines()), "level_counts": dict(counts)},
                )
            )
    return cases


def _payload_text(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2)


def _round_trip_pass(data: Any, result: Any) -> bool | None:
    if result.kind == "json_table":
        payload = result.optimized_payload
        first = payload.split("\n", 1)[0]
        delimiter = first.split('delimiter="', 1)[1].split('"', 1)[0]
        restored = JsonTableCodec((delimiter,)).decompress(payload, {"delimiter": delimiter})
        return restored == data
    if result.reversible:
        # Other current codecs carry local metadata but no CLI round-trip API yet.
        return None
    return None


def run_local(out_dir: Path, count: int) -> dict[str, Any]:
    random.seed(SEED)
    cases = build_cases(count)
    corpus_dir = out_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    engine = KompressorEngine()
    compression_path = out_dir / "compression_results.jsonl"
    reversibility_path = out_dir / "reversibility_results.jsonl"
    task_oracle_path = out_dir / "deterministic_task_oracle.jsonl"
    results = []
    reversible = []
    with (
        compression_path.open("w", encoding="utf-8") as comp,
        reversibility_path.open("w", encoding="utf-8") as rev,
        task_oracle_path.open("w", encoding="utf-8") as oracle,
    ):
        for case in cases:
            raw_text = _payload_text(case.data)
            suffix = ".json" if not isinstance(case.data, str) or case.kind == "nested_json" else ".txt"
            if case.kind == "xml":
                suffix = ".xml"
            path = corpus_dir / f"{case.id}{suffix}"
            path.write_text(raw_text, encoding="utf-8")
            t0 = time.perf_counter()
            result = engine.optimize(case.data)
            compression_ms = (time.perf_counter() - t0) * 1000
            row = {
                "id": case.id,
                "kind": case.kind,
                "expected_codec": case.codec_expected,
                "codec": result.kind,
                "baseline_chars": result.token_stats.baseline_chars,
                "optimized_chars": result.token_stats.optimized_chars,
                "char_savings_pct": 0.0
                if result.token_stats.baseline_chars == 0
                else round(
                    100
                    * (result.token_stats.baseline_chars - result.token_stats.optimized_chars)
                    / result.token_stats.baseline_chars,
                    4,
                ),
                "baseline_tokens_estimate": result.token_stats.baseline_tokens_estimate,
                "optimized_tokens_estimate": result.token_stats.optimized_tokens_estimate,
                "token_savings_estimate_pct": result.token_stats.percent_saved_estimate,
                "estimator": result.token_stats.estimator,
                "compression_ms": round(compression_ms, 4),
                "reversible_claim": result.reversible,
                "warnings": result.warnings,
            }
            comp.write(json.dumps(row, ensure_ascii=False) + "\n")
            results.append(row)
            rt = _round_trip_pass(case.data, result)
            if rt is not None:
                rt_row = {"id": case.id, "codec": result.kind, "round_trip_pass": rt}
                rev.write(json.dumps(rt_row, ensure_ascii=False) + "\n")
                reversible.append(rt_row)
            oracle.write(json.dumps({"id": case.id, "task": case.task}, ensure_ascii=False) + "\n")
    return summarize_local(results, reversible, count)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] * (c - k) + values[c] * (k - f)


def summarize_local(results: list[dict[str, Any]], reversible: list[dict[str, Any]], count: int) -> dict[str, Any]:
    savings = [float(r["char_savings_pct"]) for r in results]
    token_savings = [float(r["token_savings_estimate_pct"]) for r in results]
    by_kind: dict[str, list[float]] = {}
    for row in results:
        by_kind.setdefault(str(row["kind"]), []).append(float(row["char_savings_pct"]))
    return {
        "payloads": count,
        "median_char_savings_pct": round(statistics.median(savings), 4),
        "p25_char_savings_pct": round(_pct(savings, 0.25), 4),
        "p75_char_savings_pct": round(_pct(savings, 0.75), 4),
        "negative_savings_count": sum(1 for v in savings if v < 0),
        "median_token_savings_estimate_pct": round(statistics.median(token_savings), 4),
        "p95_compression_ms": round(_pct([float(r["compression_ms"]) for r in results], 0.95), 4),
        "codec_counts": dict(Counter(str(r["codec"]) for r in results)),
        "by_kind_median_char_savings_pct": {k: round(statistics.median(v), 4) for k, v in sorted(by_kind.items())},
        "reversibility_checked": len(reversible),
        "reversibility_passed": sum(1 for r in reversible if r["round_trip_pass"]),
        "reversibility_pass_rate": 1.0 if reversible and all(r["round_trip_pass"] for r in reversible) else 0.0,
    }


def run_security(out_dir: Path) -> dict[str, Any]:
    fixtures = {
        "api_key": "api_key=abcdefghijklmnopqrstuvwxyz123456",
        "anthropic": "ANTHROPIC_API_KEY=sk-ant-api03abcdefghijklmnopqrstuvwxyz123456",
        "token": "token=ghp_abcdefghijklmnopqrstuvwxyz123456",
        "aws": "AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP",
        "bearer": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
        "database_url": "postgres://user:correct-horse-battery-staple@db.example.com/prod",
    }
    path = out_dir / "security_results.jsonl"
    passed = 0
    with path.open("w", encoding="utf-8") as handle:
        for name, secret in fixtures.items():
            payload = [{"id": name, "secret": secret, "event": "auth_timeout_error"} for _ in range(6)]
            text = json.dumps(payload)
            findings = find_secrets(text)
            redacted = redact_secrets(text)
            leaked = any(value in redacted for value in [secret, secret.split("=", 1)[-1]])
            row = {
                "id": name,
                "detected": bool(findings),
                "finding_count": len(findings),
                "redacted_marker_present": "[REDACTED_" in redacted,
                "leaked_original_secret": leaked,
                "pass": bool(findings) and "[REDACTED_" in redacted and not leaked,
            }
            passed += int(row["pass"])
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"security_fixtures": len(fixtures), "security_passed": passed, "security_pass_rate": passed / len(fixtures)}


def write_manifest(out_dir: Path, count: int) -> None:
    manifest = {
        "benchmark": "kompressor-significant-local-hermes",
        "seed": SEED,
        "payload_count": count,
        "python": sys.version,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "claim_policy": {
            "provider_token_claims": "not measured unless live provider token APIs are added",
            "local_token_estimator": "char_proxy",
            "reversibility_gate": "100% for checked reversible json_table payloads",
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run_hermes(out_dir: Path, n: int) -> dict[str, Any]:
    hermes = shutil_which("hermes")
    if hermes is None:
        return {"runs": 0, "skipped": True, "reason": "hermes not found"}
    proof_log = out_dir / "hermes_native_proof.jsonl"
    results_path = out_dir / "hermes_task_results.jsonl"
    proof_log.unlink(missing_ok=True)
    ok = 0
    compressed_events = 0
    with results_path.open("w", encoding="utf-8") as handle:
        selected = [c for c in build_cases(max(n * 5, n)) if c.kind == "json_list_records"][:n]
        for case in selected:
            expected = case.task
            query = (
                "Answer only with total record count and counts by severity from the raw JSON below. "
                "Use labels Total, CRITICAL, WARNING, INFO.\n\n" + json.dumps(case.data, ensure_ascii=False, indent=2)
            )
            env = os.environ.copy()
            env["KOMPRESSOR_HERMES_PROOF_LOG"] = str(proof_log)
            env["KOMPRESSOR_HERMES_THRESHOLD_CHARS"] = "256"
            t0 = time.perf_counter()
            proc = subprocess.run(
                [hermes, "chat", "-Q", "-t", "safe", "-q", query],
                text=True,
                capture_output=True,
                timeout=180,
                env=env,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            output = proc.stdout + proc.stderr
            total_match = re.search(r"Total\D+(\d+)", output, re.I)
            crit_match = re.search(r"CRITICAL\D+(\d+)", output, re.I)
            warn_match = re.search(r"WARNING\D+(\d+)", output, re.I)
            info_match = re.search(r"INFO\D+(\d+)", output, re.I)
            parsed = {
                "total": int(total_match.group(1)) if total_match else None,
                "CRITICAL": int(crit_match.group(1)) if crit_match else None,
                "WARNING": int(warn_match.group(1)) if warn_match else None,
                "INFO": int(info_match.group(1)) if info_match else None,
            }
            expected_counts = expected["severity_counts"]
            correct = (
                proc.returncode == 0
                and parsed["total"] == expected["total"]
                and parsed["CRITICAL"] == expected_counts.get("CRITICAL", 0)
                and parsed["WARNING"] == expected_counts.get("WARNING", 0)
                and parsed["INFO"] == expected_counts.get("INFO", 0)
            )
            ok += int(correct)
            handle.write(
                json.dumps(
                    {
                        "id": case.id,
                        "returncode": proc.returncode,
                        "correct": correct,
                        "expected": expected,
                        "parsed": parsed,
                        "latency_ms": round(latency_ms, 2),
                        "stdout_preview": proc.stdout[-500:],
                        "stderr_preview": proc.stderr[-500:],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    proof_events = []
    if proof_log.exists():
        with proof_log.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    proof_events.append(json.loads(line))
        compressed_events = sum(
            1
            for e in proof_events
            if e.get("strategy") == "json_table" and e.get("compressed_chars", 10**9) < e.get("original_chars", 0)
        )
    return {
        "requested_runs": n,
        "runs": len(selected),
        "correct": ok,
        "accuracy": ok / len(selected) if selected else 0,
        "proof_events": len(proof_events),
        "compressed_events": compressed_events,
        "all_runs_had_compression_event": compressed_events >= len(selected),
        "proof_log": str(proof_log),
    }


def shutil_which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


def write_report(out_dir: Path, summary: dict[str, Any]) -> None:
    report = f"""# Kompressor Significant Benchmark Report

Run directory: `{out_dir}`

## Summary

```json
{json.dumps(summary, indent=2, ensure_ascii=False)}
```

## Claim interpretation

- Local compression/token numbers use Kompressor's deterministic `char_proxy` estimator, not live provider token APIs.
- Reversibility is exact where this benchmark has a decompressor oracle (`json_table`).
- Security fixtures are synthetic planted-token checks.
- Hermes-native results are live `hermes chat` runs with
  `KOMPRESSOR_HERMES_PROOF_LOG` proving native middleware compression events.

## Artifacts

- `manifest.json`
- `compression_results.jsonl`
- `reversibility_results.jsonl`
- `deterministic_task_oracle.jsonl`
- `security_results.jsonl`
- `hermes_task_results.jsonl` if Hermes was available
- `hermes_native_proof.jsonl` if Hermes middleware ran
"""
    (out_dir / "report.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--payloads", type=int, default=500)
    parser.add_argument("--hermes-runs", type=int, default=0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    write_manifest(args.out, args.payloads)
    local = run_local(args.out, args.payloads)
    security = run_security(args.out)
    hermes = run_hermes(args.out, args.hermes_runs) if args.hermes_runs else {"runs": 0, "skipped": True}
    summary = {"local": local, "security": security, "hermes_native": hermes}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(args.out, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
