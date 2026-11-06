#!/usr/bin/env bash
# V8-17 两意图字节门禁（第 2 部分 phase=2、第 4 部分 phase=4）。用法：run_gates.sh <phase>
# 监视：run_separation_v15.py --mode production-quick（与 full_v14c 比较）；过境：run_transit_v16.py --stage quick 后
# 用 gate_compare.py 与 full_transit_r2 同键比较。两者 24 进程、同环境、同输入；合同排除清单 []。
set -u
PHASE="$1"
ROOT="F:/CASIA/Drone Swarm Situational Awareness Algorithm"
RUN="$ROOT/_handoff/2026-11-06_V8-17_intrusion/run"
DOC="$ROOT/Simulation-v08/docs/v08/V8-17"
cd "$ROOT/Simulation-v08/Multi-UAV SimpleGC" || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PY="C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B"
DEVSET="$ROOT/Simulation-v08/docs/v08/V8-03/devset_v08.json"
DATA="$ROOT/SwarmData"
MON_BASE="$ROOT/_handoff/2026-11-04_V8-14_skeleton/out/full_v14c"
TR_BASE="$ROOT/_handoff/2026-11-05_V8-16_transit/run/out/full_transit_r2"
MON_OUT="$RUN/out/monitor_regression_$PHASE"
TR_OUT="$RUN/out/transit_regression_$PHASE"
echo "start $(date '+%F %T') commit=$(git rev-parse HEAD) dirty=$(git status --porcelain | wc -l)"
git diff --stat
$PY tools/v08/run_separation_v15.py --mode production-quick --workers 24 --baseline "$MON_BASE" --devset "$DEVSET" --data-root "$DATA" --cache "$RUN/cache" --out "$MON_OUT"
echo "monitor exit=$? $(date '+%F %T')"
$PY "$DOC/gate_compare.py" monitoring "$PHASE" "$MON_BASE" "$MON_OUT/run" "$DOC/part$PHASE/gate_monitoring.json"
echo "monitor gate exit=$?"
$PY tools/v08/run_transit_v16.py --stage quick --workers 24 --devset "$DEVSET" --data-root "$DATA" --cache "$RUN/cache" --out "$TR_OUT"
echo "transit exit=$? $(date '+%F %T')"
$PY "$DOC/gate_compare.py" transit "$PHASE" "$TR_BASE" "$TR_OUT" "$DOC/part$PHASE/gate_transit.json"
echo "transit gate exit=$? end $(date '+%F %T')"
