from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qcore.domain.ids import ModelId
from qcore.domain.types import RegimeSnapshot, Symbol, Timeframe, VolatilitySnapshot


@dataclass(frozen=True, slots=True)
class ModelSnapshotKey:
    model_id: ModelId
    symbol: Symbol
    timeframe: Timeframe
    snapshot_type: str


@dataclass(slots=True)
class ModelStore:
    latest_by_key: dict[ModelSnapshotKey, object] = field(default_factory=dict)

    def store_snapshot(self, snapshot: object) -> None:
        key = self._key_for(snapshot)
        self.latest_by_key[key] = snapshot

    def latest(self, *, model_id: ModelId, symbol: Symbol, timeframe: Timeframe, snapshot_type: str) -> object | None:
        return self.latest_by_key.get(
            ModelSnapshotKey(
                model_id=model_id,
                symbol=symbol,
                timeframe=timeframe,
                snapshot_type=snapshot_type,
            )
        )

    def latest_snapshots_for(self, *, symbol: Symbol, timeframe: Timeframe) -> tuple[object, ...]:
        return tuple(
            snapshot
            for key, snapshot in self.latest_by_key.items()
            if key.symbol == symbol and key.timeframe == timeframe
        )

    def stats(self) -> dict[str, int]:
        return {"latest_snapshots": len(self.latest_by_key)}

    @staticmethod
    def _key_for(snapshot: object) -> ModelSnapshotKey:
        if isinstance(snapshot, VolatilitySnapshot):
            return ModelSnapshotKey(
                model_id=snapshot.model_id,
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                snapshot_type="volatility",
            )
        if isinstance(snapshot, RegimeSnapshot):
            return ModelSnapshotKey(
                model_id=snapshot.model_id,
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                snapshot_type="regime",
            )
        raise TypeError(f"unsupported model snapshot type: {type(snapshot)!r}")
