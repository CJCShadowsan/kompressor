from __future__ import annotations

import json
import subprocess


def test_gateway_proof_script(tmp_path):
    out = tmp_path / "proof.json"
    proc = subprocess.run(
        ["./.venv/bin/python", "scripts/gateway_proof.py", "--out", str(out)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(out.read_text())
    assert payload["gateway_rewrite_proof"] is True
    assert payload["retrieval_round_trip"] is True


def test_gateway_benchmark_script(tmp_path):
    proc = subprocess.run(
        ["./.venv/bin/python", "scripts/gateway_benchmark.py", "--out", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads((tmp_path / "summary.json").read_text())
    assert payload["total_cases"] == 3
    assert payload["negative_savings_count"] == 0
