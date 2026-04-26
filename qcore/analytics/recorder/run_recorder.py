from __future__ import annotations

import json
import shutil
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, TextIO

from qcore.domain.commands import OrderRequest
from qcore.domain.events import FillEvent, OrderAccepted, OrderCanceled, OrderRejected
from qcore.domain.results import ExecutionInstruction, ExecutionReport, GateDecision, RiskDecision
from qcore.domain.types import (
    AlphaSignal,
    ClosedTrade,
    LedgerEntry,
    Money,
    PortfolioSnapshot,
    PortfolioTarget,
    PositionSnapshot,
    Price,
    Quantity,
    RegimeSnapshot,
    RunManifest,
    Symbol,
    Timeframe,
    Venue,
    VolatilitySnapshot,
    WarmupStatus,
)


def to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: to_serializable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_serializable(item) for item in value]
    return value


def _primitive_value_payload(value: Symbol | Venue | Timeframe) -> dict[str, str]:
    return {"value": value.value}


def _money_payload(value: Money) -> dict[str, str]:
    return {"amount": str(value.amount), "currency": value.currency}


def _price_payload(value: Price | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"value": str(value.value)}


def _quantity_payload(value: Quantity) -> dict[str, str]:
    return {"value": str(value.value)}


def _position_snapshot_payload(position: PositionSnapshot) -> dict[str, Any]:
    return {
        "symbol": _primitive_value_payload(position.symbol),
        "quantity": _quantity_payload(position.quantity),
        "avg_price": _price_payload(position.avg_price),
        "mark_price": _price_payload(position.mark_price),
        "market_value": _money_payload(position.market_value),
        "unrealized_pnl": _money_payload(position.unrealized_pnl),
        "realized_pnl": _money_payload(position.realized_pnl),
        "timestamp": position.timestamp.isoformat(),
    }


def _portfolio_snapshot_payload(snapshot: PortfolioSnapshot) -> dict[str, Any]:
    balance = snapshot.balance
    return {
        "timestamp": snapshot.timestamp.isoformat(),
        "positions": [_position_snapshot_payload(position) for position in snapshot.positions],
        "balance": {
            "cash": _money_payload(balance.cash),
            "equity": _money_payload(balance.equity),
            "fees_paid": _money_payload(balance.fees_paid),
            "timestamp": balance.timestamp.isoformat(),
        },
        "realized_pnl": _money_payload(snapshot.realized_pnl),
        "unrealized_pnl": _money_payload(snapshot.unrealized_pnl),
        "net_pnl": _money_payload(snapshot.net_pnl),
    }


class RunRecorder:
    def __init__(self, run_dir: Path, *, buffer_size: int = 1000) -> None:
        self.run_dir = run_dir
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.trade_count = 0
        self.buffer_size = max(1, int(buffer_size))
        self._buffers: dict[str, list[str]] = {}
        self._handles: dict[str, TextIO] = {}

    def write_manifest(self, manifest: RunManifest) -> Path:
        path = self.run_dir / "manifest.json"
        path.write_text(json.dumps(to_serializable(manifest), indent=2), encoding="utf-8")
        return path

    def record_event(self, event: object) -> None:
        if isinstance(event, AlphaSignal):
            self._write_jsonl("alpha_signals.jsonl", event)
        elif isinstance(event, PortfolioTarget):
            self._write_jsonl("targets.jsonl", event)
        elif isinstance(event, GateDecision):
            self._write_jsonl("gates.jsonl", event)
        elif isinstance(event, RiskDecision):
            self._write_jsonl("risk.jsonl", event)
        elif isinstance(event, ExecutionInstruction):
            self._write_jsonl("instructions.jsonl", event)
        elif isinstance(event, OrderRequest):
            self._write_jsonl("orders.jsonl", event)
        elif isinstance(event, (OrderAccepted, OrderRejected, OrderCanceled)):
            self._write_jsonl("order_events.jsonl", event)
        elif isinstance(event, FillEvent):
            self._write_jsonl("fills.jsonl", event)
        elif isinstance(event, ClosedTrade):
            self.trade_count += 1
            self._write_jsonl("trades.jsonl", event)
        elif isinstance(event, LedgerEntry):
            self._write_jsonl("ledger.jsonl", event)
        elif isinstance(event, ExecutionReport):
            self._write_jsonl("execution_reports.jsonl", event)
        elif isinstance(event, WarmupStatus):
            self._write_jsonl("warmup.jsonl", event)
        elif isinstance(event, VolatilitySnapshot):
            self._write_jsonl("volatility.jsonl", event)
        elif isinstance(event, RegimeSnapshot):
            self._write_jsonl("regime.jsonl", event)

    def record_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self._write_jsonl_payload("equity.jsonl", _portfolio_snapshot_payload(snapshot))

    def write_summary(self, manifest: RunManifest, snapshot: PortfolioSnapshot) -> Path:
        summary = {
            "run_id": str(manifest.run_id),
            "event_count": manifest.event_count,
            "trade_count": self.trade_count,
            "ending_cash": str(snapshot.balance.cash.amount),
            "ending_equity": str(snapshot.balance.equity.amount),
            "realized_pnl": str(snapshot.realized_pnl.amount),
            "unrealized_pnl": str(snapshot.unrealized_pnl.amount),
            "net_pnl": str(snapshot.net_pnl.amount),
            "fees_paid": str(snapshot.balance.fees_paid.amount),
            "positions": to_serializable(snapshot.positions),
        }
        path = self.run_dir / "summary.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return path

    def _write_jsonl(self, name: str, payload: object) -> None:
        line = json.dumps(to_serializable(payload))
        self._append_json_line(name, line)

    def _write_jsonl_payload(self, name: str, payload: Any) -> None:
        line = json.dumps(payload)
        self._append_json_line(name, line)

    def _append_json_line(self, name: str, line: str) -> None:
        bucket = self._buffers.setdefault(name, [])
        bucket.append(line)
        if len(bucket) >= self.buffer_size:
            self._flush_file(name)

    def flush(self) -> None:
        for name in list(self._buffers.keys()):
            self._flush_file(name)
        for handle in self._handles.values():
            handle.flush()

    def close(self) -> None:
        self.flush()
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()

    def _flush_file(self, name: str) -> None:
        lines = self._buffers.get(name)
        if not lines:
            return
        handle = self._handles.get(name)
        if handle is None:
            path = self.run_dir / name
            handle = path.open("a", encoding="utf-8")
            self._handles[name] = handle
        handle.write("\n".join(lines))
        handle.write("\n")
        lines.clear()
