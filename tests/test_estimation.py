import pytest

from kompressor.estimation import AnthropicCountTokensEstimator, CharProxyEstimator, calculate_stats
from kompressor.models import KompressorConfig


def test_char_proxy_estimate() -> None:
    assert CharProxyEstimator(4).estimate_tokens("x" * 400) == 100
    assert CharProxyEstimator(4).estimate_tokens("") == 0


def test_cost_math_and_expansion() -> None:
    stats = calculate_stats("abcd" * 100, "abcd" * 200, KompressorConfig(cost_per_million_input_usd=3))
    assert stats.saved_tokens_estimate < 0
    assert stats.percent_saved_estimate < 0
    assert stats.estimator == "char_proxy"


def test_anthropic_estimator_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        AnthropicCountTokensEstimator()
