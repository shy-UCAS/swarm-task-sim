"""Read-only reproduction of the failed arc-station invariant; no solver or production run."""
import ast
import hashlib
import json
import sys
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
sys.path.insert(0, str(CODE))
from v08.contract.monitoring import MemberPlan
from v08.motion.dwell_nominal import dwell_lines_from_skeleton, member_nominal_with_dwell

points = tuple((4000.1 + .3 * index, 4000.2 + .1 * index) for index in range(8))
plan = MemberPlan("m", 0, points, 100., 3., .14, ((0., 2.),), ())
nom = member_nominal_with_dwell(plan, (.53, 20.))
delta = np.diff(np.asarray(points), axis=0)
original_s = np.r_[0.0, np.cumsum(np.hypot(delta[:, 0], delta[:, 1]))]
original_point = [float(np.interp(.53, original_s, np.asarray(points)[:, axis])) for axis in (0, 1)]
valid_plan = replace(plan, end_s=float(original_s[-1]))
valid_nom = member_nominal_with_dwell(valid_plan, (.53, 20.))
sk = NS(witnesses={"dwell_windows": {"m": (.53, 20., original_point)}})
line = dwell_lines_from_skeleton(sk, {"m": {"nominal": nom}})[0]
snapshot = json.loads((REPO / "docs/v08/V8-19/snapshot_part1.json").read_text(encoding="utf-8"))
symbol_checks = []
for record in snapshot["frozen_symbols"]:
    source = Path(record["path"]).read_text(encoding="utf-8")
    node = next(node for node in ast.parse(source).body if getattr(node, "name", None) == record["qualname"])
    actual = hashlib.sha256(ast.get_source_segment(source, node).encode("utf-8")).hexdigest()
    symbol_checks.append({**record, "actual_sha256": actual, "equal": actual == record["sha256"]})
preserved = []
for path, expected in snapshot["preserved_owner_files"].items():
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    preserved.append({"path": path, "expected_sha256": expected, "actual_sha256": actual, "equal": expected == actual})
manifest = json.loads((REPO / "docs/v08/V8-19/manifest.json").read_text(encoding="utf-8"))
preset_checks = {name: hashlib.sha256((CODE / "tests/v08/V8-19" / name).read_bytes()).hexdigest() == row["sha256"]
                 for name, row in manifest["presets"].items()}
result = {
    "checked_utc": datetime.now(timezone.utc).isoformat(),
    "classification": "part2_reference_quickcheck_failed; not an old-intent bytes or retained-output P0",
    "input": {"member_plan": {"member_id": "m", "segment_index": 0, "curve_xy": points,
               "altitude_m": 100., "end_s": 3., "release_delay_s": .14, "speed_breaks": [[0., 2.]], "stops": []},
               "station_m": .53, "duration_s": 20.},
    "requested_station_hex": float(.53).hex(),
    "recomputed_incoming_length_m": nom.dwell_station_m,
    "recomputed_incoming_length_hex": nom.dwell_station_m.hex(),
    "station_roundoff_m": nom.dwell_station_m - .53,
    "composite_stations_m": nom.curve.s.tolist(),
    "exact_requested_station_occurrences": int(sum(nom.curve.s == .53)),
    "nominal_arrival_s": nom.arrival_s,
    "nominal_departure_s": nom.departure_s,
    "side_specific_time_at_requested_station_s": nom.time_at_s(.53),
    "side_specific_minus_arrival_s": nom.time_at_s(.53) - nom.arrival_s,
    "arrival_table_interpolation_s": float(np.interp(.53, nom.curve.s, nom.t_nodes)) + nom.release_s,
    "dwell_line_start_s": line[1],
    "dwell_line_minus_nominal_arrival_s": line[1] - nom.arrival_s,
    "original_point_xy": original_point, "composite_dwell_point_xy": nom.dwell_point_xy,
    "point_unchanged": bool(np.array_equal(original_point, nom.dwell_point_xy)),
    "end_decode_exact": nom.end_s == nom.release_s + (nom.end_s - nom.release_s),
    "consistent_end_s_reproduction": {
        "end_s_m": valid_plan.end_s,
        "complete_curve_length_m": float(original_s[-1]),
        "recomputed_station_m": valid_nom.dwell_station_m,
        "exact_requested_station_occurrences": int(sum(valid_nom.curve.s == .53)),
        "arrival_s": valid_nom.arrival_s,
        "mapped_arrival_s": valid_nom.time_at_s(.53),
        "same_reference_values": bool(np.array_equal(nom.curve.s, valid_nom.curve.s)
                                      and nom.arrival_s == valid_nom.arrival_s),
        "note": "Original self-test used a noncanonical unused MemberPlan.end_s; setting it to the complete curve length leaves the station failure identical. Original test/log retained unchanged.",
    },
    "frozen_symbols": symbol_checks, "owner_files": preserved, "verbatim_presets_equal": preset_checks,
    "production_stages_started": [], "byte_gates_started": [], "new_retained_contracts": 0,
    "proposed_direction_not_applied": "Keep the selected original station as the unique arrival-table anchor and use that same explicit anchor for side selection; do not spatially snap Pd, resample Td, relax tolerance, or modify preset assertions. Requires review before changing the failed checkpoint.",
}
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "run/diagnostics/part2_station_failure_r1.json"
if out.exists():
    raise FileExistsError(out)
out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({key: result[key] for key in ("recomputed_incoming_length_m", "station_roundoff_m", "exact_requested_station_occurrences",
    "nominal_arrival_s", "nominal_departure_s", "side_specific_time_at_requested_station_s", "side_specific_minus_arrival_s",
    "dwell_line_minus_nominal_arrival_s", "point_unchanged", "end_decode_exact", "verbatim_presets_equal")}, ensure_ascii=False))
print(json.dumps({"frozen_symbols_equal": all(row["equal"] for row in symbol_checks), "owner_files_equal": all(row["equal"] for row in preserved)}))
