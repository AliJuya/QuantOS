# QuantOS

QuantOS starts from a kernel-first runtime and a deterministic event chain rather than from a backtester script. The current vertical slice is parquet-first and implements:

- deterministic parquet bar replay through a resolved local scan plan
- typed `BarCloseEvent` dispatch through a synchronous event bus
- append-only closed-bar rivers inside the market data store
- incremental EMA cross alpha generation
- portfolio target construction
- pre-trade risk approval
- simulated market execution with fee and slippage
- accounting as the single source of truth for cash, positions, fees, and PnL
- run artifact recording under `artifacts/runs/<run_id>`

This public snapshot intentionally exposes only:

- `qcore.alpha.strategies.ema_cross.EmaCrossStrategy`
- `qcore.alpha.strategies.strategy_template.StrategyTemplate`

Private strategy packs, private configs, and local run artifacts are not included.

Run the day-one backtest:

```bash
python -m apps.backtester.main --config configs/app/backtest_ema_cross.yaml --project-root .
```
