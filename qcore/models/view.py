from __future__ import annotations

from dataclasses import dataclass

from qcore.domain.ids import ModelId
from qcore.domain.types import RegimeSnapshot, Symbol, Timeframe, VolatilitySnapshot
from qcore.models.store import ModelStore


@dataclass(frozen=True, slots=True)
class ModelView:
    store: ModelStore

    def latest_volatility(
        self,
        *,
        model_id: ModelId,
        symbol: Symbol,
        timeframe: Timeframe,
    ) -> VolatilitySnapshot | None:
        snapshot = self.store.latest(
            model_id=model_id,
            symbol=symbol,
            timeframe=timeframe,
            snapshot_type="volatility",
        )
        if isinstance(snapshot, VolatilitySnapshot):
            return snapshot
        return None

    def latest_regime(
        self,
        *,
        model_id: ModelId,
        symbol: Symbol,
        timeframe: Timeframe,
    ) -> RegimeSnapshot | None:
        snapshot = self.store.latest(
            model_id=model_id,
            symbol=symbol,
            timeframe=timeframe,
            snapshot_type="regime",
        )
        if isinstance(snapshot, RegimeSnapshot):
            return snapshot
        return None
