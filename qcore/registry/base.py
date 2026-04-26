from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class ComponentRegistry(Generic[T]):
    def __init__(self, name: str) -> None:
        self._name = name
        self._factories: dict[str, Callable[..., T]] = {}

    def register(self, kind: str, factory: Callable[..., T]) -> None:
        self._factories[kind] = factory

    def build(self, cfg: dict[str, Any], **ctx: Any) -> T:
        kind = cfg.get("kind")
        if kind is None:
            raise ValueError(f"{self._name} registry: config missing 'kind'")
        factory = self._factories.get(str(kind))
        if factory is None:
            available = sorted(self._factories)
            raise KeyError(f"{self._name} registry: unknown kind '{kind}' (available: {available})")
        return factory(cfg, **ctx)

    def kinds(self) -> list[str]:
        return sorted(self._factories)
