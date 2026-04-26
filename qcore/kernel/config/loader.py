from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .normalize import normalize_config


def load_config(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        loaded = json.loads(raw)
    else:
        loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise ValueError(f"config root must be a mapping: {path}")
    return normalize_config(loaded)
