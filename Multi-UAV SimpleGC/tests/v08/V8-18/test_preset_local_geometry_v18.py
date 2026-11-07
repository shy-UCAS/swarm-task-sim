"""V8-18预置测试，未经运行；项目接口/真实场景层。"""
import json
import os
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import shapely

from v08.motion import optimize as O
from v08.motion.layer_limits import constraints_for_task
from v08.contract.monitoring import GroupSpec, TaskSpec
from v08.contract.single_intent import feint_mission
from v08.motion.formation import formation_slots
from v08.motion import feint_chords as FC
from v08.motion import feint_turn as FT
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey
from v08.scene.context import load_context


def envpath(key):
    if not os.environ.get(key):
        raise unittest.SkipTest(key + "未设置，验收未执行")
    return Path(os.environ[key]).resolve()


def circle(r):
    return dict(type="Circle", center_m=[0.0, 0.0], radius_m=float(r))


def context():
    f = NS(id="t", geometry=circle(20), center=(0.0, 0.0),
           layers={"warning": circle(300), "alert": circle(160), "protected": circle(100)},
           offsets={"warning": 280., "alert": 140., "protected": 80.})
    return NS(facilities=[f], facility_by_id={"t": f}, world=circle(4000), obstacles=[],
              params={"world_margin_m": 35., "obstacle_margin_m": 35.,
                      "forbidden_margin_m": 10., "pre_entry_warning_clearance_m": 10.,
                      "alignment_length_m": 100., "curve_spacing_m": 0.5},
              extra={}, inputs={"sha256": {}}, cold_build=nullcontext,
              family=NS(initial_states={"m": {}}), field=lambda *a, **k: None)


class InterfacePreset(unittest.TestCase):
    def test_existing_feint_boundaries(self):
        c = constraints_for_task(context(), TaskSpec("task0", "feint", "t"))
        # S：warning原键在先、再追加alert；feint base禁止protected，不禁止目标alert。
        self.assertEqual(list(c["crossing_boundaries"]), ["t", "__crossing__t::alert"])
        self.assertEqual([(x.name, x.sense, x.minimum_m) for x in c["base"]],
                         [("world", -1, 35.), ("protected:t", 1, 10.)])

    def test_outer_solver_receives_turns(self):
        nom = NS(curve=NS(s=np.array([0., 10., 30.])),
                 t_nodes=np.array([0., 2., 6.]), release_s=20.)
        maps = {"m": {"nominal": nom}}
        for intent in ("feint", "transit", "intrusion"):
            with self.subTest(intent=intent):
                rows = {"m": [("u", 5., 20., "turn_u_min_m")]} if intent == "feint" else {}
                sk = NS(witnesses={"target_id": "t", "intent": intent, "turn_ranges": rows}, members={})
                sol = NS(ok=False, reason="fixture", references={}, diagnostics={})
                with patch("v08.motion.skeleton.references_from_skeleton", return_value=((), (), maps)), \
                     patch("v08.motion.skeleton.merge_semantic_lines", return_value=()), \
                     patch.object(O, "solve_joint", return_value=sol) as solve:
                    out = O._optimize_segment_intent(context(), sk, None, {"knot_s": 1.}, intent)
                # 独立预期同9.1解析值；旧意图应为空，测真实外层而非只测helper。
                want = (("m", 21., 24., 15.),) if intent == "feint" else ()
                self.assertEqual(solve.call_args.args[0].turns, want)
                self.assertIs(out["problem"], solve.call_args.args[0])


class SceneGatePreset(unittest.TestCase):
    def test_all_candidates_coarse_equals_exact(self):
        entries_doc = json.loads(envpath("V8_18_DEVSET").read_text(encoding="utf-8"))
        entries = entries_doc["families"] if isinstance(entries_doc, dict) else entries_doc
        data, cache = envpath("V8_18_DATA_ROOT"), envpath("V8_18_CACHE")
        groups, checked, mismatch, first = [], 0, 0, None
        for e in sorted(entries, key=lambda e: e["order"])[:5]:
            ctx = load_context(e, data_root=data, cache_dir=cache)
            mission = feint_mission(ctx, sample_common(ctx.family, 0))
            g0, task = mission.groups[0], mission.tasks[0]
            ids = sorted(ctx.family.initial_states)
            for n in (1, (len(ids) + 1) // 2, len(ids)):
                group = GroupSpec(g0.group_id, tuple(ids[:n]), g0.speed_profile, "column")
                key = RngKey(ctx.family.family_id, 0, "formation", mission=0,
                             group=g0.group_id, segment=0)
                slots = formation_slots(group, ctx.family, key, formation="column")
                count = 0
                for cell, candidate in FC.iter_certification_cases(ctx, task, slots):
                    # 独立oracle为S精确几何组成的exact路径；禁止其调用粗筛。
                    exact = FT.certify_candidate(ctx, task, slots, cell, candidate, mode="exact")
                    fast = FT.certify_candidate(ctx, task, slots, cell, candidate, mode="upper_literal")
                    if bool(exact["feasible"]) != bool(fast["feasible"]):
                        mismatch += 1
                        if first is None:
                            first = (e["order"], n, cell, candidate, exact, fast)
                    count += 1
                # U要求全集对照，空迭代不能冒充通过；无可行者仍应枚举拒绝候选。
                self.assertGreater(count, 0, (e["order"], n))
                groups.append((e["order"], n))
                checked += count
        # 固定前五族N=6,9,6,7,9来自S登记输入，手算三种人数。
        self.assertEqual(groups, [(1, 1), (1, 3), (1, 6), (2, 1), (2, 5), (2, 9),
                                  (3, 1), (3, 3), (3, 6), (4, 1), (4, 4), (4, 7),
                                  (5, 1), (5, 5), (5, 9)])
        self.assertGreater(checked, 0)
        # U D.3规范要求0。若按字面粗筛失败，保留反例走12.1裁定，不能改预期。
        self.assertEqual(mismatch, 0, first)


if __name__ == "__main__":
    unittest.main()
