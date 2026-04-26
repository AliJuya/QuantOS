from __future__ import annotations

from pathlib import Path
from typing import Iterator, Mapping, Any

import pyarrow.parquet as pq


def iter_parquet_rows(
    *,
    paths: tuple[Path, ...],
    required_columns: list[str],
    batch_size: int,
) -> Iterator[tuple[Path, Mapping[str, Any]]]:
    for path in paths:
        parquet_file = pq.ParquetFile(path)
        available_columns = set(parquet_file.schema.names)
        selected_columns = [column for column in required_columns if column in available_columns]
        for batch in parquet_file.iter_batches(
            columns=selected_columns,
            batch_size=batch_size,
            use_threads=False,
        ):
            batch_data = batch.to_pydict()
            for index in range(batch.num_rows):
                row: dict[str, Any] = {}
                for column in required_columns:
                    if column in batch_data:
                        row[column] = batch_data[column][index]
                    else:
                        row[column] = None
                yield path, row
