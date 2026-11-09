"""Read-only diagnosis of the first selected-curve quick-check failure; do not alter the test."""
import ast
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DIAG = ROOT / "run/diagnostics"
sys.path.insert(0, str(CODE))

from v08.motion.intents import close_observation as C
from v08.motion.nominal_checks import screen_close_observation_member
from v08.motion.dwell_nominal import member_nominal_with_dwell
from v08.motion.skeleton import reference_guidance
from v08.motion.transit_chords import transit_base
from v08.runner.monitoring import jsonable

test = CODE / "tests/v08/V8-19/test_extra_selected_curve_v19.py"
spec = importlib.util.spec_from_file_location("v19_failed_fixture", test)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
ctx, plan = fixture.fixture()
rng = fixture.FirstChoice()
result = C.add_dwell(ctx, plan, rng)
station, duration, point = result.witnesses["dwell_windows"]["m"]
nom = member_nominal_with_dwell(plan.members["m"], (station, duration), guidance=reference_guidance())
f0 = int(round(nom.release_s * 10))
f1 = int(np.floor((nom.end_s + nom.hold_s) * 10 + 1e-9))
time_us = np.arange(f0, f1 + 1, dtype=np.int64) * 100_000
p, v, _ = nom.pva(time_us / 1e6)
screen = screen_close_observation_member(ctx.facilities, "t", time_us, p, v)
cons = transit_base(ctx, "t", intent=C.INTENT)
margins = C._margins(cons["base"], np.asarray(plan.members["m"].curve_xy))
manifest = json.loads((REPO / "docs/v08/V8-19/manifest.json").read_text(encoding="utf-8"))
frozen = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
          for path, expected in manifest["frozen_files"].items()}
symbols = []
for row in manifest["frozen_symbols"]:
    text = Path(row["path"]).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(text).body if getattr(n, "name", None) == row["qualname"])
    symbols.append({"qualname": row["qualname"], "equal": hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest() == row["sha256"]})
owner = {f"V8-{n}/owner_rerun.json": hashlib.sha256((REPO / f"docs/v08/V8-{n}/owner_rerun.json").read_bytes()).hexdigest()
         for n in (17, 18)}
presets = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in (CODE / "tests/v08/V8-19").glob("test_preset*.py")}
doc = {"utc": datetime.now(timezone.utc).isoformat(), "stage": "part3 quick checkpoint failed",
       "test_sha256": hashlib.sha256(test.read_bytes()).hexdigest(),
       "failed_test": "SelectedCurve.test_analytic_selected_point_and_two_tail_draws",
       "failed_assertion": "self.assertTrue(result.witnesses['screen']['m']['passed'])",
       "test_counts": {"run": 5, "passed": 4, "failed": 1},
       "production_error": False, "suspected_test_expectation_error": True,
       "fixture_curve": {"x_range_m": [-450., 450.], "y_m": 0., "warning_radius_m": 300., "alert_radius_m": 160.,
                         "protected_radius_m": 100., "minimum_alert_clearance_m": -170.},
       "analysis": "The executor-added fixture crosses the origin and violates the pre-existing whole-curve alert constraint. add_dwell correctly records its nominal target max layer 3, not 1. The assertion that all nominal conditions pass was an erroneous fixture expectation. This is not a floating-point representation issue and the test/source have not been changed after failure.",
       "whole_curve_base_min_margins_m": {k: float(np.min(v)) for k, v in margins.items()},
       "selected_dwell": result.proposal["dwell"], "dwell_windows": result.witnesses["dwell_windows"],
       "rng_calls": rng.calls, "screen_conditions": screen["conditions"], "screen_counts": screen["counts"],
       "screen_observation_dwell": screen["observation_dwell"], "screen_revisit": screen["revisit"],
       "screen_revisit_work": screen["revisit_work"], "selected_diagnostics": result.witnesses["dwell_diagnostics"],
       "new_intent_production_contracts_retained": 0, "p0_triggered": [],
       "frozen_files": {"checked": len(frozen), "all_equal": all(frozen.values()), "differences": [p for p, same in frozen.items() if not same]},
       "frozen_symbols": symbols, "owner_sha256": owner, "preset_sha256": presets,
       "not_run_after_checkpoint": ["same-attempt production geometry/RNG audit", "cold/hot serial/parallel cache audit", "maximum actual query measurement", "part3 two-key complete geometry smoke", "part4", "part5", "part6", "part7"]}
assert all(frozen.values()) and all(row["equal"] for row in symbols)
assert owner["V8-17/owner_rerun.json"] == "d9c0022bf84636eb61d0b27a2f65bf3f6c490c738046087036f22b14cdf65bd0"
assert owner["V8-18/owner_rerun.json"] == "0482b9c83fcb274d9fc14177fc8027d73d191afc1e1e8345187cfe74276b8e4b"
(DIAG / "part3_failed_fixture_diagnosis_r1.json").write_text(json.dumps(jsonable(doc), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({k: doc[k] for k in ("test_counts", "screen_conditions", "screen_counts", "whole_curve_base_min_margins_m", "selected_dwell", "p0_triggered")}, ensure_ascii=False))
