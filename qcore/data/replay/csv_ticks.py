from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from qcore.data.catalog import ResolvedCsvTickDataset
from qcore.data.normalization import ParquetTickDecoder
from qcore.data.replay._csv_iter import iter_csv_rows
from qcore.domain.events import TickEvent
from qcore.domain.types import SourceDescriptor


@dataclass(frozen=True, slots=True)
class CsvTickReplaySource:
    dataset: ResolvedCsvTickDataset

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_id="csv_replay",
            source_type="csv",
            mode="replay",
            ordering="monotonic_tick_time",
            locations=self.dataset.paths,
            source_timeframe=None,
            metadata={
                "input_mode": "ticks",
                "batch_size": self.dataset.batch_size,
            },
        )

    def iter_events(self) -> Iterator[TickEvent]:
        decoder = ParquetTickDecoder(self.dataset)
        required_columns = list(decoder.required_columns())
        last_key: tuple[datetime, str, str] | None = None

        for path, row in iter_csv_rows(paths=self.dataset.paths, required_columns=required_columns):
            event = decoder.decode_row(row)
            event_key = (event.timestamp, event.symbol.value, event.venue.value)
            if last_key is not None and event_key < last_key:
                raise ValueError(
                    f"non-monotonic csv tick replay ordering detected at {path}: "
                    f"{event_key} < {last_key}"
                )
            last_key = event_key
            yield event
