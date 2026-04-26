from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from qcore.domain.types import Timeframe


@dataclass(frozen=True, slots=True)
class WarmupRequirement:
    component_id: str
    bars_by_timeframe: Mapping[Timeframe, int]

    def normalized(self) -> dict[Timeframe, int]:
        normalized: dict[Timeframe, int] = {}
        for timeframe, bars in self.bars_by_timeframe.items():
            count = int(bars)
            if count <= 0:
                continue
            normalized[timeframe] = max(normalized.get(timeframe, 0), count)
        return normalized


@dataclass(slots=True)
class WarmupRegistry:
    _requirements: dict[str, WarmupRequirement] = field(default_factory=dict)

    def register(self, requirement: WarmupRequirement) -> None:
        self._requirements[requirement.component_id] = requirement

    def extend(self, requirements: Iterable[WarmupRequirement]) -> None:
        for requirement in requirements:
            self.register(requirement)

    def global_bars_by_timeframe(self) -> dict[Timeframe, int]:
        merged: dict[Timeframe, int] = {}
        for requirement in self._requirements.values():
            for timeframe, bars in requirement.normalized().items():
                merged[timeframe] = max(merged.get(timeframe, 0), bars)
        return merged

    def component_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._requirements.keys()))

    def required_bars(self, timeframe: Timeframe) -> int:
        return self.global_bars_by_timeframe().get(timeframe, 0)

    def stats(self) -> dict[str, object]:
        merged = self.global_bars_by_timeframe()
        return {
            "components": self.component_ids(),
            "bars_by_timeframe": {str(timeframe): bars for timeframe, bars in merged.items()},
        }


def merge_warmup_requirements(requirements: Iterable[WarmupRequirement]) -> dict[Timeframe, int]:
    registry = WarmupRegistry()
    registry.extend(requirements)
    return registry.global_bars_by_timeframe()
