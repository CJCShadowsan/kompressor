"""Compatibility API from the original project brief."""

from __future__ import annotations

import json
from typing import Any

from kompressor.codecs.json_table import JsonTableCodec
from kompressor.estimation import CharProxyEstimator, calculate_stats
from kompressor.models import KompressorConfig


class ClaudeTokenSaver:
    def __init__(self) -> None:
        self.cost_per_million_input = 3.00
        self.chars_per_token_proxy = 4.0

    def estimate_tokens(self, text: str) -> int:
        return max(1, CharProxyEstimator(self.chars_per_token_proxy).estimate_tokens(text))

    def flatten_json_context(self, data_list: list[dict[str, Any]], delimiter: str = "|") -> str:
        codec = JsonTableCodec((delimiter, "\t", "¦", "~"))
        return codec.compress(data_list).payload

    def calculate_savings(self, raw_data: list[dict[str, Any]]) -> dict[str, object]:
        standard_string = json.dumps(raw_data, ensure_ascii=False)
        optimized_string = self.flatten_json_context(raw_data)
        stats = calculate_stats(
            standard_string,
            optimized_string,
            KompressorConfig(
                cost_per_million_input_usd=self.cost_per_million_input,
                chars_per_token_proxy=self.chars_per_token_proxy,
            ),
        )
        return {
            "standard_tokens": stats.baseline_tokens_estimate,
            "optimized_tokens": stats.optimized_tokens_estimate,
            "percent_saved": stats.percent_saved_estimate,
            "financial_saved_per_run": round(stats.saved_cost_estimate_usd, 6),
            "optimized_payload": optimized_string,
            "estimator": stats.estimator,
        }
