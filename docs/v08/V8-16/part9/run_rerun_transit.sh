#!/usr/bin/env bash
cd "F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08/Multi-UAV SimpleGC"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
echo "start $(date '+%F %T') commit=$(git rev-parse HEAD) dirty=$(git status --porcelain | wc -l)"
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B tools/v08/run_transit_v16.py --stage rerun --devset "F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08/docs/v08/V8-03/devset_v08.json" --data-root "F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData" --cache "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/cache" --out "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/out/rerun_transit" --workers 1 --keys "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/out/full_transit/rerun_keys.json" --compare-to "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-05_V8-16_transit/run/out/full_transit"
echo "exit=$? $(date '+%F %T')"
