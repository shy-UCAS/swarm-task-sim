"""V8-14 第 6 部分：只构造骨架的批次入口（薄入口，不含算法）。

用法（在 Multi-UAV SimpleGC 目录下，conda llm，先设 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1）：
    python -B tools/v08/run_skeleton_monitoring.py --devset <devset_v08.json> --data-root <SwarmData>
        --cache <缓存目录> --out <不存在的新目录> [--workers N]
    （--workers 缺省 = v08/runner/runtime_defaults.DEFAULT_WORKERS，V8-15 实测选定）

与 run_joint_monitoring.py 相同的 --devset --data-root --cache --out --workers 语义与路径守卫（resolve 后拒绝仓库、
冻结工作树、数据根与任何 v07_* 路径；输出目录必须不存在）。
退出码：0 = 完成且检查点未触发；2 = 诊断触发；3 = 未完成；4 = P0；1 = 参数、路径或环境错误。
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--devset", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    args = ap.parse_args(argv)
    from v08.runner.monitoring import PathRejected, guard_path
    try:
        out = guard_path(args.out, label="输出", data_root=Path(args.data_root), must_not_exist=True)
        guard_path(args.cache, label="缓存", data_root=Path(args.data_root))
    except PathRejected as exc:
        print(f"路径被拒绝：{exc}", file=sys.stderr)
        return 1
    from v08.runner import skeleton_monitoring as SK
    return SK.cli(args, out)


if __name__ == "__main__":
    sys.exit(main())
