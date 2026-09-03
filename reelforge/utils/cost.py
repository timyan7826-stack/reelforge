"""Cost & usage accounting.

ReelForge tracks per-stage API usage (tokens, calls, USD) and writes a
machine-readable report alongside every run so that batch production cost is
auditable and predictable.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Usage:
    """Accumulated usage for one stage or the whole run."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    other_units: int = 0
    cost_usd: float = 0.0

    def merge(self, other: "Usage") -> None:
        self.calls += other.calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.other_units += other.other_units
        self.cost_usd += other.cost_usd

    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "other_units": self.other_units,
            "cost_usd": round(self.cost_usd, 6),
        }


# Reference prices in USD per 1M tokens (2026 public list prices, editable).
# Rates are used only for estimates; actual billing is up to your provider.
DEFAULT_RATES = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "deepseek-chat": {"input": 0.27, "output": 1.10},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a single call given a known model rate."""
    rates = DEFAULT_RATES.get(model)
    if not rates:
        return 0.0
    return (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1_000_000


class CostLedger:
    """Thread-free accumulator that records usage per stage and writes a report."""

    def __init__(self) -> None:
        self._by_stage: dict[str, Usage] = {}

    def add(self, stage: str, usage: Usage) -> None:
        if stage not in self._by_stage:
            self._by_stage[stage] = Usage()
        self._by_stage[stage].merge(usage)

    def total(self) -> Usage:
        total = Usage()
        for u in self._by_stage.values():
            total.merge(u)
        return total

    def to_dict(self) -> dict:
        return {
            "stages": {k: v.to_dict() for k, v in sorted(self._by_stage.items())},
            "total": self.total().to_dict(),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }

    def write_report(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        report = out_dir / "cost-report.json"
        report.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return report
