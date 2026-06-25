"""Token and cost estimation."""

from __future__ import annotations

import os
from typing import Protocol

from kompressor.models import KompressorConfig, TokenStats


class TokenEstimator(Protocol):
    name: str

    def estimate_tokens(self, text: str) -> int: ...


class CharProxyEstimator:
    """Deterministic fallback estimator using a characters-per-token proxy."""

    def __init__(self, chars_per_token: float = 4.0) -> None:
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")
        self.chars_per_token = chars_per_token
        self.name = "char_proxy"

    def estimate_tokens(self, text: str) -> int:
        if text == "":
            return 0
        return max(1, int(len(text) / self.chars_per_token))


class AnthropicCountTokensEstimator:
    """Optional live Anthropic count-token estimator.

    This class imports the Anthropic SDK lazily so normal installs and tests do not require
    credentials or a network call.
    """

    def __init__(self, model: str = "claude-3-5-sonnet-latest", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.name = f"anthropic_count_tokens:{model}"
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for live token counting")

    def estimate_tokens(self, text: str) -> int:  # pragma: no cover - live integration
        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)
        result = client.messages.count_tokens(
            model=self.model,
            messages=[{"role": "user", "content": text}],
        )
        return int(result.input_tokens)


def calculate_stats(
    raw: str,
    optimized: str,
    config: KompressorConfig | None = None,
    estimator: TokenEstimator | None = None,
) -> TokenStats:
    cfg = config or KompressorConfig()
    est = estimator or CharProxyEstimator(cfg.chars_per_token_proxy)
    baseline_tokens = est.estimate_tokens(raw)
    optimized_tokens = est.estimate_tokens(optimized)
    saved = baseline_tokens - optimized_tokens
    pct = round((saved / baseline_tokens) * 100, 2) if baseline_tokens else 0.0
    baseline_cost = (baseline_tokens / 1_000_000) * cfg.cost_per_million_input_usd
    optimized_cost = (optimized_tokens / 1_000_000) * cfg.cost_per_million_input_usd
    return TokenStats(
        baseline_chars=len(raw),
        optimized_chars=len(optimized),
        baseline_tokens_estimate=baseline_tokens,
        optimized_tokens_estimate=optimized_tokens,
        saved_tokens_estimate=saved,
        percent_saved_estimate=pct,
        baseline_cost_estimate_usd=round(baseline_cost, 9),
        optimized_cost_estimate_usd=round(optimized_cost, 9),
        saved_cost_estimate_usd=round(baseline_cost - optimized_cost, 9),
        estimator=est.name,
    )
