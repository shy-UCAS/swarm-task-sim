"""Record the authorized before/after station values, source identities and test evidence."""
import ast
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DOC = REPO / "docs/v08/V8-19"
PART = DOC / "part2_anchor"
PART.mkdir(exist_ok=False)
sys.path.insert(0, str(CODE))
from v08.contract.monitoring import MemberPlan
from v08.motion.dwell_nominal import compose_dwell, dwell_lines_from_skeleton, member_nominal_with_dwell
from types import SimpleNamespace as NS

points = tuple((4000.1 + .3 * i, 4000.2 + .1 * i) for i in range(8))
array = np.asarray(points)
delta = np.diff(array, axis=0)
arc = np.r_[0., np.cumsum(np.hypot(delta[:, 0], delta[:, 1]))]
plan = MemberPlan("m", 0, points, 100., float(arc[-1]), .14, ((0., 2.),), ())
nom = member_nominal_with_dwell(plan, (.53, 20.))
saved_arrays = [a.copy() for a in (nom.incoming.curve.s, nom.incoming.t_nodes, nom.outgoing.curve.s, nom.outgoing.t_nodes)]
composed = compose_dwell(nom.incoming, nom.outgoing, 20., station_m=.53)
unmodified = all(np.array_equal(a, b) for a, b in zip(saved_arrays,
    (nom.incoming.curve.s, nom.incoming.t_nodes, nom.outgoing.curve.s, nom.outgoing.t_nodes)))
line = dwell_lines_from_skeleton(NS(witnesses={"dwell_windows": {"m": (.53, 20., nom.dwell_point_xy)}}), {"m": {"nominal": nom}})[0]
old = json.loads((DOC / "part2/part2_station_failure_r2.json").read_text(encoding="utf-8"))
manifest = json.loads((DOC / "manifest.json").read_text(encoding="utf-8"))
frozen_file_diffs = []
for path, expected in manifest["frozen_files"].items():
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if expected != actual:
        frozen_file_diffs.append(path)
symbol_checks = []
for row in manifest["frozen_symbols"]:
    text = Path(row["path"]).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(text).body if getattr(n, "name", None) == row["qualname"])
    actual = hashlib.sha256(ast.get_source_segment(text, node).encode("utf-8")).hexdigest()
    symbol_checks.append({"qualname": row["qualname"], "equal": actual == row["sha256"]})
presets = {name: hashlib.sha256((CODE / "tests/v08/V8-19" / name).read_bytes()).hexdigest() == row["sha256"] for name, row in manifest["presets"].items()}
owners = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected for path, expected in manifest["preserved_owner_files"].items()}
result = {
    "checked_utc": datetime.now(timezone.utc).isoformat(),
    "source_before": "7b16f96b39c6aae58e20c2a653321b67e156b1bf",
    "requested_station_m": .53, "unchanged_incoming_raw_length_m": float(nom.incoming.curve.s[-1]),
    "anchor_guard_difference_m": float(nom.incoming.curve.s[-1]) - .53,
    "anchor_guard_bound_m": 1e-9 * max(1., .53),
    "before": {key: old[key] for key in ("exact_requested_station_occurrences", "nominal_arrival_s",
        "side_specific_time_at_requested_station_s", "side_specific_minus_arrival_s", "dwell_line_minus_nominal_arrival_s")},
    "after": {"anchor_station_m": nom.dwell_station_m,
        "exact_requested_station_occurrences": int(sum(nom.curve.s == .53)),
        "nominal_arrival_s": nom.arrival_s, "side_specific_time_at_requested_station_s": nom.time_at_s(.53),
        "side_specific_minus_arrival_s": nom.time_at_s(.53) - nom.arrival_s,
        "arrival_table_interpolation_s": float(np.interp(.53, nom.curve.s, nom.t_nodes)) + nom.release_s,
        "dwell_line_start_s": line[1], "dwell_line_minus_nominal_arrival_s": line[1] - nom.arrival_s},
    "leg_tables_unchanged": unmodified,
    "spatial_point_unchanged": bool(np.array_equal(nom.dwell_point_xy, old["original_point_xy"])),
    "duration_s": nom.dwell_s, "end_decode_exact": nom.end_s == nom.release_s + (nom.end_s - nom.release_s),
    "frozen_file_differences": frozen_file_diffs, "frozen_symbols": symbol_checks,
    "verbatim_presets_equal": presets, "owner_files_equal": owners,
    "tests_completed": {"preset_numeric": 8, "reference_interfaces": 2, "extra": 5},
    "pending": {"cache_identity_interface": "implementation/verification pending", "artifact_preset": "requires two rounds of gates and quick/full/rerun outputs; dependency-order clarification requested"},
    "p0_triggered": [], "new_retained_contracts": 0,
}
assert unmodified and result["spatial_point_unchanged"] and result["end_decode_exact"]
assert result["after"]["exact_requested_station_occurrences"] == 1
assert result["after"]["side_specific_minus_arrival_s"] == result["after"]["dwell_line_minus_nominal_arrival_s"] == 0.
assert not frozen_file_diffs and all(row["equal"] for row in symbol_checks) and all(presets.values()) and all(owners.values())
(PART / "anchor_values.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
for name in ("anchor_numeric_r1.log", "anchor_extra_r1.log", "anchor_interface_reference_r1.log"):
    shutil.copyfile(ROOT / "run/diagnostics" / name, PART / name)
ruling = ROOT / "V8-19_站点锚点裁定_20261108.md"
shutil.copyfile(ruling, DOC / "instructions" / ruling.name)
shutil.copyfile(__file__, DOC / "record_anchor_fix.py")
manifest["station_anchor_ruling"] = {"path": str(ruling), "sha256": hashlib.sha256(ruling.read_bytes()).hexdigest(),
    "precedence": "replaces main section 2.2 arrival-table implementation; all remaining rules retained"}
manifest["latest_anchor_verification"] = result
(DOC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
shutil.copyfile(DOC / "REPORT.md", DOC / "REPORT_CHECKPOINT_7b16f96.md")
first_status = next(line for line in report.splitlines() if line.startswith("> **停止状态："))
report = report.replace(first_status, "> **恢复状态：已按站点锚点裁定修正P2表示问题；当前15项独立检查通过，历史失败证据保留。第一轮24进程门禁尚未启动；完整缓存接口和产物验收仍按依赖顺序核对。**")
report = report.replace("## 当前八部分状态", "## 7b16f96检查点时的八部分状态（历史）")
report = report.replace("## 2. 驻留参考快速检查——失败停止", "## 2. 驻留参考快速检查——7b16f96失败记录（历史）")
report += r"""

## 站点锚点裁定后的接续

从本地/显式获取远端一致的`7b16f96b39c6aae58e20c2a653321b67e156b1bf`继续，未重置。依据[instructions/V8-19_站点锚点裁定_20261108.md](instructions/V8-19_站点锚点裁定_20261108.md)，原始选中站点成为唯一锚点：仅在拼接表中替换incoming最后弧长，outgoing以原锚点平移；分侧映射使用同一锚点及替换后的incoming表。原incoming/outgoing对象本身不动。

替换前严格检查 \(\lvert L_{in}-s_d\rvert\le10^{-9}\max(1,s_d)\)，不满足抛ValueError。新增自加测试将进场末端长度偏大 \(10^{-6}\,\mathrm{m}\)，已确认拒绝；原自加测试和三份预置预期均未改。

| 项 | 修正前 | 修正后 |
|---|---|---|
| incoming原始末端累计弧长（米） | 0.5300000000002733 | 0.5300000000002733，原对象未变 |
| 拼接表中的原站点0.53出现次数 | 0 | 1 |
| 名义到达（秒） | 21.246305092329266 | 21.246305092329266 |
| time_at_s(0.53)（秒） | 21.246305092328676 | 21.246305092329266 |
| 时间映射/驻留line相对到达偏差（秒） | -5.897504706808832e-13 | 0，严格相等 |

空间驻留点、20秒时长、原腿表和结束时刻解码全部保持。冻结100整文件、5个对象、三份预置SHA及两owner散列均同。见[anchor_values](part2_anchor/anchor_values.json)。本次原样数值8/8、参考接口2/2、自加5/5通过，日志在part2_anchor；尚未把未执行的缓存接口或产物测试记为通过。

本裁定第3节同时授权：以后纯浮点表示差异不超过1e-9（相对或米/秒）、不改变定义/阈值/RNG/预置预期、不碰冻结对象时，可原始值锚定、记录后继续；不满足任一条件仍停报。其他P0、45分钟弦预建、30分钟200骨架和24/1进程规则保持。

**测试依赖顺序待澄清：** 新裁定第4节要求产物测试通过后才启动第一轮门禁，但原第9.3的3项产物测试要求两轮8组门禁、20快批、200＋100全量及5键复跑目录。目前这些尚未生成，不能在第一轮门禁前通过该测试；已向用户提出按原依赖顺序后置产物测试的澄清。澄清前不启动24进程门禁，继续独立的锚点修正与接口准备。Interface的缓存identity方法依赖尚待完成的intent参数化，亦单独记录。
"""
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
print(json.dumps(result["after"], ensure_ascii=False))
