from pathlib import Path

from qcore.kernel.config import load_config, normalize_config


def test_normalize_config_supports_singular_strategy_and_gate() -> None:
    config = normalize_config({
        "strategy": {"kind": "ema_cross", "strategy_id": "s1", "short_period": 3, "long_period": 5, "signal_horizon": "1d"},
        "gate": {"kind": "pass_through"},
    })

    assert isinstance(config["strategies"], list)
    assert config["strategies"][0]["strategy_id"] == "s1"
    assert isinstance(config["gates"], list)
    assert config["gates"][0]["kind"] == "pass_through"
    assert config["models"] == []


def test_load_config_normalizes_shorthand(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "\n".join([
            "strategy:",
            "  kind: ema_cross",
            "  strategy_id: s1",
            "  short_period: 3",
            "  long_period: 5",
            "  signal_horizon: 1d",
        ]),
        encoding="utf-8",
    )

    config = load_config(path)

    assert "strategies" in config
    assert config["strategies"][0]["kind"] == "ema_cross"
    assert config["gates"] == []
    assert config["models"] == []
