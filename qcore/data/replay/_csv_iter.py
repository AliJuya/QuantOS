from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator, Mapping


def iter_csv_rows(
    *,
    paths: tuple[Path, ...],
    required_columns: list[str],
) -> Iterator[tuple[Path, Mapping[str, str]]]:
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"csv file has no header: {path}")
            missing = [column for column in required_columns if column not in reader.fieldnames]
            if missing:
                raise ValueError(f"csv file {path} is missing required columns: {', '.join(missing)}")
            for row in reader:
                yield path, row
