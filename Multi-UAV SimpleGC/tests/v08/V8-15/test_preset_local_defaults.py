"""V8-15 预置；未经运行。期望来自本次已存的worker选择结果，不写死新默认值。
真实测量文件缺失时skip；不得把skip记为通过。CLI均被截断到分派之前，不跑实验。
"""
import importlib.util
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tools" / "v08"))


def load_script(name):
    path = PROJECT / "tools" / "v08" / (name + ".py")
    spec = importlib.util.spec_from_file_location("v15_test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DefaultsPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("V8_15_WORKER_SELECTION")
        if not path:
            raise unittest.SkipTest("未提供真实worker选择文件：不是默认值测试通过")
        cls.selection = json.loads(Path(path).read_text(encoding="utf-8"))
        if cls.selection["selected"] is None:
            raise unittest.SkipTest("本次尚无合格worker档；没有新默认可验")
        cls.expected = int(cls.selection["selected"])

    def test_runtime_defaults_and_signatures(self):
        from v08.runner.runtime_defaults import DEFAULT_WORKERS
        from v08.runner import joint_monitoring as JM, skeleton_monitoring as SK
        self.assertEqual(DEFAULT_WORKERS, self.expected, "U D.3/F.4：默认来源是已存实测选定值")
        for fn in (JM.run_batch, SK.run_skeleton_batch):
            self.assertEqual(inspect.signature(fn).parameters["workers"].default, self.expected,
                             "所有已授权默认入口同步，不能残留另一个默认")
        driver = load_script("run_separation_v15")
        args = driver.build_parser().parse_args([
            "--mode", "production-quick", "--out", "unused",
            "--devset", "unused", "--data-root", "unused", "--cache", "unused",
            "--baseline", "unused"])
        self.assertEqual(args.workers, self.expected,
                         "新名单快速入口默认与选定值相同；解析不运行任务")

    def test_both_existing_cli_defaults_and_explicit_override(self):
        from v08.runner import joint_monitoring as JM, skeleton_monitoring as SK
        with tempfile.TemporaryDirectory() as tmp:
            joint = load_script("run_joint_monitoring")
            with patch.object(joint, "_guard", return_value=Path(tmp)), \
                 patch.object(JM, "cli", return_value=0) as called:
                joint.main(["--stage", "quick", "--out", "unused"])
                self.assertEqual(called.call_args.args[0].workers, self.expected,
                                 "旧joint parser原为1，本项必须同步实测默认")
                joint.main(["--stage", "quick", "--out", "unused", "--workers", "1"])
                self.assertEqual(called.call_args.args[0].workers, 1,
                                 "显式单进程选项仍可覆盖默认；历史复跑用途")
            skeleton = load_script("run_skeleton_monitoring")
            argv = ["--out", "unused", "--devset", "unused",
                    "--data-root", "unused", "--cache", "unused"]
            with patch("v08.runner.monitoring.guard_path", return_value=Path(tmp)), \
                 patch.object(SK, "cli", return_value=0) as called:
                skeleton.main(argv)
                self.assertEqual(called.call_args.args[0].workers, self.expected,
                                 "旧skeleton parser原为8，与实测默认同步")
                skeleton.main(argv + ["--workers", "1"])
                self.assertEqual(called.call_args.args[0].workers, 1,
                                 "显式选项优先于新默认")


if __name__ == "__main__":
    unittest.main()
