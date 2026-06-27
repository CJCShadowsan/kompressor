"""Raw-text-free gateway statistics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kompressor.gateway.models import GatewayTelemetry


def empty_stats() -> dict[str, Any]:
    return {
        "requests": 0,
        "rewrites": 0,
        "baseline_chars": 0,
        "rewritten_chars": 0,
        "saved_chars": 0,
        "by_strategy": {},
        "by_reversibility_class": {},
        "policy_rejections": {},
        "estimator": "character counts; not provider billing metadata",
    }


class GatewayStats:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_stats()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, stats: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def record(self, telemetry: GatewayTelemetry) -> dict[str, Any]:
        stats = self.load()
        stats["requests"] += 1
        stats["rewrites"] += telemetry.rewrite_count
        for rewrite in telemetry.rewrites:
            stats["baseline_chars"] += rewrite.original_chars
            stats["rewritten_chars"] += rewrite.rewritten_chars
            stats["saved_chars"] += rewrite.saved_chars
            by_strategy = stats["by_strategy"].setdefault(rewrite.strategy, {"count": 0, "saved_chars": 0})
            by_strategy["count"] += 1
            by_strategy["saved_chars"] += rewrite.saved_chars
            by_class = stats["by_reversibility_class"].setdefault(
                rewrite.reversibility_class, {"count": 0, "saved_chars": 0}
            )
            by_class["count"] += 1
            by_class["saved_chars"] += rewrite.saved_chars
        for reason in telemetry.policy_rejections:
            stats["policy_rejections"][reason] = stats["policy_rejections"].get(reason, 0) + 1
        self.save(stats)
        return stats
