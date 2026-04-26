from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from qcore.domain.contracts import EventHandler


def _normalize_emitted(value: object | Iterable[object] | None) -> list[object]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, dict)):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return [value]


@dataclass(slots=True)
class SynchronousEventBus:
    _handlers: dict[type[object], list[EventHandler]] = field(default_factory=lambda: defaultdict(list))
    _dispatch_cache: dict[type[object], tuple[EventHandler, ...]] = field(default_factory=dict)

    def subscribe(self, event_type: type[object], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        self._dispatch_cache.clear()

    def publish(self, event: object) -> tuple[object, ...]:
        queue: deque[object] = deque([event])
        published: list[object] = []
        while queue:
            current = queue.popleft()
            published.append(current)
            for handler in self._handlers_for(type(current), current):
                emitted = handler(current)
                queue.extend(_normalize_emitted(emitted))
        return tuple(published)

    def _handlers_for(self, concrete_type: type[object], current: object) -> tuple[EventHandler, ...]:
        cached = self._dispatch_cache.get(concrete_type)
        if cached is not None:
            return cached

        handlers: list[EventHandler] = []
        for subscribed_type, subscribed_handlers in self._handlers.items():
            if isinstance(current, subscribed_type):
                handlers.extend(subscribed_handlers)
        resolved = tuple(handlers)
        self._dispatch_cache[concrete_type] = resolved
        return resolved
