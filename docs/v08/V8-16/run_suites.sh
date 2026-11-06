#!/usr/bin/env bash
# V8-16 回归套件：逐套写出命令、cwd、提交、环境与完整 unittest -v 输出（含 traceback）。用法：run_suites.sh <日志文件>
LOG="$(realpath -m "$1")"
cd "F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08/Multi-UAV SimpleGC" || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PY="C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B"
{
echo "# V8-16 回归套件 $(date '+%F %T %z')"
echo "# cwd=$(pwd)"
echo "# commit=$(git rev-parse HEAD) dirty=$(git status --porcelain | wc -l)"
echo "# threads OMP=$OMP_NUM_THREADS OPENBLAS=$OPENBLAS_NUM_THREADS MKL=$MKL_NUM_THREADS NUMEXPR=$NUMEXPR_NUM_THREADS"
echo "# V8_15_WORKER_SELECTION=${V8_15_WORKER_SELECTION:-<unset>}"
} > "$LOG"
run() {  # 目录 模式
  echo "" >> "$LOG"; echo "## $PY -m unittest discover -s $1 -p \"$2\" -v" >> "$LOG"
  $PY -m unittest discover -s "$1" -p "$2" -v 2>&1 | grep -v "UserWarning: A NumPy version\|^  from scipy\|^  import numpy" >> "$LOG"
  echo "exit=${PIPESTATUS[0]}" >> "$LOG"
}
run tests/v08/V8-15 "test_preset_numeric_*.py"
run tests/v08/V8-15 "test_preset_local_formation.py"
run tests/v08/V8-15 "test_preset_local_injection.py"
run tests/v08/V8-15 "test_preset_local_stress.py"
run tests/v08/V8-15 "test_preset_local_defaults.py"
run tests/v08/V8-15 "test_extra_*.py"
run tests/v08/V8-16 "test_preset_numeric_v16.py"
run tests/v08/V8-16 "test_preset_local_geometry_v16.py"
run tests/v08/V8-16 "test_preset_local_revisit_v16.py"
run tests/v08/V8-16 "test_extra_*.py"
run tests/v08/V8-11 "test_*.py"
run tests/v08/V8-12 "test_*.py"
run tests/v08/V8-13 "test_preset_numeric_*.py"
run tests/v08/V8-13 "test_extra_*.py"
run tests/v08/V8-14 "test_preset_numeric_*.py"
run tests/v08/V8-14 "test_extra_*.py"
run tests/v08/V8-14 "test_preset_local_geometry.py"
# V8-12 带数据根（历史 Fréchet 预期失败之外应全过）
echo "" >> "$LOG"; echo "## V8_12_DATA_ROOT=F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData $PY -m unittest discover -s tests/v08/V8-12 -p \"test_*.py\" -v" >> "$LOG"
V8_12_DATA_ROOT="F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData" $PY -m unittest discover -s tests/v08/V8-12 -p "test_*.py" -v 2>&1 | grep -v "UserWarning: A NumPy version\|^  from scipy\|^  import numpy" >> "$LOG"
echo "exit=${PIPESTATUS[0]}" >> "$LOG"
echo "" >> "$LOG"; echo "# end $(date '+%F %T %z')" >> "$LOG"
