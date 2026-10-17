"""FE-P0 G2: exact baseline methods, adversarial boundaries and real S1.5 views."""
from copy import deepcopy
import json
from pathlib import Path
import random
import unittest

from task_v07.geometry import geometry_facts
from task_v07.visibility import ExactVisibilityPlanner, _box

PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE = PROJECT/"docs/v07/perf"


class ReferencePlanner(ExactVisibilityPlanner):
    # Verbatim 09279c2 methods; only names changed. No bounding-box calls.
    def ref_free(self, point):
        key=tuple(point)
        if key in self._free_cache:
            return self._free_cache[key]
        answer=bool(geometry_facts(self.world, point)["signed_distance_m"] <= 1e-8) and all(
            geometry_facts(g, point)["signed_distance_m"] >= self.margin-1e-8 for g in self.obstacles)
        self._free_cache[key]=answer
        return answer


    def ref_visible(self, start, finish):
        # World is convex; endpoint containment implies whole-segment containment.
        if not self.free(start) or not self.free(finish):
            return False
        if tuple(start) == tuple(finish):
            return True
        return all(geometry_facts(g,[start,finish],footprint=True)["clearance_m"] >= self.margin-1e-8
                   for g in self.obstacles)


    free = ref_free
    _visible_uncached = ref_visible


def scene_for(geometries):
    return {"world": {"geometry": {"type": "Polygon", "vertices_m": [[-500., -500.], [500., -500.], [500., 500.], [-500., 500.]]}},
            "entities": [{"id": str(i), "type": "hard_constraint_obstacle", "geometry": g} for i, g in enumerate(geometries)]}


def polygon(x, y, buffer=None):
    g = {"type": "Polygon", "vertices_m": [[x-25., y-20.], [x+25., y-20.], [x+25., y+20.], [x-25., y+20.]]}
    if buffer is not None: g.update(type="BufferedPolygon", buffer_m=buffer)
    return g


def real_views():
    captured = json.loads((EVIDENCE/"FE_P0_real_view.json").read_text(encoding="utf-8"))
    scene = json.loads((EVIDENCE/"FE_P0_real_scene.json").read_text(encoding="utf-8"))
    # task_v07.planning.role_planner(scene, survey=False) passes this raw scene with margin 35.
    return [("real_effective", captured["view"], captured["margin_m"]), ("real_raw", scene, 35.)]


class BroadphaseTests(unittest.TestCase):
    def test_real_graphs_exact(self):
        for label, view, margin in real_views():
            actual, reference = ExactVisibilityPlanner(view, margin), ReferencePlanner(view, margin)
            self.assertEqual(actual.vertices, reference.vertices, label)
            self.assertEqual(actual.adjacency, reference.adjacency, label)
            self.assertGreater(actual._broadphase_stats["skipped"], 0)
            print("GRAPH_PARITY " + json.dumps({"view": label, "vertices": len(actual.vertices), "stats": actual._broadphase_stats}), flush=True)

    def test_tangencies_and_expanded_polygon_boundaries(self):
        shapes = [{"type": "Circle", "center_m": [0., 0.], "radius_m": 40.},
                  polygon(0., 0.), polygon(0., 0., 8.), polygon(0., 0., -8.), polygon(0., 0., 0.)]
        for margin in (0., 35.):
            for g in shapes:
                view = scene_for([g])
                actual, reference = ExactVisibilityPlanner(view, margin), ReferencePlanner(view, margin)
                top = 40. if g["type"] == "Circle" else 20.+g.get("buffer_m", 0.)
                for delta in (-1e-7, 0., 1e-7):
                    y = top+margin+delta
                    start, finish = [-100., y], [100., y]
                    self.assertEqual(actual.visible(start, finish), reference.visible(start, finish), (g, margin, delta))
                    self.assertEqual(actual.free([0., y]), reference.free([0., y]), (g, margin, delta))
                if g["type"] == "Circle":
                    self.assertTrue(actual.visible([-100., top+margin], [100., top+margin]))
                    self.assertFalse(actual.visible([-100., top+margin-1e-7], [100., top+margin-1e-7]))
        self.assertIsNone(_box({"type": "unsupported"}))

    def test_random_exact_predicates(self):
        # Overlapping circles and polygons plus positive, negative and zero buffers.
        synthetic = scene_for([{"type": "Circle", "center_m": [0., 0.], "radius_m": 40.},
                               {"type": "Circle", "center_m": [30., 0.], "radius_m": 40.},
                               polygon(-150., 100.), polygon(-130., 110., 10.),
                               polygon(180., 100., -10.), polygon(180., -100., 0.)])
        cases = [("synthetic_0", synthetic, 0.), ("synthetic_35", synthetic, 35.), *real_views()]
        for label, view, margin in cases:
            actual, reference = ExactVisibilityPlanner(view, margin), ReferencePlanner(view, margin)
            coords = view["world"]["geometry"]["vertices_m"]
            bounds = [(min(p[i] for p in coords), max(p[i] for p in coords)) for i in (0, 1)]
            rng = random.Random(20261016)
            def point(): return [rng.uniform(*bounds[i]) for i in (0, 1)]
            for index in range(20000):
                start, finish = point(), point()
                self.assertEqual(actual.visible(start, finish), reference.visible(start, finish),
                                 {"case": label, "segment": index, "start": start, "finish": finish})
            for index in range(5000):
                p = point()
                self.assertEqual(actual.free(p), reference.free(p), {"case": label, "point": index, "xy": p})
            print("RANDOM_PARITY " + json.dumps({"case": label, "segments": 20000, "points": 5000,
                                                  "equal": True, "stats": actual._broadphase_stats}), flush=True)


if __name__ == "__main__":
    unittest.main()
