"""执行方自加测试：核心模块不得直接或间接导入 shapely 或 scene_v07（其包 __init__ 会导入 shapely）。
预置的 test_core_imports_without_shapely 在第 3 部分才能运行；这里在每个部分检查已有的核心模块。"""
import subprocess
import sys
import unittest

CORE = ("v08.scene.exact", "v08.scene.field", "v08.scene.context", "v08.contract.monitoring",
        "v08.motion.feasible")
OPTIONAL = ("v08.sampler.common", "v08.motion.path", "v08.motion.formation", "v08.motion.connect",
            "v08.motion.speed", "v08.motion.nominal", "v08.motion.nominal_checks", "v08.motion.plan",
            "v08.motion.intents.monitoring", "v08.runner.monitoring_report")

PROGRAM = """
import importlib, importlib.abc, importlib.util, sys
class NoShapely(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "shapely" or fullname.startswith("shapely.") or fullname.startswith("scene_v07"):
            raise RuntimeError("core imported " + fullname)
sys.meta_path.insert(0, NoShapely())
for module in sys.argv[1:]:
    importlib.import_module(module)
print("imported", len(sys.argv) - 1)
"""


class TestNoShapely(unittest.TestCase):
    def test_core_modules(self):
        mods = list(CORE)
        for m in OPTIONAL:
            try:
                present = subprocess.run([sys.executable, "-B", "-c", "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)", m],
                                         capture_output=True).returncode == 0
            except Exception:
                present = False
            if present:
                mods.append(m)
        r = subprocess.run([sys.executable, "-B", "-c", PROGRAM, *mods], text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        print("\n检查的模块:", ", ".join(mods))


if __name__ == "__main__":
    unittest.main()
