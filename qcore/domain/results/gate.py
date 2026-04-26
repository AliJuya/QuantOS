from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from qcore.domain.ids import AlphaId, GateId
from qcore.domain.types import AlphaSignal, ensure_utc


@dataclass(frozen=True, slots=True)
class GateDecision:
    gate_id: GateId
    alpha_id: AlphaId
    approved_signal: AlphaSignal | None
    reason: str
    timestamp: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))

    @property
    def approved(self) -> bool:
        return self.approved_signal is not None
