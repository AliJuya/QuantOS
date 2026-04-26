from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from qcore.data.catalog import ResolvedParquetBarDataset
from qcore.data.normalization import ParquetBarDecoder
from qcore.data.replay._parquet_iter import iter_parquet_rows
from qcore.domain.events import BarCloseEvent
from qcore.domain.types import SourceDescriptor


@dataclass(frozen=True, slots=True)
class ParquetBarReplaySource:
    dataset: ResolvedParquetBarDataset

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_id="parquet_replay",
            source_type="parquet",
            mode="replay",
            ordering="monotonic_bar_close_time",
            locations=self.dataset.paths,
            source_timeframe=self.dataset.default_timeframe,
            metadata={
                "input_mode": "bars",
                "timestamp_is": self.dataset.timestamp_is,
                "batch_size": self.dataset.batch_size,
            },
        )

    def iter_events(self) -> Iterator[BarCloseEvent]:
        decoder = ParquetBarDecoder(self.dataset)
        required_columns = list(decoder.required_columns())
        last_key: tuple[datetime, str, str, str] | None = None

        for path, row in iter_parquet_rows(
            paths=self.dataset.paths,
            required_columns=required_columns,
            batch_size=self.dataset.batch_size,
        ):
            event = decoder.decode_row(row)
            event_key = (
                event.timestamp,
                event.symbol.value,
                event.venue.value,
                event.timeframe.value,
            )
            if last_key is not None and event_key < last_key:
                raise ValueError(
                    f"non-monotonic parquet replay ordering detected at {path}: "
                    f"{event_key} < {last_key}"
                )
            last_key = event_key
            yield event
