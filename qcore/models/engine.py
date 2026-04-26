from __future__ import annotations

from dataclasses import dataclass, field

from qcore.domain.events import BarCloseEvent
from qcore.models.store import ModelStore
from qcore.models.view import ModelView


@dataclass(slots=True)
class ModelEngine:
    models: tuple[object, ...]
    store: ModelStore = field(default_factory=ModelStore)

    @property
    def view(self) -> ModelView:
        return ModelView(self.store)

    def on_bar_close(self, event: BarCloseEvent) -> list[object]:
        emitted: list[object] = []
        for model in self.models:
            produced = model.on_bar_close(event)
            if produced is None:
                continue
            if isinstance(produced, list):
                values = produced
            elif isinstance(produced, tuple):
                values = list(produced)
            else:
                values = [produced]
            for snapshot in values:
                try:
                    self.store.store_snapshot(snapshot)
                except TypeError:
                    pass
            emitted.extend(values)
        return emitted

    def stats(self) -> dict[str, object]:
        return {
            "models": [model.__class__.__name__ for model in self.models],
            "store": self.store.stats(),
        }
