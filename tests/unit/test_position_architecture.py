from datetime import UTC, datetime
from decimal import Decimal

from qcore.accounting.portfolio_state import AccountingEngine
from qcore.data.stores import MarketStore
from qcore.domain.enums import OrderSide, RiskStatus
from qcore.domain.events import BarCloseEvent, FillEvent
from qcore.domain.ids import AlphaId, FillId, OrderId, StrategyId, TargetId
from qcore.domain.types import Money, PortfolioTarget, Price, Quantity, Symbol, Timeframe, Venue
from qcore.execution.planner import BasicExecutionPlanner
from qcore.risk.pre_trade import BasicRiskManager


def _seed_price(market_store: MarketStore, symbol: Symbol, venue: Venue, price: str) -> None:
    market_store.on_bar_close(
        BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=Timeframe("1m"),
            bar_open_time=datetime(2026, 1, 1, tzinfo=UTC),
            open_price=Price(price),
            high_price=Price(price),
            low_price=Price(price),
            close_price=Price(price),
            volume=Quantity("1"),
            timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        )
    )


def _fill(
    *,
    symbol: Symbol,
    venue: Venue,
    strategy_id: str,
    side: OrderSide,
    quantity: str,
    price: str = "100",
) -> FillEvent:
    return FillEvent(
        fill_id=FillId(f"fill-{strategy_id}-{side.value.lower()}"),
        order_id=OrderId(f"order-{strategy_id}-{side.value.lower()}"),
        symbol=symbol,
        side=side,
        quantity=Quantity(quantity),
        fill_price=Price(price),
        venue=venue,
        timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        fee=Money("0"),
        slippage_bps=Decimal("0"),
        strategy_id=StrategyId(strategy_id),
        metadata={"target_quantity": quantity if side is OrderSide.BUY else f"-{quantity}"},
    )


def _target(
    *,
    symbol: Symbol,
    strategy_id: str,
    quantity: str,
    price: str = "100",
) -> PortfolioTarget:
    return PortfolioTarget(
        target_id=TargetId(f"target-{strategy_id}"),
        alpha_id=AlphaId(f"alpha-{strategy_id}"),
        symbol=symbol,
        target_quantity=Quantity(quantity),
        target_price=Price(price),
        timestamp=datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
        strategy_id=StrategyId(strategy_id),
    )


def test_execution_planner_uses_strategy_slice_not_symbol_net() -> None:
    market_store = MarketStore()
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    _seed_price(market_store, symbol, venue, "100")

    accounting = AccountingEngine(market_store=market_store, starting_cash=Decimal("100000"))
    accounting.on_fill(_fill(symbol=symbol, venue=venue, strategy_id="s1", side=OrderSide.BUY, quantity="5"))

    planner = BasicExecutionPlanner(accounting=accounting, min_trade_quantity=Decimal("0.0001"))
    target = _target(symbol=symbol, strategy_id="s2", quantity="4")
    risk = BasicRiskManager(
        accounting=accounting,
        market_store=market_store,
        max_abs_position_quantity=Decimal("20"),
        max_abs_notional=Decimal("200000"),
    )

    decision = risk.on_portfolio_target(target)
    instruction = planner.on_risk_decision(decision)

    assert instruction is not None
    assert instruction.strategy_id == StrategyId("s2")
    assert instruction.side is OrderSide.BUY
    assert instruction.quantity.value == Decimal("4")
    assert instruction.current_quantity.value == Decimal("0")
    assert instruction.metadata["aggregate_current_quantity"] == "5"
    assert instruction.metadata["aggregate_target_quantity"] == "9"


def test_risk_manager_checks_proposed_aggregate_position() -> None:
    market_store = MarketStore()
    symbol = Symbol("ETHUSDT")
    venue = Venue("SIM")
    _seed_price(market_store, symbol, venue, "100")

    accounting = AccountingEngine(market_store=market_store, starting_cash=Decimal("100000"))
    accounting.on_fill(_fill(symbol=symbol, venue=venue, strategy_id="s1", side=OrderSide.BUY, quantity="6"))

    risk = BasicRiskManager(
        accounting=accounting,
        market_store=market_store,
        max_abs_position_quantity=Decimal("10"),
        max_abs_notional=Decimal("1000"),
    )

    decision = risk.on_portfolio_target(_target(symbol=symbol, strategy_id="s2", quantity="5"))

    assert decision.status is RiskStatus.REJECTED
    assert decision.reason == "position limit exceeded"
    assert decision.metadata["current_aggregate_quantity"] == "6"
    assert decision.metadata["proposed_aggregate_quantity"] == "11"
