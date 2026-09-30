"""Read-only real-log loading and offscreen GUI checks; never start SITL."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt5 import QtCore, QtGui, QtWidgets, QtTest
from replay_viewer.data import load_replay
from replay_viewer.window import ReplayWindow, configure_application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QtWidgets.QApplication([])
    configure_application(app)
    window = ReplayWindow()
    window.show()
    paths = sorted((ROOT / "verification/v03_integration_20260930/runs").glob("*/metadata.json"))
    for name in ("v03_pilot_20260930", "v03_pilot_remaining_20260930"):
        ledger = json.loads((ROOT / "verification" / name / "attempt_ledger.json").read_text(encoding="utf-8"))
        paths += [Path(a["run_directory"]) / "metadata.json" for m in ledger["missions"] for a in m["attempts"]]
    report = {"runs": [], "screenshots": [], "new_sitl_launches": 0}
    captured = set()
    for metadata in paths:
        run = metadata.parent
        files = [run / name for name in ("metadata.json", "scenario.json", "samples.csv", "events.jsonl", "analysis_latest.json") if (run / name).exists()]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        data = load_replay(run)
        window.apply_data(data)
        window.seek(min(data.duration, data.mission_start + 50))
        app.processEvents()
        n = len(data.agent_ids)
        assert window.table.rowCount() == n
        assert all(len(window.arrays[a][0]) >= len(data.tracks[a].samples) for a in data.agent_ids)
        # The view must never change any of these original run files.
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        assert before == after
        record = dict(path=str(run), agents=n, status=data.metadata["status"], duration=data.duration,
                      samples=sum(len(t.samples) for t in data.tracks.values()), warnings=data.warnings,
                      evidence_unchanged=True, source_sha256=before)
        report["runs"].append(record)
        shot_key = "failed" if data.metadata["status"] != "completed" else str(n)
        if shot_key not in captured:
            screenshot = args.output / f"replay_{shot_key}.png"
            assert window.grab().save(str(screenshot))
            report["screenshots"].append(str(screenshot))
            captured.add(shot_key)
    assert len(report["runs"]) == 15, "Expected five matrix runs and ten pilot runs"
    # Exercise actual worker-thread load and control interactions, not just apply_data.
    window.load_path(ROOT / "missions/recon_shared_3uav.json")
    deadline = time.monotonic() + 10
    while window.worker is not None and time.monotonic() < deadline:
        QtTest.QTest.qWait(20)
    assert window.worker is None, "Background load did not finish"
    assert not window.data.is_run and not window.play.isEnabled()
    assert window.grab().save(str(args.output / "plan_preview.png"))
    report["screenshots"].append(str(args.output / "plan_preview.png"))
    legacy = ROOT / "tasks/task_point_visit_3uav.json"
    if not legacy.exists():
        legacy = ROOT / "scenarios/task_point_visit_3uav.json"
    window.apply_data(load_replay(legacy))
    assert not window.play.isEnabled()
    report["legacy_plan_preview"] = str(legacy)
    report["async_task_load"] = True
    window.close()
    (args.output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(runs=len(report["runs"]), screenshots=report["screenshots"], output=str(args.output)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
