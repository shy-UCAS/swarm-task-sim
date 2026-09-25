"""Summarize retained integration runs without modifying their data."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
summary = []
for directory in sorted((ROOT / "runs").glob("*")):
    if not (directory / "metadata.json").is_file():
        continue
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    quality_path = directory / "quality.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    arrival_spread = {}
    for phase in metadata["scenario"]["phases"]:
        times = [e["t"] for e in events if e["event"] == "phase_finished" and e.get("phase") == phase["name"]]
        if len(times) == len(metadata["scenario"]["vehicles"]):
            arrival_spread[phase["name"]] = max(times) - min(times)
    summary.append(dict(run=directory.name, status=metadata["status"], error=metadata.get("error"),
                        vehicle_count=len(metadata["scenario"]["vehicles"]), elapsed_s=metadata.get("elapsed_s"),
                        start_spread_s=metadata.get("phase_start_spread_s"), arrival_spread_s=arrival_spread,
                        quality=quality, all_processes_reaped=all(v is not None for v in metadata.get("cleanup", {}).values())))
output = ROOT / "verification_summary.json"
output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
