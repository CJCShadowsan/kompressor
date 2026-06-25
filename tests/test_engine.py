from kompressor.engine import KompressorEngine
from kompressor.models import KompressorConfig


def test_engine_routes_json_array_to_table() -> None:
    rows = [{"id": f"AX-{idx}", "event": "auth_timeout_error", "severity": "CRITICAL"} for idx in range(30)]
    result = KompressorEngine().optimize(rows)
    assert result.kind == "json_table"
    assert result.reversible
    assert result.system_prompt


def test_engine_threshold_returns_none() -> None:
    result = KompressorEngine(KompressorConfig(minimum_chars_to_optimize=100)).optimize("small")
    assert result.kind == "none"


def test_engine_invalid_string_safe() -> None:
    result = KompressorEngine().optimize("not structured")
    assert result.kind == "none"
