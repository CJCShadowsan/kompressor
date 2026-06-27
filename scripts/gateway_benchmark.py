#!/usr/bin/env python3
"""Benchmark Kompressor Gateway rewriting on local synthetic workloads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompressor.gateway.models import GatewayConfig  # noqa: E402
from kompressor.gateway.rewriter import GatewayRewriter  # noqa: E402


def workloads() -> dict[str, str]:
    rows = json.dumps(
        [
            {"id": i, "event": "auth_timeout_error", "severity": ["CRITICAL", "WARNING", "INFO"][i % 3]}
            for i in range(80)
        ]
    )
    logs = "\n".join(
        f"2026-06-27T00:00:{i:02d}Z ERROR service=auth code={500 + i % 3} request=req-{i}" for i in range(80)
    )
    markdown = "\n".join(["# Incident Runbook", "Repeated paragraph about remediation and rollback."] * 80)
    return {"json_rows": rows, "logs": logs, "markdown": markdown}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cases = []
    for name, text in workloads().items():
        rewriter = GatewayRewriter(GatewayConfig(store_dir=str(args.out / "store"), threshold_chars=0))
        rewritten, telemetry = rewriter.rewrite_request({"messages": [{"role": "user", "content": text}]})
        rewritten_text = (
            rewritten["messages"][-1]["content"]
            if rewritten["messages"][-1]["role"] == "user"
            else json.dumps(rewritten)
        )
        cases.append(
            {
                "name": name,
                "baseline_chars": len(text),
                "rewritten_chars": len(rewritten_text),
                "saved_chars": len(text) - len(rewritten_text),
                "rewrite_count": telemetry.rewrite_count,
                "strategies": [r.strategy for r in telemetry.rewrites],
                "reversibility_classes": [r.reversibility_class for r in telemetry.rewrites],
                "negative_savings": len(rewritten_text) > len(text),
            }
        )
    summary = {
        "cases": cases,
        "total_cases": len(cases),
        "negative_savings_count": sum(1 for c in cases if c["negative_savings"]),
        "estimator": "character counts; not provider billing metadata",
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
