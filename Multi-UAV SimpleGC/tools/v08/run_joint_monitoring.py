"""V8-13 联合时空轨迹优化（监视单段）的命令行薄入口；不含另一套算法。

用法（在 Multi-UAV SimpleGC 目录下，conda llm 环境，先设 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1）:
    python -B tools/v08/run_joint_monitoring.py --stage tracking  --out <不存在的新目录>
    python -B tools/v08/run_joint_monitoring.py --stage numerics  --out <新目录>
    python -B tools/v08/run_joint_monitoring.py --stage quick|full|diversity --devset <devset_v08.json>
        --data-root <SwarmData> --cache <缓存目录> --out <新目录> [--workers N]
    （--workers 缺省 = v08/runner/runtime_defaults.DEFAULT_WORKERS，V8-15 实测选定；quick 分支与 rerun 仍单进程）
    python -B tools/v08/run_joint_monitoring.py --stage rerun --devset ... --data-root ... --cache ...
        --keys <rerun_keys.json> --compare-to <原 full 目录> --out <新目录> --workers 1

默认不执行任何阶段（--stage 必填）；不接受覆盖已有输出。输出与缓存路径按 resolve() 后的实际路径检查：
拒绝仓库、冻结工作树、数据根与任何 v07_* 路径。

退出码：0 = 完成且（如有）检查点未触发；2 = 诊断性检查点触发；3 = 检查点未完成；4 = P0 停止；
1 = 参数、路径或环境错误。
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))


def _guard(path, label, data_root=None, must_not_exist=False):
    from v08.runner.monitoring import guard_path
    return guard_path(path, label=label, data_root=data_root, must_not_exist=must_not_exist)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["tracking", "numerics", "quick", "full", "diversity", "rerun"],
                    required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--devset")
    ap.add_argument("--data-root")
    ap.add_argument("--cache")
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--keys")
    ap.add_argument("--compare-to")
    args = ap.parse_args(argv)

    from v08.runner.monitoring import PathRejected
    data_root = Path(args.data_root) if args.data_root else None
    try:
        out = _guard(args.out, "输出", data_root=data_root, must_not_exist=True)
    except PathRejected as exc:
        print(f"路径被拒绝：{exc}", file=sys.stderr)
        return 1

    if args.stage == "tracking":
        from v08.diagnostics.joint_calibration import measure_tracking_cases
        summary = measure_tracking_cases(out_dir=out)
        for r in summary["rows"]:
            print(f"J={r['jerk']:g}: max step err {r['max_error_m']:.4f} m（帧 {r['max_frame_error_m']:.4f}），"
                  f"complete={r['complete']}，最坏 {r['worst_case']}")
        print("检查点 1：", json.dumps(summary["choice"], ensure_ascii=False))
        ch = summary["choice"]
        if ch["reason"] == "incomplete":
            return 3
        return 2 if ch["triggered"] else 0

    if args.stage == "numerics":
        from v08.diagnostics.joint_calibration import calibrate_optimizer
        res = calibrate_optimizer(tracking_config=None, out_dir=out)
        print(json.dumps(res.get("selected"), ensure_ascii=False))
        return 0 if res.get("selected") else 3

    from v08.runner import joint_monitoring as JM
    return JM.cli(args, out)


if __name__ == "__main__":
    sys.exit(main())
