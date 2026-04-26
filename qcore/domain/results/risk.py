from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from qcore.domain.enums import RiskStatus
from qcore.domain.ids import DecisionId, TargetId
from qcore.domain.types import PortfolioTarget, ensure_utc


@dataclass(frozen=True, slots=True)
class RiskDecision:
    decision_id: DecisionId
    target_id: TargetId
    status: RiskStatus
    approved_target: PortfolioTarget | None
    reason: str
    timestamp: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))

    @property
    def approved(self) -> bool:
        return self.status is RiskStatus.APPROVED

