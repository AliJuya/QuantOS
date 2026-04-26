import pytest

from qcore.registry.base import ComponentRegistry
from qcore.registry.calendars import build_calendar
from qcore.registry.execution import build_broker, build_planner
from qcore.registry.gates import build_gate_engine
from qcore.registry.models import build_model, build_models
from qcore.registry.risk import build_risk
from qcore.registry.strategies import build_strategies, build_strategy


# ---------------------------------------------------------------------------
# ComponentRegistry base
# ---------------------------------------------------------------------------


def test_registry_register_and_build() -> None:
    reg: ComponentRegistry[str] = ComponentRegistry("test")
    reg.register("foo", lambda cfg: f"foo:{cfg.get('x')}")
    result = reg.build({"kind": "foo", "x": 42})
    assert result == "foo:42"


def test_registry_missing_kind_raises() -> None:
    reg: ComponentRegistry[str] = ComponentRegistry("test")
    reg.register("foo", lambda cfg: "foo")
    with pytest.raises(ValueError, match="missing 'kind'"):
        reg.build({})


def test_registry_unknown_kind_raises() -> None:
    reg: ComponentRegistry[str] = ComponentRegistry("test")
    reg.register("foo", lambda cfg: "foo")
    with pytest.raises(KeyError, match="unknown kind"):
        reg.build({"kind": "bar"})


def test_registry_kinds() -> None:
    reg: ComponentRegistry[str] = ComponentRegistry("test")
    reg.register("b", lambda cfg: "b")
    reg.register("a", lambda cfg: "a")
    assert reg.kinds() == ["a", "b"]


# ---------------------------------------------------------------------------
# Calendar registry
# ---------------------------------------------------------------------------


def test_build_calendar_always_open() -> None:
    from qcore.data.calendars import AlwaysOpenCalendar

    cal = build_calendar({"kind": "always_open", "calendar_id": "c1", "timezone": "UTC"})
    assert isinstance(cal, AlwaysOpenCalendar)


def test_build_calendar_defaults_to_always_open() -> None:
    from qcore.data.calendars import AlwaysOpenCalendar

    cal = build_calendar({})
    assert isinstance(cal, AlwaysOpenCalendar)


def test_build_calendar_windowed() -> None:
    from qcore.data.calendars import WindowedSessionCalendar

    cal = build_calendar({
        "kind": "windowed",
        "calendar_id": "nyse",
        "timezone": "America/New_York",
        "windows": [{"label": "rth", "start_hour": 9, "end_hour": 16}],
    })
    assert isinstance(cal, WindowedSessionCalendar)


def test_build_calendar_unknown_kind_raises() -> None:
    with pytest.raises(KeyError, match="unknown kind"):
        build_calendar({"kind": "nonexistent"})


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------


def test_build_strategy_ema_cross() -> None:
    from qcore.alpha.strategies import EmaCrossStrategy
    from qcore.domain.types import Timeframe

    cfg = {
        "kind": "ema_cross",
        "strategy_id": "test_s",
        "short_period": 3,
        "long_period": 8,
        "signal_horizon": "1d",
    }
    s = build_strategy(cfg, Timeframe("1d"))
    assert isinstance(s, EmaCrossStrategy)
    assert s.short_period == 3
    assert s.long_period == 8


def test_build_strategy_respects_input_timeframe_override() -> None:
    from qcore.domain.types import Timeframe

    cfg = {
        "kind": "ema_cross",
        "strategy_id": "test_s",
        "short_period": 3,
        "long_period": 8,
        "signal_horizon": "1d",
        "input_timeframe": "4h",
    }
    s = build_strategy(cfg, Timeframe("1d"))
    assert s.input_timeframe == Timeframe("4h")


def test_build_strategy_uses_source_timeframe_when_not_set() -> None:
    from qcore.domain.types import Timeframe

    cfg = {
        "kind": "ema_cross",
        "strategy_id": "test_s",
        "short_period": 3,
        "long_period": 8,
        "signal_horizon": "1d",
    }
    s = build_strategy(cfg, Timeframe("1h"))
    assert s.input_timeframe == Timeframe("1h")


def test_build_strategy_unknown_kind_raises() -> None:
    from qcore.domain.types import Timeframe

    with pytest.raises(KeyError, match="unknown kind"):
        build_strategy({"kind": "rsi_divergence"}, Timeframe("1d"))


def test_build_strategies_list() -> None:
    from qcore.alpha.strategies import EmaCrossStrategy
    from qcore.domain.types import Timeframe

    cfgs = [
        {"kind": "ema_cross", "strategy_id": "s1", "short_period": 3, "long_period": 8, "signal_horizon": "1d"},
        {"kind": "ema_cross", "strategy_id": "s2", "short_period": 5, "long_period": 20, "signal_horizon": "1d"},
    ]
    strategies = build_strategies(cfgs, Timeframe("1d"))
    assert len(strategies) == 2
    assert all(isinstance(s, EmaCrossStrategy) for s in strategies)
    assert strategies[0].strategy_id.value == "s1"
    assert strategies[1].strategy_id.value == "s2"


def test_build_strategies_empty_raises() -> None:
    from qcore.domain.types import Timeframe

    with pytest.raises(ValueError, match="at least one strategy"):
        build_strategies([], Timeframe("1d"))


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------


def test_build_model_ewma_vol() -> None:
    from qcore.models.vol import EwmaVolatilityModel

    m = build_model({"kind": "ewma_vol", "timeframe": "1d", "lookback": 10})
    assert isinstance(m, EwmaVolatilityModel)
    assert m.lookback == 10


def test_build_model_ema_regime() -> None:
    from qcore.models.regime import EmaTrendRegimeModel

    m = build_model({"kind": "ema_regime", "timeframe": "1d", "fast_period": 5, "slow_period": 20})
    assert isinstance(m, EmaTrendRegimeModel)
    assert m.fast_period == 5


def test_build_models_list() -> None:
    from qcore.models.regime import EmaTrendRegimeModel
    from qcore.models.vol import EwmaVolatilityModel

    cfgs = [
        {"kind": "ewma_vol", "timeframe": "1d"},
        {"kind": "ema_regime", "timeframe": "1d"},
    ]
    models = build_models(cfgs)
    assert len(models) == 2
    assert isinstance(models[0], EwmaVolatilityModel)
    assert isinstance(models[1], EmaTrendRegimeModel)


def test_build_models_empty_list() -> None:
    assert build_models([]) == ()


def test_build_model_unknown_kind_raises() -> None:
    with pytest.raises(KeyError, match="unknown kind"):
        build_model({"kind": "transformer_alpha", "timeframe": "1d"})


# ---------------------------------------------------------------------------
# Gate registry (now takes list)
# ---------------------------------------------------------------------------


def test_build_gate_engine_single() -> None:
    from qcore.gates import GateEngine
    from qcore.models import ModelEngine

    model_engine = ModelEngine(models=())
    cfgs = [{
        "kind": "model_alignment",
        "gate_id": "g1",
        "timeframe": "1d",
        "require_regime_alignment": False,
        "allow_unready": True,
    }]
    ge = build_gate_engine(cfgs, model_engine)
    assert isinstance(ge, GateEngine)
    assert len(ge.gates) == 1


def test_build_gate_engine_multiple() -> None:
    from qcore.gates import GateEngine
    from qcore.models import ModelEngine

    model_engine = ModelEngine(models=())
    cfgs = [
        {"kind": "model_alignment", "gate_id": "g1", "timeframe": "1d", "allow_unready": True},
        {"kind": "model_alignment", "gate_id": "g2", "timeframe": "1d", "allow_unready": True},
    ]
    ge = build_gate_engine(cfgs, model_engine)
    assert isinstance(ge, GateEngine)
    assert len(ge.gates) == 2


def test_build_gate_engine_empty_raises() -> None:
    from qcore.models import ModelEngine

    ge = build_gate_engine([], ModelEngine(models=()))
    assert len(ge.gates) == 1
    assert ge.gates[0].__class__.__name__ == "PassThroughGate"


def test_build_gate_engine_unknown_kind_raises() -> None:
    from qcore.models import ModelEngine

    with pytest.raises(KeyError, match="unknown kind"):
        build_gate_engine([{"kind": "ml_gate", "timeframe": "1d"}], ModelEngine(models=()))


# ---------------------------------------------------------------------------
# Risk registry
# ---------------------------------------------------------------------------


def test_build_risk_basic() -> None:
    from qcore.accounting.portfolio_state import AccountingEngine
    from qcore.data.stores import MarketStore
    from qcore.risk.pre_trade import BasicRiskManager

    ms = MarketStore()
    accounting = AccountingEngine(market_store=ms, starting_cash=10000)
    risk = build_risk({"kind": "basic", "max_abs_position_quantity": 100, "max_abs_notional": 10000}, ms, accounting)
    assert isinstance(risk, BasicRiskManager)


def test_build_risk_unknown_kind_raises() -> None:
    from qcore.accounting.portfolio_state import AccountingEngine
    from qcore.data.stores import MarketStore

    ms = MarketStore()
    accounting = AccountingEngine(market_store=ms, starting_cash=10000)
    with pytest.raises(KeyError, match="unknown kind"):
        build_risk({"kind": "kelly_risk", "max_abs_position_quantity": 100, "max_abs_notional": 10000}, ms, accounting)


# ---------------------------------------------------------------------------
# Execution registry
# ---------------------------------------------------------------------------


def test_build_planner_basic() -> None:
    from qcore.accounting.portfolio_state import AccountingEngine
    from qcore.data.stores import MarketStore
    from qcore.execution.planner import BasicExecutionPlanner

    ms = MarketStore()
    acct = AccountingEngine(market_store=ms, starting_cash=10000)
    exec_cfg = {"planner": "basic", "broker": "simulated", "venue": "SIM",
                "fee_bps": 5, "slippage_bps": 2, "min_trade_quantity": 0.001}
    planner = build_planner(exec_cfg, acct)
    assert isinstance(planner, BasicExecutionPlanner)


def test_build_broker_simulated() -> None:
    from qcore.data.stores import MarketStore
    from qcore.execution.brokers import SimulatedBroker

    ms = MarketStore()
    exec_cfg = {"planner": "basic", "broker": "simulated", "venue": "SIM",
                "fee_bps": 5, "slippage_bps": 2, "min_trade_quantity": 0.001}
    broker = build_broker(exec_cfg, ms)
    assert isinstance(broker, SimulatedBroker)


def test_build_planner_defaults_to_basic() -> None:
    from qcore.accounting.portfolio_state import AccountingEngine
    from qcore.data.stores import MarketStore
    from qcore.execution.planner import BasicExecutionPlanner

    ms = MarketStore()
    acct = AccountingEngine(market_store=ms, starting_cash=10000)
    exec_cfg = {"venue": "SIM", "fee_bps": 5, "slippage_bps": 2, "min_trade_quantity": 0.001}
    planner = build_planner(exec_cfg, acct)
    assert isinstance(planner, BasicExecutionPlanner)


def test_build_planner_unknown_kind_raises() -> None:
    from qcore.accounting.portfolio_state import AccountingEngine
    from qcore.data.stores import MarketStore

    ms = MarketStore()
    acct = AccountingEngine(market_store=ms, starting_cash=10000)
    with pytest.raises(KeyError, match="unknown kind"):
        build_planner({"planner": "iceberg", "min_trade_quantity": 0.001}, acct)
