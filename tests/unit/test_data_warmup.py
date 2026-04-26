from qcore.data import WarmupRegistry, WarmupRequirement, merge_warmup_requirements
from qcore.domain.types import Timeframe


def test_warmup_registry_merges_max_bars_per_timeframe() -> None:
    one_day = Timeframe("1d")
    one_hour = Timeframe("1h")
    registry = WarmupRegistry()
    registry.register(
        WarmupRequirement(
            component_id="alpha_a",
            bars_by_timeframe={one_day: 10, one_hour: 5},
        )
    )
    registry.register(
        WarmupRequirement(
            component_id="alpha_b",
            bars_by_timeframe={one_day: 7, one_hour: 12},
        )
    )

    merged = registry.global_bars_by_timeframe()

    assert merged[one_day] == 10
    assert merged[one_hour] == 12


def test_merge_warmup_requirements_helper() -> None:
    five_min = Timeframe("5m")
    fifteen_min = Timeframe("15m")

    merged = merge_warmup_requirements(
        (
            WarmupRequirement(component_id="s1", bars_by_timeframe={five_min: 40}),
            WarmupRequirement(component_id="s2", bars_by_timeframe={fifteen_min: 20, five_min: 25}),
        )
    )

    assert merged[five_min] == 40
    assert merged[fifteen_min] == 20
