"""V8-12 监视单段生成器的命令行入口（单进程）。

用法（在 Multi-UAV SimpleGC 目录下，conda llm 环境）:
    python -B scripts/v08/v8_12_monitoring.py --stage plan --data-root <SwarmData> --cache <缓存目录> --out <不存在的新目录>
    python -B scripts/v08/v8_12_monitoring.py --stage quick|full ...      （第 5 部分，尚未实现）

--stage plan  只规划检查（第 4 部分）：登记开发场景集 40 族 × draw 0..4，加 10 族 × 10 种子的多样性；
              无仿真、无动力学预演。写入 --out 下的 contracts/、diversity/、summary.json、failures.json、diversity.json。
--limit-families N / --draws K / --no-diversity 只用于冒烟或调试：结果标记为不完整，不能当作第 4 部分的结论。

输出与缓存路径在创建任何文件之前按 resolve() 后的实际路径检查：拒绝仓库、冻结工作树、数据根和任何 v07_* 路径。

退出码：0 = 完成，检查点完整且没有触发止损；2 = 检查点触发止损（诊断性，不是 P0）；
3 = 检查点未完成（有缺失测量、内部错误、冒烟子集或缺少多样性）；
4 = P0 停止（输入登记清单的 SHA256 不符）；1 = 参数、路径或环境错误。
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))

DEVSET_PATH = PROJECT.parent / "docs" / "v08" / "V8-03" / "devset_v08.json"
EXPECTED_DEVSET_SHA = "f773cdf1ccea88c98bc064c2b8c6d12aa70b5cb93e25cb468629472bfa98dc52"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["plan", "quick", "full"], required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan-input")
    ap.add_argument("--quick-input")
    ap.add_argument("--devset", default=str(DEVSET_PATH))
    ap.add_argument("--limit-families", type=int)
    ap.add_argument("--draws", type=int, default=5)
    ap.add_argument("--no-diversity", action="store_true")
    args = ap.parse_args(argv)

    from v08.runner import monitoring as run
    from v08.runner import monitoring_report as R

    if args.stage != "plan":
        print("第 5 部分（quick/full）尚未实现；本入口目前只支持 --stage plan。", file=sys.stderr)
        return 1
    data_root = Path(args.data_root)
    if not data_root.is_dir():
        print(f"数据根不存在：{data_root}", file=sys.stderr)
        return 1
    try:
        cache = run.guard_path(args.cache, label="缓存", data_root=data_root)
        out = run.guard_path(args.out, label="输出", data_root=data_root, must_not_exist=True)
    except run.PathRejected as exc:
        print(f"路径被拒绝：{exc}", file=sys.stderr)
        return 1
    devset = Path(args.devset)
    entries = run.load_entries(devset)
    # V8-03 登记的是按 order 排序的族 id 列表（换行连接）的 SHA256，不是 JSON 文件本身的哈希
    sha = hashlib.sha256("\n".join(e["family_id"] for e in entries).encode("utf-8")).hexdigest()
    if sha != EXPECTED_DEVSET_SHA or len(entries) != 40:
        print(f"登记清单的族 id 列表 SHA256 不符：{sha}（预期 {EXPECTED_DEVSET_SHA}），族数 {len(entries)}",
              file=sys.stderr)
        return 4
    subset = False
    if args.limit_families:
        entries = entries[:args.limit_families]
        subset = True
    if args.draws != run.DRAWS_PER_FAMILY:
        subset = True
    with_div = not args.no_diversity
    if subset:
        print("注意：这是冒烟子集，结果不完整，不能作为第 4 部分结论。")
    t0 = time.perf_counter()
    summary, chk = run.plan_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, devset_path=devset,
                                  with_diversity=with_div, draws=args.draws)
    wall = time.perf_counter() - t0
    c = summary
    print(f"\n合同 {c['successes']}/{c['contracts']} 规划成功；缺失 {c['missing']}；内部错误 {len(c['errors'])}；"
          f"规划净耗时中位数 {c['planning_median_s']}；总墙钟 {wall:.0f} s")
    print(f"止损触发：{list(chk.triggers)}；检查点完整：{chk.complete}")
    for r in chk.incomplete_reasons:
        print("  未完成原因：", r)
    print(f"输出：{out}")
    if subset or not chk.complete:
        return 3
    return 2 if chk.triggers else 0


if __name__ == "__main__":
    sys.exit(main())
