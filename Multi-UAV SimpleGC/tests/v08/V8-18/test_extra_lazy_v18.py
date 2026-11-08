"""2026-11-08 裁定自加测试：按需判空、全空退让、真实合同的 1/2 进程字节一致。"""
import hashlib
import json
import multiprocessing as mp
import os
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from v08.motion import feint_chords as FC
from v08.motion.intents import feint as F
from v08.sampler.keys import RngKey, rng_for


def witness():
    return dict(A_m=0.0, kind="u", side=1, radius_m=20.0, collect_D_compatible=[100.0], terminal_x=500.0)


class LazyCells(unittest.TestCase):
    def test_fixed_permutation_stops_at_first_nonempty(self):
        calls = []

        class RNG:
            def permutation(self, n):
                self_n.append(n)
                return np.array([4, 1, 5, 0, 3, 2])

        # 以裁定明确列出的 4（空）→1（非空）、选中 1、两次判空为预期。
        # 原文“第 2、5 个”与该序列有序数歧义；采用非空下标 1、5，REPORT 登记。
        def required_certify(cell):
            calls.append(cell)
            return {"cell": cell} if cell in (1, 5) else None

        self_n = []
        index, record, walked = FC.first_nonempty(list(range(6)), required_certify, RNG())
        self.assertEqual(index, 1)
        self.assertEqual(record, {"cell": 1})
        self.assertEqual(walked, [4, 1])
        self.assertEqual(calls, [4, 1])
        self.assertEqual(self_n, [6])

    def test_all_empty_advances_to_next_probe(self):
        ctx = NS(extra={}, family=NS(lateral_spacing_m=10.0))
        group = NS(member_ids=("a", "b"), group_id="g", formation_prior="abreast")
        task = NS(target_id="t")
        key = RngKey("fixture", 0, "shape", mission=0, group="g", segment=0)
        calls, permutations, orders = [], [], []
        cells = [{"theta_idx": i, "h_m": 0.0} for i in range(3)]

        class RNG:
            def permutation(self, n):
                permutations.append(n)
                return np.arange(n)

        def candidates(ctx, target, slots):
            orders.append(slots.order)
            return {"cells": cells, "query_id": slots.realized, "n_cells": 3, "reasons": {}}

        def certify(ctx, task, slots, cell, **kwargs):
            calls.append((slots.realized, cell["theta_idx"]))
            return witness() if slots.realized == "column" else None

        steps, telemetry = [], []
        with patch.object(F, "retreat_chain", return_value=("abreast", "column")), \
             patch.object(FC, "candidate_cells", side_effect=candidates), \
             patch.object(FC, "first_feasible", side_effect=certify):
            got = F.select_formation(ctx, group, task, key, RNG(), steps, telemetry)
        self.assertEqual(got["slots"].realized, "column")
        self.assertEqual(calls, [("abreast", 0), ("abreast", 1), ("abreast", 2), ("column", 0)])
        self.assertEqual([s["nonempty_position"] for s in steps], [None, 1])
        self.assertEqual([s["cells_examined"] for s in steps], [3, 1])
        self.assertEqual(permutations, [3, 3])
        self.assertEqual(orders[0], orders[1])

    def test_memory_hits_preserve_selection_and_rng(self):
        ctx = NS(extra={})
        key = RngKey("fixture", 0, "shape", mission=0, group="g", segment=0)
        FC.begin_contract(ctx, key)
        cells = [{"theta_idx": i, "h_m": 0.0} for i in range(6)]
        doc = {"cells": cells, "query_id": "q", "n_cells": 6, "reasons": {}}
        with patch.object(FC, "candidate_cells", return_value=doc), \
             patch.object(FC, "first_feasible", side_effect=lambda c, t, s, cell, **kw:
                          witness() if cell["theta_idx"] == 1 else None) as certify:
            cold_rng, warm_rng = rng_for(key), rng_for(key)
            cold = FC.sample_cell(ctx, NS(target_id="t"), NS(), cold_rng)
            count = certify.call_count
            warm = FC.sample_cell(ctx, NS(target_id="t"), NS(), warm_rng)
            self.assertEqual(certify.call_count, count)
        self.assertEqual(cold["summary"], warm["summary"])
        self.assertEqual(cold["cell"], warm["cell"])
        self.assertEqual(cold_rng.random(), warm_rng.random())


class LocalProcesses(unittest.TestCase):
    def test_same_contract_one_and_two_processes(self):
        from v08.runner.monitoring import load_entries
        from v08.runner.skeleton_transit import _task
        required = ("V8_18_DEVSET", "V8_18_DATA_ROOT", "V8_18_CACHE", "V8_18_LAZY_TEST_OUT")
        if any(not os.environ.get(k) for k in required):
            self.skipTest("真实进程测试输入未设置，验收未执行")
        root = Path(os.environ["V8_18_LAZY_TEST_OUT"])
        root.mkdir(parents=True, exist_ok=False)
        entry = next(e for e in load_entries(os.environ["V8_18_DEVSET"]) if int(e["order"]) == 1)
        results = {}
        for workers in (1, 2):
            out = root / f"workers_{workers}"
            out.mkdir()
            # 伴随键使 2 进程实际并发；o01_d0 是裁定要求比较的同一合同。
            tasks = [(entry, d, os.environ["V8_18_DATA_ROOT"], os.environ["V8_18_CACHE"], str(out), "feint")
                     for d in (0, 2)]
            with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
                rows = list(ex.map(_task, tasks))
            self.assertFalse(any(r.get("error") or r.get("exceptions") for r in rows), rows)
            results[workers] = {r["contract_id"]: {"success": r["success"], "attempts": r["attempts"]} for r in rows}
        comparisons = []
        for cid in ("o01_d0", "o01_d2"):
            trees = []
            for workers in (1, 2):
                folder = root / f"workers_{workers}" / "contracts" / cid
                trees.append({p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()})
            self.assertTrue(trees[0])
            self.assertEqual(set(trees[0]), set(trees[1]))
            for name in sorted(trees[0]):
                self.assertEqual(trees[0][name], trees[1][name], (cid, name))
            comparisons.append({"contract_id": cid, "files": {n: hashlib.sha256(b).hexdigest()
                                                               for n, b in trees[0].items()}, "all_equal": True})
        (root / "comparison.json").write_text(json.dumps({"workers": [1, 2], "exclusions": [],
            "results": results, "comparisons": comparisons}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
