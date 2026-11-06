#!/usr/bin/env bash
# V8-17 新测试：预置三文件逐个运行（缺环境变量 skip 须在报告写"未执行"）+ 自加测试。用法：run_v17_tests.sh <日志文件> [artifacts]
# 第二参数为 artifacts 时同时运行 test_preset_local_artifacts_v17.py（需要 V8_17_REGRESSION_MANIFEST / V8_17_OUT 等）。
LOG="$(realpath -m "$1")"
R="F:/CASIA/Drone Swarm Situational Awareness Algorithm"
cd "$R/Simulation-v08/Multi-UAV SimpleGC" || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export V8_17_DATA_ROOT="$R/SwarmData" V8_17_TEST_CACHE="$R/_handoff/2026-11-06_V8-17_intrusion/run/cache"
export V8_17_DEVSET="$R/Simulation-v08/docs/v08/V8-03/devset_v08.json"
export V8_17_MONITOR_BASELINE="$R/_handoff/2026-11-04_V8-14_skeleton/out/full_v14c"
export V8_17_TRANSIT_BASELINE="$R/_handoff/2026-11-05_V8-16_transit/run/out/full_transit_r2"
PY="C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B"
{
echo "# V8-17 新测试 $(date '+%F %T %z')"
echo "# cwd=$(pwd)"
echo "# commit=$(git rev-parse HEAD) dirty=$(git status --porcelain | wc -l)"
echo "# V8_17_REGRESSION_MANIFEST=${V8_17_REGRESSION_MANIFEST:-<unset>} V8_17_OUT=${V8_17_OUT:-<unset>} V8_17_RERUN=${V8_17_RERUN:-<unset>}"
} > "$LOG"
run() {
  echo "" >> "$LOG"; echo "## $PY -m unittest discover -s tests/v08/V8-17 -p \"$1\" -v" >> "$LOG"
  sha256sum "tests/v08/V8-17/$1" 2>/dev/null >> "$LOG"
  $PY -m unittest discover -s tests/v08/V8-17 -p "$1" -v 2>&1 | grep -v "UserWarning: A NumPy version\|^  from scipy\|^  import numpy" >> "$LOG"
  echo "exit=${PIPESTATUS[0]}" >> "$LOG"
}
run "test_preset_numeric_v17.py"
run "test_preset_local_geometry_v17.py"
if [ "${2:-}" = "artifacts" ]; then run "test_preset_local_artifacts_v17.py"; fi
run "test_extra_local_v17.py"
echo "" >> "$LOG"; echo "# end $(date '+%F %T %z')" >> "$LOG"
