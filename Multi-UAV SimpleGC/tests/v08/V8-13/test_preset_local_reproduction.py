import json
import os
from pathlib import Path
import unittest


class ReproductionPreset(unittest.TestCase):
    def test_five_bytewise_reproductions(self):
        root = Path(os.environ["V8_13_RUN_OUT"]).resolve()
        doc = json.loads((root/"reproduction.json").read_text(encoding="utf-8"))
        comparisons = doc["comparisons"]
        self.assertEqual(len(comparisons), 5, "U D.4.2：预选5合同，失败也复跑")
        self.assertEqual(len({x["contract_id"] for x in comparisons}), 5,
                         "U D.4.2：5个不同的业务key")

        for item in comparisons:
            self.assertTrue(item["files"], "可复现不能比较空文件集")
            source = Path(item["source_dir"])
            repeat = Path(item["repeat_dir"])
            source_names = {p.relative_to(source).as_posix()
                            for p in source.rglob("*") if p.is_file()}
            repeat_names = {p.relative_to(repeat).as_posix()
                            for p in repeat.rglob("*") if p.is_file()}
            self.assertEqual(set(item["files"]), source_names,
                             "D.4可复现：不能挑出相同文件、遗漏其他确定性载荷")
            self.assertEqual(source_names, repeat_names,
                             "D.4可复现：文件集合也须一致，telemetry在合同目录外")
            # 来源：D.4.2计划和仿真都比；失败合同无轨迹时仍比较失败载荷。
            self.assertIn("contract.json", item["files"], "必须比较公共合同")
            self.assertIn("result.json", item["files"], "必须比较成功/失败及attempt载荷")
            if item["success"]:
                self.assertIn("skeleton.json", item["files"], "成功合同须比较原骨架")
                self.assertIn("optimized.json", item["files"], "成功合同须比较优化计划")
                self.assertTrue(any(n.endswith("/p.npy") for n in item["files"]),
                                "成功合同须比较真实仿真输出")
            for name in item["files"]:
                rel = Path(name)
                self.assertFalse(rel.is_absolute() or ".." in rel.parts,
                                 "确定性文件清单须为内部相对路径")
                a = Path(item["source_dir"])/rel
                b = Path(item["repeat_dir"])/rel
                self.assertEqual(a.read_bytes(), b.read_bytes(),
                                 "同键/同环境/8→1进程原字节一致："+name)


if __name__ == "__main__":
    unittest.main()
