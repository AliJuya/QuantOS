from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(config)

    if "strategy" in normalized and "strategies" not in normalized:
        normalized["strategies"] = _normalize_component_list(normalized.pop("strategy"))
    elif "strategies" in normalized:
        normalized["strategies"] = _normalize_component_list(normalized["strategies"])

    if "gate" in normalized and "gates" not in normalized:
        normalized["gates"] = _normalize_component_list(normalized.pop("gate"))
    elif "gates" in normalized:
        normalized["gates"] = _normalize_component_list(normalized["gates"])

    if "models" not in normalized:
        normalized["models"] = []
    else:
        normalized["models"] = _normalize_component_list(normalized["models"])

    if "gates" not in normalized:
        normalized["gates"] = []

    return normalized


def _normalize_component_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        raise ValueError("component config must be a mapping or list of mappings")

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("component list items must be mappings")
        normalized.append(item)
    return normalized
