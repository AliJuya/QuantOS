from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from qcore.services.app_builder.live import LiveAppBuilder, LiveRuntime


class PaperAppBuilder(LiveAppBuilder):
    def __init__(
        self,
        config: dict[str, Any],
        config_path: Path,
        project_root: Path,
        run_id: str | None = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path, project_root=project_root, run_id=run_id)

    def build(self) -> LiveRuntime:
        runtime = super().build()
        runtime.manifest = replace(runtime.manifest, app_name="paper_trader", mode="paper")
        return runtime
