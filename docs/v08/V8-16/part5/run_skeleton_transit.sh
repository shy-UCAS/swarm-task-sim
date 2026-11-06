#!/usr/bin/env bash
cd "F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08/Multi-UAV SimpleGC"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PY="C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B"
$PY "F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08/docs/v08/V8-16/dir_snapshot.py" "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/cache" "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/logs/cache_before_skeleton.json"
echo "start $(date '+%F %T') commit=$(git rev-parse HEAD) dirty=$(git status --porcelain | wc -l)"
$PY tools/v08/run_transit_v16.py --stage skeleton --devset "F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08/docs/v08/V8-03/devset_v08.json" --data-root "F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData" --cache "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/cache" --out "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/out/skeleton_transit" --workers 24
echo "exit=$? $(date '+%F %T')"
$PY "F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08/docs/v08/V8-16/dir_snapshot.py" "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/cache" "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/logs/cache_after_skeleton.json" --compare "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/logs/cache_before_skeleton.json"
