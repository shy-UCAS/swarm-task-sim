"""本地真实输入测试；数据根由V8_12_DATA_ROOT给出，缓存使用系统临时目录。"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from v08.scene.context import load_context


class TestRegisteredDevset(unittest.TestCase):
    def test_registered_files_hash_and_read_only(self):
        repository = Path.cwd().parent  # 指令要求cwd为Multi-UAV SimpleGC
        manifest = repository / "docs/v08/V8-03/devset_v08.json"
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 40, "独立来源：上层C.1、V8-03登记40族")
        root_text = os.environ.get("V8_12_DATA_ROOT")
        self.assertIsNotNone(root_text,
                             "本地测试前提：显式数据根；缺数据不能skip后声称通过")
        data_root = Path(root_text).resolve()
        with tempfile.TemporaryDirectory(prefix="v8_12_cache_") as cache:
            for entry in entries:
                with self.subTest(family=entry["family_id"]):
                    directory = (data_root / Path(entry["directory_rel"])).resolve()
                    before = {}
                    for name in ("public_scene.json", "family_initial.json",
                                 "check_results.json", "provenance.json"):
                        path = directory / name
                        raw = path.read_bytes()
                        stat = path.stat()
                        before[name] = (hashlib.sha256(raw).hexdigest(),
                                        stat.st_size, stat.st_mtime_ns)
                    self.assertEqual(before["public_scene.json"][0],
                                     entry["public_scene_sha256"],
                                     "独立来源：固定提交V8-03登记哈希")
                    self.assertEqual(before["family_initial.json"][0],
                                     entry["family_initial_sha256"],
                                     "独立来源：固定提交V8-03登记初态哈希")
                    first = load_context(entry, data_root=data_root, cache_dir=cache)
                    second = load_context(entry, data_root=data_root, cache_dir=cache)
                    self.assertEqual(first.cache_key, second.cache_key,
                                     "r4 6.4数学不变量：相同几何及参数缓存键相同")
                    self.assertEqual(first.family.family_id, entry["family_id"],
                                     "独立来源：登记清单族身份")
                    for name, saved in before.items():
                        path = directory / name
                        raw = path.read_bytes()
                        stat = path.stat()
                        after = (hashlib.sha256(raw).hexdigest(),
                                 stat.st_size, stat.st_mtime_ns)
                        self.assertEqual(after, saved,
                                         "冻结不变量：读取上下文不改输入内容/大小/mtime")


if __name__ == "__main__":
    unittest.main()
