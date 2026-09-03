"""Pipeline stages.

Each stage is a swappable step in the ReelForge pipeline. Stages share a
:class:`PipelineContext` (config + run directory + cost ledger + data dict)
and write their artifacts under ``ctx.run_dir``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from reelforge.utils.cost import CostLedger


@dataclass
class PipelineContext:
    """Everything a stage needs to do its job."""

    cfg: dict                      # full merged configuration
    run_dir: Path                  # output/<run_id>/ — stage artifacts live here
    ledger: CostLedger             # usage/cost accounting
    data: dict = field(default_factory=dict)  # cross-stage data handoff
    warnings: list = field(default_factory=list)

    def warn(self, message: str) -> None:
        """Record a non-fatal warning; surfaced in the manifest and CLI output."""
        self.warnings.append(message)


class Stage(ABC):
    """Interface every pipeline stage implements."""

    name = "base"

    @abstractmethod
    def run(self, ctx: PipelineContext) -> None:
        """Execute the stage against ``ctx``."""
