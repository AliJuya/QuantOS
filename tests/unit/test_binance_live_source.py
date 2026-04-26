from adapters.exchanges.binance import BinanceWebSocketMarketDataSource
from qcore.domain.events import BarCloseEvent, TickEvent, TradeEvent


def test_binance_trade_message_decodes_to_trade_event() -> None:
    source = BinanceWebSocketMarketDataSource(symbol="BTCUSDT", input_mode="trades")

    event = source.decode_message(
        {
            "s": "BTCUSDT",
            "p": "100.5",
            "q": "0.25",
            "T": 1_704_067_200_000,
        }
    )

    assert isinstance(event, TradeEvent)
    assert event.price.value == 100.5


def test_binance_tick_message_decodes_to_tick_event() -> None:
    source = BinanceWebSocketMarketDataSource(symbol="BTCUSDT", input_mode="ticks")

    event = source.decode_message(
        {
            "s": "BTCUSDT",
            "b": "100.0",
            "a": "100.2",
            "E": 1_704_067_200_000,
        }
    )

    assert isinstance(event, TickEvent)
    assert str(event.ask.value) == "100.2"


def test_binance_closed_kline_message_decodes_to_bar_close_event() -> None:
    source = BinanceWebSocketMarketDataSource(symbol="BTCUSDT", input_mode="bars", source_timeframe="1m")

    event = source.decode_message(
        {
            "s": "BTCUSDT",
            "k": {
                "t": 1_704_067_140_000,
                "T": 1_704_067_199_999,
                "i": "1m",
                "o": "100.0",
                "h": "101.0",
                "l": "99.5",
                "c": "100.5",
                "v": "12.0",
                "x": True,
            },
        }
    )

    assert isinstance(event, BarCloseEvent)
    assert event.volume.value == 12


def test_binance_open_kline_message_is_ignored() -> None:
    source = BinanceWebSocketMarketDataSource(symbol="BTCUSDT", input_mode="bars", source_timeframe="1m")

    event = source.decode_message(
        {
            "s": "BTCUSDT",
            "k": {
                "t": 1_704_067_140_000,
                "T": 1_704_067_199_999,
                "i": "1m",
                "o": "100.0",
                "h": "101.0",
                "l": "99.5",
                "c": "100.5",
                "v": "12.0",
                "x": False,
            },
        }
    )

    assert event is None
