from datetime import UTC, datetime

from qcore.domain.enums import EntryStyle, SignalSide
from qcore.domain.ids import AlphaId, GateId, ModelId, StrategyId
from qcore.domain.results import GateDecision
from qcore.domain.types import AlphaSignal, RegimeSnapshot, Symbol, Timeframe, VolatilitySnapshot
from qcore.gates import GateEngine, ModelAlignmentGate
from qcore.models.store import ModelStore
from qcore.models.view import ModelView


def _signal(side: SignalSide) -> AlphaSignal:
    return AlphaSignal(
        alpha_id=AlphaId(f"alpha:{side.value}"),
        strategy_id=StrategyId("ema_cross"),
        symbol=Symbol("BTCUSDT"),
        side=side,
        confidence=0.5,
        horizon=Timeframe("1d"),
        entry_style=EntryStyle.TREND,
        thesis="test",
        invalidation="test",
        timestamp=datetime(2026, 1, 10, tzinfo=UTC),
        features_ref=None,
    )


def test_gate_engine_approves_when_models_align() -> None:
    store = ModelStore()
    store.store_snapshot(
        RegimeSnapshot(
            model_id=ModelId("regime.ema"),
            symbol=Symbol("BTCUSDT"),
            timeframe=Timeframe("1d"),
            timestamp=datetime(2026, 1, 10, tzinfo=UTC),
            regime="bull",
            score=0.2,
            ready=True,
        )
    )
    store.store_snapshot(
        VolatilitySnapshot(
            model_id=ModelId("volatility.ewma"),
            symbol=Symbol("BTCUSDT"),
            timeframe=Timeframe("1d"),
            timestamp=datetime(2026, 1, 10, tzinfo=UTC),
            annualized_vol=0.8,
            return_std=0.04,
            ready=True,
        )
    )
    gate = ModelAlignmentGate(
        gate_id=GateId("gate.model_alignment"),
        timeframe=Timeframe("1d"),
        regime_model_id=ModelId("regime.ema"),
        volatility_model_id=ModelId("volatility.ewma"),
        require_regime_alignment=True,
        max_annualized_vol=1.0,
        allow_unready=False,
    )
    decision = GateEngine(gates=(gate,), model_view=ModelView(store)).on_alpha_signal(_signal(SignalSide.LONG))

    assert isinstance(decision, GateDecision)
    assert decision.approved is True


def test_gate_engine_blocks_when_regime_mismatches() -> None:
    store = ModelStore()
    store.store_snapshot(
        RegimeSnapshot(
            model_id=ModelId("regime.ema"),
            symbol=Symbol("BTCUSDT"),
            timeframe=Timeframe("1d"),
            timestamp=datetime(2026, 1, 10, tzinfo=UTC),
            regime="bear",
            score=0.3,
            ready=True,
        )
    )
    gate = ModelAlignmentGate(
        gate_id=GateId("gate.model_alignment"),
        timeframe=Timeframe("1d"),
        regime_model_id=ModelId("regime.ema"),
        require_regime_alignment=True,
        allow_unready=False,
    )
    decision = GateEngine(gates=(gate,), model_view=ModelView(store)).on_alpha_signal(_signal(SignalSide.LONG))

    assert decision.approved is False
    assert decision.reason == "regime_mismatch:bear"
