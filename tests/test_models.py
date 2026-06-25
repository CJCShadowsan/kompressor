import pytest

from kompressor.models import KompressorConfig, OptimizationResult, TokenStats


def test_config_defaults() -> None:
    cfg = KompressorConfig()
    assert cfg.cost_per_million_input_usd == 3.0
    assert cfg.chars_per_token_proxy == 4.0


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        KompressorConfig(cost_per_million_input_usd=-1)


def test_result_to_dict() -> None:
    stats = TokenStats(10, 5, 3, 1, 2, 66.67, 0.1, 0.01, 0.09, "test")
    result = OptimizationResult("none", "abc", "", stats, True)
    assert result.to_dict()["token_stats"]["estimator"] == "test"
