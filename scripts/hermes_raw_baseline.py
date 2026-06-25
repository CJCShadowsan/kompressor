from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from significant_benchmark import build_cases

ROOT = Path(__file__).resolve().parents[1] / "artifacts/bench/2026-06-25-significant-v2"
OUT = ROOT / "hermes_raw_baseline_results.jsonl"
selected = [c for c in build_cases(150) if c.kind == "json_list_records"][:30]
ok = 0
with OUT.open("w", encoding="utf-8") as handle:
    for case in selected:
        expected = case.task
        query = (
            "Answer only with total record count and counts by severity from the raw JSON below. "
            "Use labels Total, CRITICAL, WARNING, INFO.\n\n" + json.dumps(case.data, ensure_ascii=False, indent=2)
        )
        env = os.environ.copy()
        env["KOMPRESSOR_HERMES_THRESHOLD_CHARS"] = "999999999"
        env.pop("KOMPRESSOR_HERMES_PROOF_LOG", None)
        t0 = time.perf_counter()
        proc = subprocess.run(
            ["hermes", "chat", "-Q", "-t", "safe", "-q", query],
            text=True,
            capture_output=True,
            timeout=180,
            env=env,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        output = proc.stdout + proc.stderr
        parsed = {
            "total": int(m.group(1)) if (m := re.search(r"Total\D+(\d+)", output, re.I)) else None,
            "CRITICAL": int(m.group(1)) if (m := re.search(r"CRITICAL\D+(\d+)", output, re.I)) else None,
            "WARNING": int(m.group(1)) if (m := re.search(r"WARNING\D+(\d+)", output, re.I)) else None,
            "INFO": int(m.group(1)) if (m := re.search(r"INFO\D+(\d+)", output, re.I)) else None,
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
summary = {"runs": len(selected), "correct": ok, "accuracy": ok / len(selected) if selected else 0}
(ROOT / "hermes_raw_baseline_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
