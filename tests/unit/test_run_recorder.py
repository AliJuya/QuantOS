from __future__ import annotations

from pathlib import Path

from qcore.analytics.recorder import RunRecorder


def test_run_recorder_resets_existing_run_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "existing-run"
    run_dir.mkdir(parents=True)
    stale = run_dir / "equity.jsonl"
    stale.write_text("stale-data\n", encoding="utf-8")

    recorder = RunRecorder(run_dir)
    recorder.close()

    assert run_dir.exists()
    assert not stale.exists()

