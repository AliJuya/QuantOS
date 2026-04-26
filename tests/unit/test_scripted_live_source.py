from pathlib import Path

from adapters.exchanges.simulator import JsonlScriptedLiveMarketDataSource
from qcore.domain.events import BarCloseEvent
from qcore.kernel.event_bus import SynchronousEventBus


def test_scripted_live_source_publishes_script_events() -> None:
    project_root = Path(__file__).resolve().parents[2]
    source = JsonlScriptedLiveMarketDataSource(
        script_path=project_root / "tests/fixtures/data/live_ema_cross_script.jsonl",
        input_mode="bars",
        source_timeframe="1d",
    )
    bus = SynchronousEventBus()
    observed: list[BarCloseEvent] = []
    bus.subscribe(BarCloseEvent, observed.append)

    source.start(bus)

    assert len(observed) == 8
    assert observed[0].close_price.value == 100
