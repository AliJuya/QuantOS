# QuantOS Upgrade Roadmap

## Objective

QuantOS should keep the QuantRiver intent while improving the architecture:

- strong data engine first
- upward aggregation from a base stream
- strategy layer separated from execution
- optional model lane: volatility / regime / structure / ML
- optional gate lane between alpha and portfolio/risk
- accounting as single source of truth
- stronger recorder/reporting than the current vertical slice
- same contracts across backtest, paper, and live

## What Is Already Fixed

- the repo is green: unit, integration, and determinism tests pass
- the smoke backtest path runs end-to-end
- a sample parquet fixture exists for deterministic local tests
- upward aggregation semantics were corrected
- market-data responsibilities now start in `qcore.data.engine.MarketDataEngine`
- strategy timeframe ownership is explicit
- source-tree hygiene is improved with `.gitignore`

## Current Gap Versus QuantRiver Intent

1. Data layer is still parquet-replay-first, not source-engine-first.
2. Builder composition is still too hardcoded.
3. No model snapshots or model runtime lane yet.
4. No gate runtime lane yet.
5. Reporting is too thin.
6. Session/calendar/warmup are still minimal.
7. Live/paper adapters are not yet meaningful.

## Upgrade Order

### Phase 1: Data Engine

Build a real market-data layer around:

- source adapters
- normalized event ingestion
- base stream ownership
- upward timeframe aggregation
- warmup registry
- session/calendar handling
- read-only market views

Target outcome:

```text
source -> normalizer -> market data engine -> market store -> aggregates
```

### Phase 2: Runtime Composition

Replace hardcoded app-builder wiring with registries/factories for:

- alpha strategies
- portfolio builders
- risk policies
- execution planners
- brokers/simulators
- recorders/reports

Target outcome:

```text
config selects components without editing core builder code
```

### Phase 3: Models

Introduce typed snapshots and stores for:

- volatility
- regime
- structure
- ML inference

Target outcome:

```text
bars -> indicators -> model snapshots -> alpha
```

### Phase 4: Gates

Add a gate layer between alpha and portfolio/risk using explicit contracts:

- gate input bundle
- gate decision
- gate reason / diagnostics

Target outcome:

```text
alpha -> gate -> portfolio target
```

### Phase 5: Reporting and Analytics

Replace thin summaries with real artifacts:

- trade log
- equity curve csv/png
- monthly / yearly / all-time stats
- max drawdown
- PF / winrate / avg win / avg loss
- strategy / session / regime attribution

### Phase 6: Paper and Live Parity

Keep the same contracts and runtime shape while swapping adapters:

- replay clock vs live clock
- simulator vs paper broker vs live broker
- same accounting / risk / execution chain

## Non-Negotiable Rules

- no pandas in hot path
- no strategy placing orders directly
- no broker adapter computing alpha
- no broad mutable state blob as the long-term design
- no new feature without a clean contract and owner
- every phase must leave the repo runnable and testable
