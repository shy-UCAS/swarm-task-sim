# V8-15 第 5 部分：四阶段 cProfile 双 Top25

每个合同一个独立进程；同一时刻只有一个阶段 profiler 活动。cumtime 有包含关系，不能逐行相加；表中 `capture` 是本项为保存 AL 轮次而加在 optimize_segment 外层的只读包装。

## o23_d4（skeleton_s 最大；基线 wall 572.0 s，剖析 wall 453.7 s）

### orchestration — 按 cumulative（互斥墙钟 0.07 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `run_contract` | v08/runner/joint_monitoring.py:217 | 1 | 0.000 | 0.011 |
| 2 | `sample_common` | v08/sampler/common.py:11 | 1 | 0.000 | 0.011 |
| 3 | `rng_for` | v08/sampler/keys.py:77 | 2 | 0.000 | 0.011 |
| 4 | `__getattr__` | numpy/__init__.py:713 | 1 | 0.000 | 0.011 |
| 5 | `_find_and_load` | <frozen importlib._bootstrap>:1349 | 15 | 0.000 | 0.011 |
| 6 | `_find_and_load_unlocked` | <frozen importlib._bootstrap>:1304 | 15 | 0.000 | 0.011 |
| 7 | `_load_unlocked` | <frozen importlib._bootstrap>:911 | 15 | 0.000 | 0.010 |
| 8 | `exec_module` | <frozen importlib._bootstrap_external>:989 | 5 | 0.000 | 0.010 |
| 9 | `_call_with_frames_removed` | <frozen importlib._bootstrap>:480 | 41 | 0.000 | 0.010 |
| 10 | `<built-in method builtins.exec>` | ~:0 | 5 | 0.000 | 0.010 |
| 11 | `<module>` | numpy/random/__init__.py:1 | 1 | 0.000 | 0.010 |
| 12 | `_handle_fromlist` | <frozen importlib._bootstrap>:1390 | 1 | 0.000 | 0.010 |
| 13 | `<built-in method builtins.__import__>` | ~:0 | 2 | 0.000 | 0.010 |
| 14 | `exec_module` | <frozen importlib._bootstrap_external>:1295 | 9 | 0.000 | 0.006 |
| 15 | `<built-in method _imp.exec_dynamic>` | ~:0 | 9 | 0.002 | 0.006 |
| 16 | `save_contract` | v08/runner/joint_monitoring.py:321 | 1 | 0.000 | 0.005 |
| 17 | `jsonable` | v08/runner/monitoring.py:72 | 4617 | 0.004 | 0.005 |
| 18 | `<module>` | numpy/random/_pickle.py:1 | 1 | 0.000 | 0.005 |
| 19 | `_json_bytes` | v08/runner/joint_monitoring.py:317 | 3 | 0.000 | 0.003 |
| 20 | `canonical_json` | v08/runner/monitoring.py:97 | 3 | 0.000 | 0.003 |
| 21 | `module_from_spec` | <frozen importlib._bootstrap>:806 | 15 | 0.000 | 0.003 |
| 22 | `_find_spec` | <frozen importlib._bootstrap>:1240 | 15 | 0.000 | 0.003 |
| 23 | `create_module` | <frozen importlib._bootstrap_external>:1287 | 9 | 0.000 | 0.003 |
| 24 | `<built-in method _imp.create_dynamic>` | ~:0 | 9 | 0.003 | 0.003 |
| 25 | `find_spec` | <frozen importlib._bootstrap_external>:1520 | 14 | 0.000 | 0.003 |

### orchestration — 按 tottime（互斥墙钟 0.07 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `jsonable` | v08/runner/monitoring.py:72 | 4617 | 0.004 | 0.005 |
| 2 | `<built-in method _imp.create_dynamic>` | ~:0 | 9 | 0.003 | 0.003 |
| 3 | `<built-in method nt.stat>` | ~:0 | 46 | 0.002 | 0.002 |
| 4 | `<built-in method _imp.exec_dynamic>` | ~:0 | 9 | 0.002 | 0.006 |
| 5 | `<built-in method builtins.isinstance>` | ~:0 | 17274 | 0.001 | 0.001 |
| 6 | `<built-in method nt.mkdir>` | ~:0 | 6 | 0.001 | 0.001 |
| 7 | `iterencode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:205 | 5 | 0.001 | 0.001 |
| 8 | `<built-in method _io.open>` | ~:0 | 4 | 0.001 | 0.001 |
| 9 | `<method 'disable' of '_lsprof.Profiler' objects>` | ~:0 | 25 | 0.000 | 0.000 |
| 10 | `<built-in method _io.open_code>` | ~:0 | 5 | 0.000 | 0.000 |
| 11 | `<method '__exit__' of '_io._IOBase' objects>` | ~:0 | 9 | 0.000 | 0.000 |
| 12 | `_path_join` | <frozen importlib._bootstrap_external>:96 | 80 | 0.000 | 0.000 |
| 13 | `attempt_chain` | v08/runner/joint_monitoring.py:112 | 20 | 0.000 | 0.001 |
| 14 | `is_dataclass` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1294 | 848 | 0.000 | 0.000 |
| 15 | `<built-in method marshal.loads>` | ~:0 | 5 | 0.000 | 0.000 |
| 16 | `<method 'read' of '_io.BufferedReader' objects>` | ~:0 | 6 | 0.000 | 0.000 |
| 17 | `_attempt_summary` | v08/runner/joint_monitoring.py:175 | 20 | 0.000 | 0.003 |
| 18 | `__init__` | <frozen importlib._bootstrap>:232 | 15 | 0.000 | 0.000 |
| 19 | `replace` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1533 | 20 | 0.000 | 0.000 |
| 20 | `_find_and_load` | <frozen importlib._bootstrap>:1349 | 15 | 0.000 | 0.011 |
| 21 | `<built-in method math.isfinite>` | ~:0 | 1771 | 0.000 | 0.000 |
| 22 | `find_spec` | <frozen importlib._bootstrap_external>:1593 | 23 | 0.000 | 0.003 |
| 23 | `sample_common` | v08/sampler/common.py:11 | 1 | 0.000 | 0.011 |
| 24 | `<built-in method nt.listdir>` | ~:0 | 1 | 0.000 | 0.000 |
| 25 | `<method 'get' of 'dict' objects>` | ~:0 | 814 | 0.000 | 0.000 |

### skeleton — 按 cumulative（互斥墙钟 317.36 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `plan_attempt` | v08/motion/plan.py:34 | 20 | 0.005 | 317.362 |
| 2 | `propose_and_build` | v08/motion/intents/monitoring.py:1448 | 20 | 0.033 | 317.314 |
| 3 | `width_then_build` | v08/motion/skeleton.py:26 | 20 | 0.000 | 317.117 |
| 4 | `build` | v08/motion/intents/monitoring.py:1481 | 20 | 0.000 | 294.635 |
| 5 | `_build_with_ring` | v08/motion/intents/monitoring.py:1376 | 20 | 0.001 | 294.635 |
| 6 | `_finish_retrace` | v08/motion/intents/monitoring.py:1335 | 20 | 0.000 | 294.246 |
| 7 | `prepare` | v08/motion/intents/monitoring.py:1281 | 20 | 0.001 | 230.951 |
| 8 | `_turns_v14` | v08/motion/intents/monitoring.py:969 | 20 | 0.017 | 215.084 |
| 9 | `sample_joint_turn` | v08/motion/monitoring_turn.py:331 | 33 | 4.231 | 215.052 |
| 10 | `_poly_sdf` | v08/scene/exact.py:90 | 256212 | 92.251 | 160.984 |
| 11 | `signed_distance` | v08/scene/exact.py:105 | 261817 | 2.796 | 149.715 |
| 12 | `clearance_values` | v08/scene/exact.py:136 | 245888 | 0.738 | 141.339 |
| 13 | `_points_ok` | v08/motion/monitoring_turn.py:232 | 9234 | 0.267 | 89.867 |
| 14 | `polyline_clearance` | v08/scene/exact.py:221 | 190364 | 2.852 | 84.949 |
| 15 | `_exact_ok` | v08/motion/monitoring_turn.py:223 | 38178 | 0.359 | 84.631 |
| 16 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1914078 | 71.961 | 71.961 |
| 17 | `assemble` | v08/motion/intents/monitoring.py:1304 | 7 | 0.007 | 63.294 |
| 18 | `build_candidate` | v08/motion/intents/monitoring.py:215 | 5 | 0.098 | 61.511 |
| 19 | `_wrapreduction` | numpy/_core/fromnumeric.py:66 | 890192 | 0.933 | 55.311 |
| 20 | `sum` | numpy/_core/fromnumeric.py:2342 | 651326 | 0.578 | 54.510 |
| 21 | `screen_member` | v08/motion/nominal_checks.py:156 | 36 | 0.011 | 53.703 |
| 22 | `revisit` | v08/motion/nominal_checks.py:77 | 36 | 51.892 | 53.401 |
| 23 | `chord_sdf_range` | v08/scene/exact.py:158 | 17117 | 3.819 | 50.232 |
| 24 | `_bezier_batch` | v08/motion/path.py:310 | 14763 | 6.425 | 29.814 |
| 25 | `_seg_point_dist` | v08/scene/exact.py:148 | 68000 | 22.144 | 27.996 |

### skeleton — 按 tottime（互斥墙钟 317.36 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `_poly_sdf` | v08/scene/exact.py:90 | 256212 | 92.251 | 160.984 |
| 2 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1914078 | 71.961 | 71.961 |
| 3 | `revisit` | v08/motion/nominal_checks.py:77 | 36 | 51.892 | 53.401 |
| 4 | `<built-in method numpy._core._multiarray_umath.c_einsum>` | ~:0 | 44289 | 23.133 | 23.133 |
| 5 | `_seg_point_dist` | v08/scene/exact.py:148 | 68000 | 22.144 | 27.996 |
| 6 | `_bezier_batch` | v08/motion/path.py:310 | 14763 | 6.425 | 29.814 |
| 7 | `sample_joint_turn` | v08/motion/monitoring_turn.py:331 | 33 | 4.231 | 215.052 |
| 8 | `chord_sdf_range` | v08/scene/exact.py:158 | 17117 | 3.819 | 50.232 |
| 9 | `polyline_clearance` | v08/scene/exact.py:221 | 190364 | 2.852 | 84.949 |
| 10 | `signed_distance` | v08/scene/exact.py:105 | 261817 | 2.796 | 149.715 |
| 11 | `bezier5_controls` | v08/motion/path.py:279 | 398715 | 2.743 | 2.865 |
| 12 | `_clip` | numpy/_core/_methods.py:96 | 486085 | 1.982 | 2.065 |
| 13 | `speed_profile` | v08/sim/guidance.py:88 | 84 | 1.649 | 2.378 |
| 14 | `_wrapreduction` | numpy/_core/fromnumeric.py:66 | 890192 | 0.933 | 55.311 |
| 15 | `value` | v08/scene/field.py:158 | 29981 | 0.928 | 2.034 |
| 16 | `_arc` | v08/motion/path.py:145 | 35506 | 0.921 | 1.728 |
| 17 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 7500 | 0.898 | 0.898 |
| 18 | `diff` | numpy/lib/_function_base_impl.py:1413 | 199326 | 0.779 | 0.894 |
| 19 | `<genexpr>` | v08/motion/intents/monitoring.py:319 | 1090758 | 0.770 | 0.770 |
| 20 | `<built-in method builtins.divmod>` | ~:0 | 10615124 | 0.741 | 0.741 |
| 21 | `clearance_values` | v08/scene/exact.py:136 | 245888 | 0.738 | 141.339 |
| 22 | `intersects` | shapely/predicates.py:747 | 2091 | 0.733 | 0.733 |
| 23 | `linspace` | numpy/_core/function_base.py:27 | 106616 | 0.720 | 1.104 |
| 24 | `<built-in method builtins.min>` | ~:0 | 5244742 | 0.694 | 0.694 |
| 25 | `<built-in method numpy.array>` | ~:0 | 447801 | 0.623 | 0.623 |

### optimize — 按 cumulative（互斥墙钟 136.14 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `capture` | tools/v08/profile_monitoring_v15.py:391 | 4 | 0.000 | 136.144 |
| 2 | `optimize_segment` | v08/motion/optimize.py:926 | 4 | 0.049 | 136.140 |
| 3 | `solve_joint` | v08/motion/optimize.py:837 | 4 | 0.019 | 64.854 |
| 4 | `check_monitoring` | v08/motion/optimize_checks.py:363 | 4 | 0.009 | 61.631 |
| 5 | `minimize` | scipy/optimize/_minimize.py:53 | 4 | 0.001 | 57.448 |
| 6 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 4 | 0.771 | 57.448 |
| 7 | `_update_fun` | scipy/optimize/_differentiable_functions.py:292 | 1001 | 0.008 | 56.533 |
| 8 | `wrapped` | scipy/optimize/_differentiable_functions.py:15 | 997 | 0.012 | 56.525 |
| 9 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 1994 | 1.459 | 56.521 |
| 10 | `__call__` | scipy/optimize/_optimize.py:77 | 997 | 0.002 | 56.501 |
| 11 | `fun_and_grad` | scipy/optimize/_differentiable_functions.py:340 | 997 | 0.005 | 56.414 |
| 12 | `value_grad` | v08/motion/optimize.py:773 | 1001 | 3.907 | 55.299 |
| 13 | `screen_member` | v08/motion/nominal_checks.py:156 | 36 | 0.010 | 54.907 |
| 14 | `revisit` | v08/motion/nominal_checks.py:77 | 36 | 53.059 | 54.599 |
| 15 | `_blocks` | v08/motion/optimize.py:636 | 1009 | 11.624 | 36.742 |
| 16 | `eval` | v08/motion/optimize.py:299 | 36468 | 18.306 | 20.754 |
| 17 | `references_from_skeleton` | v08/motion/skeleton.py:179 | 4 | 0.001 | 9.599 |
| 18 | `chord_sdf_range` | v08/scene/exact.py:158 | 198 | 0.837 | 9.446 |
| 19 | `__matmul__` | scipy/sparse/_base.py:665 | 109728 | 0.066 | 8.709 |
| 20 | `_matmul_dispatch` | scipy/sparse/_base.py:544 | 109764 | 0.117 | 8.337 |
| 21 | `semantic_lines` | v08/motion/skeleton.py:87 | 36 | 0.004 | 8.263 |
| 22 | `_matmul_multivector` | scipy/sparse/_compressed.py:496 | 91206 | 0.248 | 7.940 |
| 23 | `curvature_radius_min` | v08/motion/optimize_checks.py:207 | 72 | 0.133 | 6.536 |
| 24 | `_band_ranges` | v08/motion/skeleton.py:79 | 126 | 0.041 | 6.165 |
| 25 | `check_physical` | v08/motion/optimize_checks.py:250 | 4 | 0.051 | 5.509 |

### optimize — 按 tottime（互斥墙钟 136.14 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `revisit` | v08/motion/nominal_checks.py:77 | 36 | 53.059 | 54.599 |
| 2 | `eval` | v08/motion/optimize.py:299 | 36468 | 18.306 | 20.754 |
| 3 | `_blocks` | v08/motion/optimize.py:636 | 1009 | 11.624 | 36.742 |
| 4 | `bp_t` | v08/motion/optimize.py:665 | 6592 | 4.764 | 4.790 |
| 5 | `_seg_point_dist` | v08/scene/exact.py:148 | 792 | 4.339 | 5.336 |
| 6 | `value_grad` | v08/motion/optimize.py:773 | 1001 | 3.907 | 55.299 |
| 7 | `<built-in method scipy.sparse._sparsetools.csr_matvecs>` | ~:0 | 46089 | 3.628 | 3.628 |
| 8 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 661811 | 3.489 | 3.489 |
| 9 | `<built-in method scipy.sparse._sparsetools.csc_matvecs>` | ~:0 | 45117 | 3.477 | 3.477 |
| 10 | `_poly_sdf` | v08/scene/exact.py:90 | 648 | 2.780 | 4.384 |
| 11 | `solve_banded` | scipy/linalg/_basic.py:370 | 18270 | 2.123 | 2.641 |
| 12 | `speed_profile` | v08/sim/guidance.py:88 | 72 | 1.674 | 2.390 |
| 13 | `_clip` | numpy/_core/_methods.py:96 | 245768 | 1.485 | 1.608 |
| 14 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 1994 | 1.459 | 56.521 |
| 15 | `eigvals` | numpy/linalg/_linalg.py:1181 | 10323 | 1.015 | 1.103 |
| 16 | `<built-in method numpy.zeros>` | ~:0 | 202989 | 0.937 | 0.937 |
| 17 | `as_series` | numpy/polynomial/polyutils.py:63 | 710252 | 0.858 | 2.603 |
| 18 | `chord_sdf_range` | v08/scene/exact.py:158 | 198 | 0.837 | 9.446 |
| 19 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 589467 | 0.813 | 0.813 |
| 20 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 4 | 0.771 | 57.448 |
| 21 | `common_type` | numpy/lib/_type_check_impl.py:661 | 710324 | 0.694 | 1.249 |
| 22 | `<built-in method builtins.min>` | ~:0 | 5270758 | 0.677 | 0.677 |
| 23 | `<built-in method numpy.array>` | ~:0 | 2219973 | 0.637 | 0.637 |
| 24 | `evaluate` | v08/motion/optimize.py:83 | 756 | 0.466 | 0.649 |
| 25 | `<built-in method builtins.max>` | ~:0 | 2721184 | 0.422 | 0.422 |

### simulation：无调用

### verify：无调用

## o35_d3（optimize_s 最大（未选键）；基线 wall 547.8 s，剖析 wall 447.9 s）

### orchestration — 按 cumulative（互斥墙钟 3.21 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `save_contract` | v08/runner/joint_monitoring.py:321 | 1 | 0.007 | 2.927 |
| 2 | `jsonable` | v08/runner/monitoring.py:72 | 2894218 | 1.680 | 2.421 |
| 3 | `_json_bytes` | v08/runner/joint_monitoring.py:317 | 5 | 0.003 | 2.199 |
| 4 | `canonical_json` | v08/runner/monitoring.py:97 | 5 | 0.007 | 2.196 |
| 5 | `plan_to_record` | v08/runner/monitoring.py:112 | 1 | 0.000 | 0.672 |
| 6 | `<built-in method builtins.isinstance>` | ~:0 | 9574741 | 0.557 | 0.557 |
| 7 | `dumps` | C:/Users/shy/anaconda3/envs/llm/Lib/json/__init__.py:183 | 7 | 0.000 | 0.411 |
| 8 | `encode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:183 | 7 | 0.000 | 0.411 |
| 9 | `iterencode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:205 | 7 | 0.411 | 0.411 |
| 10 | `<built-in method math.isfinite>` | ~:0 | 2205489 | 0.112 | 0.112 |
| 11 | `is_dataclass` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1294 | 283308 | 0.056 | 0.086 |
| 12 | `phase_diagnostics` | v08/runner/joint_monitoring.py:529 | 1 | 0.007 | 0.074 |
| 13 | `__call__` | v08/motion/skeleton.py:54 | 16 | 0.029 | 0.034 |
| 14 | `evaluate` | v08/motion/optimize.py:83 | 24 | 0.022 | 0.031 |
| 15 | `member_deviation` | v08/runner/joint_monitoring.py:515 | 1 | 0.001 | 0.028 |
| 16 | `<built-in method numpy.asarray>` | ~:0 | 418 | 0.028 | 0.028 |
| 17 | `phase_metrics` | v08/diagnostics/monitoring_skeleton.py:25 | 8 | 0.013 | 0.023 |
| 18 | `save` | numpy/lib/_npyio_impl.py:504 | 40 | 0.000 | 0.022 |
| 19 | `<built-in method builtins.hasattr>` | ~:0 | 283424 | 0.015 | 0.015 |
| 20 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 25 | 0.015 | 0.015 |
| 21 | `write_array` | numpy/lib/_format_impl.py:702 | 40 | 0.000 | 0.012 |
| 22 | `_find_and_load` | <frozen importlib._bootstrap>:1349 | 16 | 0.000 | 0.011 |
| 23 | `<method 'tofile' of 'numpy.ndarray' objects>` | ~:0 | 40 | 0.011 | 0.011 |
| 24 | `_find_and_load_unlocked` | <frozen importlib._bootstrap>:1304 | 16 | 0.000 | 0.011 |
| 25 | `_load_unlocked` | <frozen importlib._bootstrap>:911 | 16 | 0.000 | 0.010 |

### orchestration — 按 tottime（互斥墙钟 3.21 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `jsonable` | v08/runner/monitoring.py:72 | 2894218 | 1.680 | 2.421 |
| 2 | `<built-in method builtins.isinstance>` | ~:0 | 9574741 | 0.557 | 0.557 |
| 3 | `iterencode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:205 | 7 | 0.411 | 0.411 |
| 4 | `<built-in method math.isfinite>` | ~:0 | 2205489 | 0.112 | 0.112 |
| 5 | `is_dataclass` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1294 | 283308 | 0.056 | 0.086 |
| 6 | `__call__` | v08/motion/skeleton.py:54 | 16 | 0.029 | 0.034 |
| 7 | `<built-in method numpy.asarray>` | ~:0 | 418 | 0.028 | 0.028 |
| 8 | `evaluate` | v08/motion/optimize.py:83 | 24 | 0.022 | 0.031 |
| 9 | `<built-in method builtins.hasattr>` | ~:0 | 283424 | 0.015 | 0.015 |
| 10 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 25 | 0.015 | 0.015 |
| 11 | `phase_metrics` | v08/diagnostics/monitoring_skeleton.py:25 | 8 | 0.013 | 0.023 |
| 12 | `<method 'tofile' of 'numpy.ndarray' objects>` | ~:0 | 40 | 0.011 | 0.011 |
| 13 | `<built-in method _io.open>` | ~:0 | 54 | 0.009 | 0.009 |
| 14 | `<method 'write' of '_io.BufferedWriter' objects>` | ~:0 | 45 | 0.007 | 0.007 |
| 15 | `phase_diagnostics` | v08/runner/joint_monitoring.py:529 | 1 | 0.007 | 0.074 |
| 16 | `save_contract` | v08/runner/joint_monitoring.py:321 | 1 | 0.007 | 2.927 |
| 17 | `canonical_json` | v08/runner/monitoring.py:97 | 5 | 0.007 | 2.196 |
| 18 | `<method 'searchsorted' of 'numpy.ndarray' objects>` | ~:0 | 24 | 0.007 | 0.007 |
| 19 | `_speed` | v08/diagnostics/monitoring_skeleton.py:20 | 56 | 0.005 | 0.005 |
| 20 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 512 | 0.004 | 0.004 |
| 21 | `<built-in method numpy._core._multiarray_umath.c_einsum>` | ~:0 | 24 | 0.004 | 0.004 |
| 22 | `_json_bytes` | v08/runner/joint_monitoring.py:317 | 5 | 0.003 | 2.199 |
| 23 | `<built-in method nt.mkdir>` | ~:0 | 16 | 0.003 | 0.003 |
| 24 | `basis_weights` | v08/motion/optimize.py:159 | 24 | 0.003 | 0.004 |
| 25 | `<built-in method _imp.create_dynamic>` | ~:0 | 9 | 0.003 | 0.003 |

### skeleton — 按 cumulative（互斥墙钟 161.59 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `plan_attempt` | v08/motion/plan.py:34 | 8 | 0.002 | 161.593 |
| 2 | `propose_and_build` | v08/motion/intents/monitoring.py:1448 | 8 | 0.020 | 161.550 |
| 3 | `width_then_build` | v08/motion/skeleton.py:26 | 8 | 0.000 | 161.265 |
| 4 | `build` | v08/motion/intents/monitoring.py:1481 | 8 | 0.000 | 149.380 |
| 5 | `_build_with_ring` | v08/motion/intents/monitoring.py:1376 | 8 | 0.000 | 149.379 |
| 6 | `_finish_retrace` | v08/motion/intents/monitoring.py:1335 | 3 | 0.000 | 96.825 |
| 7 | `assemble` | v08/motion/intents/monitoring.py:1304 | 8 | 0.033 | 91.590 |
| 8 | `build_candidate` | v08/motion/intents/monitoring.py:215 | 8 | 0.245 | 91.066 |
| 9 | `prepare` | v08/motion/intents/monitoring.py:1281 | 8 | 0.000 | 57.545 |
| 10 | `screen_member` | v08/motion/nominal_checks.py:156 | 56 | 0.017 | 56.587 |
| 11 | `revisit` | v08/motion/nominal_checks.py:77 | 56 | 54.063 | 55.895 |
| 12 | `_turns_v14` | v08/motion/intents/monitoring.py:969 | 3 | 0.004 | 55.535 |
| 13 | `sample_joint_turn` | v08/motion/monitoring_turn.py:331 | 8 | 1.921 | 55.529 |
| 14 | `_finish_loop` | v08/motion/intents/monitoring.py:1326 | 5 | 0.000 | 52.311 |
| 15 | `_poly_sdf` | v08/scene/exact.py:90 | 45523 | 26.685 | 45.542 |
| 16 | `polyline_clearance` | v08/scene/exact.py:221 | 33596 | 1.011 | 38.397 |
| 17 | `signed_distance` | v08/scene/exact.py:105 | 45106 | 0.743 | 37.367 |
| 18 | `_exact_ok` | v08/motion/monitoring_turn.py:223 | 5883 | 0.076 | 35.845 |
| 19 | `clearance_values` | v08/scene/exact.py:136 | 42752 | 0.169 | 35.248 |
| 20 | `chord_sdf_range` | v08/scene/exact.py:158 | 5227 | 2.306 | 28.927 |
| 21 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 403200 | 22.047 | 22.047 |
| 22 | `speed_profile` | v08/sim/guidance.py:88 | 444 | 14.863 | 21.399 |
| 23 | `map_speed_events` | v08/motion/speed.py:51 | 8 | 0.008 | 17.638 |
| 24 | `_wrapreduction` | numpy/_core/fromnumeric.py:66 | 177083 | 0.190 | 16.900 |
| 25 | `sum` | numpy/_core/fromnumeric.py:2342 | 132700 | 0.123 | 16.380 |

### skeleton — 按 tottime（互斥墙钟 161.59 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `revisit` | v08/motion/nominal_checks.py:77 | 56 | 54.063 | 55.895 |
| 2 | `_poly_sdf` | v08/scene/exact.py:90 | 45523 | 26.685 | 45.542 |
| 3 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 403200 | 22.047 | 22.047 |
| 4 | `speed_profile` | v08/sim/guidance.py:88 | 444 | 14.863 | 21.399 |
| 5 | `_seg_point_dist` | v08/scene/exact.py:148 | 19040 | 12.886 | 16.109 |
| 6 | `<built-in method builtins.min>` | ~:0 | 36527369 | 4.382 | 4.382 |
| 7 | `<built-in method numpy._core._multiarray_umath.c_einsum>` | ~:0 | 4608 | 2.649 | 2.649 |
| 8 | `<built-in method math.sqrt>` | ~:0 | 34159167 | 2.356 | 2.356 |
| 9 | `chord_sdf_range` | v08/scene/exact.py:158 | 5227 | 2.306 | 28.927 |
| 10 | `sample_joint_turn` | v08/motion/monitoring_turn.py:331 | 8 | 1.921 | 55.529 |
| 11 | `<genexpr>` | v08/motion/intents/monitoring.py:319 | 2756227 | 1.867 | 1.867 |
| 12 | `_release_delays_ref` | v08/motion/intents/monitoring.py:470 | 8 | 1.136 | 5.031 |
| 13 | `polyline_clearance` | v08/scene/exact.py:221 | 33596 | 1.011 | 38.397 |
| 14 | `_clip` | numpy/_core/_methods.py:96 | 128442 | 0.743 | 0.758 |
| 15 | `signed_distance` | v08/scene/exact.py:105 | 45106 | 0.743 | 37.367 |
| 16 | `_bezier_batch` | v08/motion/path.py:310 | 1536 | 0.706 | 3.380 |
| 17 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 3252 | 0.700 | 0.700 |
| 18 | `intersects` | shapely/predicates.py:747 | 1558 | 0.532 | 0.532 |
| 19 | `<built-in method builtins.max>` | ~:0 | 2578711 | 0.391 | 0.393 |
| 20 | `<built-in method builtins.divmod>` | ~:0 | 5716722 | 0.344 | 0.344 |
| 21 | `<built-in method numpy.asarray>` | ~:0 | 477751 | 0.336 | 0.336 |
| 22 | `_arc` | v08/motion/path.py:145 | 10777 | 0.317 | 0.557 |
| 23 | `bezier5_controls` | v08/motion/path.py:279 | 40935 | 0.266 | 0.278 |
| 24 | `build_candidate` | v08/motion/intents/monitoring.py:215 | 8 | 0.245 | 91.066 |
| 25 | `value` | v08/scene/field.py:158 | 6155 | 0.239 | 0.463 |

### optimize — 按 cumulative（互斥墙钟 241.63 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `capture` | tools/v08/profile_monitoring_v15.py:391 | 7 | 0.000 | 241.628 |
| 2 | `optimize_segment` | v08/motion/optimize.py:926 | 7 | 0.118 | 241.623 |
| 3 | `solve_joint` | v08/motion/optimize.py:837 | 7 | 0.039 | 151.300 |
| 4 | `minimize` | scipy/optimize/_minimize.py:53 | 7 | 0.001 | 137.227 |
| 5 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 7 | 1.815 | 137.226 |
| 6 | `_update_fun` | scipy/optimize/_differentiable_functions.py:292 | 1911 | 0.019 | 135.121 |
| 7 | `wrapped` | scipy/optimize/_differentiable_functions.py:15 | 1903 | 0.027 | 135.102 |
| 8 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 3806 | 3.276 | 135.092 |
| 9 | `__call__` | scipy/optimize/_optimize.py:77 | 1903 | 0.003 | 135.048 |
| 10 | `fun_and_grad` | scipy/optimize/_differentiable_functions.py:340 | 1904 | 0.008 | 134.778 |
| 11 | `value_grad` | v08/motion/optimize.py:773 | 1910 | 10.020 | 132.225 |
| 12 | `_blocks` | v08/motion/optimize.py:636 | 1924 | 25.932 | 86.852 |
| 13 | `check_monitoring` | v08/motion/optimize_checks.py:363 | 7 | 0.025 | 67.822 |
| 14 | `screen_member` | v08/motion/nominal_checks.py:156 | 56 | 0.016 | 54.769 |
| 15 | `revisit` | v08/motion/nominal_checks.py:77 | 56 | 52.438 | 54.104 |
| 16 | `eval` | v08/motion/optimize.py:299 | 61792 | 44.889 | 50.229 |
| 17 | `references_from_skeleton` | v08/motion/skeleton.py:179 | 7 | 0.003 | 22.374 |
| 18 | `chord_sdf_range` | v08/scene/exact.py:158 | 380 | 1.906 | 21.490 |
| 19 | `__matmul__` | scipy/sparse/_base.py:665 | 185768 | 0.117 | 21.269 |
| 20 | `_matmul_dispatch` | scipy/sparse/_base.py:544 | 185824 | 0.197 | 20.648 |
| 21 | `_matmul_multivector` | scipy/sparse/_compressed.py:496 | 154424 | 0.415 | 19.852 |
| 22 | `semantic_lines` | v08/motion/skeleton.py:87 | 56 | 0.011 | 18.956 |
| 23 | `_band_ranges` | v08/motion/skeleton.py:79 | 156 | 0.080 | 13.315 |
| 24 | `_seg_point_dist` | v08/scene/exact.py:148 | 1072 | 9.675 | 11.933 |
| 25 | `bp_t` | v08/motion/optimize.py:665 | 10166 | 11.741 | 11.782 |

### optimize — 按 tottime（互斥墙钟 241.63 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `revisit` | v08/motion/nominal_checks.py:77 | 56 | 52.438 | 54.104 |
| 2 | `eval` | v08/motion/optimize.py:299 | 61792 | 44.889 | 50.229 |
| 3 | `_blocks` | v08/motion/optimize.py:636 | 1924 | 25.932 | 86.852 |
| 4 | `bp_t` | v08/motion/optimize.py:665 | 10166 | 11.741 | 11.782 |
| 5 | `value_grad` | v08/motion/optimize.py:773 | 1910 | 10.020 | 132.225 |
| 6 | `_seg_point_dist` | v08/scene/exact.py:148 | 1072 | 9.675 | 11.933 |
| 7 | `<built-in method scipy.sparse._sparsetools.csr_matvecs>` | ~:0 | 77912 | 9.252 | 9.252 |
| 8 | `<built-in method scipy.sparse._sparsetools.csc_matvecs>` | ~:0 | 76512 | 8.853 | 8.853 |
| 9 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1066550 | 7.582 | 7.582 |
| 10 | `_poly_sdf` | v08/scene/exact.py:90 | 928 | 6.439 | 10.032 |
| 11 | `solve_banded` | scipy/linalg/_basic.py:370 | 30952 | 5.681 | 7.011 |
| 12 | `speed_profile` | v08/sim/guidance.py:88 | 112 | 4.092 | 5.901 |
| 13 | `_clip` | numpy/_core/_methods.py:96 | 414974 | 3.359 | 3.569 |
| 14 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 3806 | 3.276 | 135.092 |
| 15 | `<built-in method numpy.zeros>` | ~:0 | 339489 | 2.509 | 2.509 |
| 16 | `eigvals` | numpy/linalg/_linalg.py:1181 | 18198 | 2.481 | 2.616 |
| 17 | `chord_sdf_range` | v08/scene/exact.py:158 | 380 | 1.906 | 21.490 |
| 18 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 7 | 1.815 | 137.226 |
| 19 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 805830 | 1.669 | 1.669 |
| 20 | `<built-in method builtins.min>` | ~:0 | 12154891 | 1.418 | 1.418 |
| 21 | `as_series` | numpy/polynomial/polyutils.py:63 | 1263624 | 1.357 | 4.182 |
| 22 | `common_type` | numpy/lib/_type_check_impl.py:661 | 1263736 | 1.150 | 2.044 |
| 23 | `<built-in method numpy.array>` | ~:0 | 3868807 | 0.926 | 0.926 |
| 24 | `evaluate` | v08/motion/optimize.py:83 | 1120 | 0.908 | 1.306 |
| 25 | `_alloc` | v08/motion/optimize.py:745 | 1924 | 0.833 | 1.714 |

### simulation — 按 cumulative（互斥墙钟 35.48 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `run_tracking_group` | v08/sim/tracking_batch.py:48 | 1 | 4.391 | 35.427 |
| 2 | `step` | v08/sim/kernel.py:27 | 128411 | 0.327 | 17.497 |
| 3 | `_pva` | v08/sim/tracking.py:74 | 1037385 | 1.085 | 12.169 |
| 4 | `step` | swarm_sim/fast_dynamics/plants.py:43 | 128411 | 0.868 | 11.048 |
| 5 | `pva` | v08/motion/optimize.py:108 | 1037394 | 7.766 | 10.248 |
| 6 | `command` | swarm_sim/fast_dynamics/controllers.py:18 | 128411 | 1.037 | 4.774 |
| 7 | `project_acceleration` | swarm_sim/fast_dynamics/plants.py:9 | 385233 | 2.012 | 4.639 |
| 8 | `dense_state` | swarm_sim/fast_dynamics/plants.py:18 | 154094 | 1.242 | 4.102 |
| 9 | `_array3` | swarm_sim/fast_dynamics/contracts.py:43 | 873201 | 1.231 | 3.263 |
| 10 | `allclose` | numpy/_core/numeric.py:2226 | 128411 | 0.148 | 2.890 |
| 11 | `norm` | numpy/linalg/_linalg.py:2598 | 642055 | 1.638 | 2.540 |
| 12 | `isclose` | numpy/_core/numeric.py:2320 | 128411 | 1.230 | 2.510 |
| 13 | `all` | numpy/_core/fromnumeric.py:2586 | 1258434 | 0.500 | 2.319 |
| 14 | `__post_init__` | swarm_sim/fast_dynamics/contracts.py:59 | 154095 | 0.245 | 1.900 |
| 15 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 1258434 | 0.899 | 1.819 |
| 16 | `clip` | numpy/_core/fromnumeric.py:2245 | 513698 | 0.305 | 1.235 |
| 17 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1930840 | 1.094 | 1.094 |
| 18 | `_wrapfunc` | numpy/_core/fromnumeric.py:48 | 513706 | 0.184 | 0.930 |
| 19 | `<built-in method builtins.isinstance>` | ~:0 | 2568463 | 0.379 | 0.860 |
| 20 | `ndim` | numpy/_core/fromnumeric.py:3520 | 1037394 | 0.634 | 0.823 |
| 21 | `at` | swarm_sim/fast_dynamics/engine.py:41 | 25683 | 0.020 | 0.756 |
| 22 | `_positive` | swarm_sim/fast_dynamics/contracts.py:30 | 462305 | 0.213 | 0.732 |
| 23 | `<built-in method numpy.asarray>` | ~:0 | 4970710 | 0.691 | 0.691 |
| 24 | `<method 'clip' of 'numpy.ndarray' objects>` | ~:0 | 513698 | 0.143 | 0.682 |
| 25 | `h` | v08/motion/optimize.py:75 | 2074805 | 0.622 | 0.622 |

### simulation — 按 tottime（互斥墙钟 35.48 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `pva` | v08/motion/optimize.py:108 | 1037394 | 7.766 | 10.248 |
| 2 | `run_tracking_group` | v08/sim/tracking_batch.py:48 | 1 | 4.391 | 35.427 |
| 3 | `project_acceleration` | swarm_sim/fast_dynamics/plants.py:9 | 385233 | 2.012 | 4.639 |
| 4 | `norm` | numpy/linalg/_linalg.py:2598 | 642055 | 1.638 | 2.540 |
| 5 | `dense_state` | swarm_sim/fast_dynamics/plants.py:18 | 154094 | 1.242 | 4.102 |
| 6 | `_array3` | swarm_sim/fast_dynamics/contracts.py:43 | 873201 | 1.231 | 3.263 |
| 7 | `isclose` | numpy/_core/numeric.py:2320 | 128411 | 1.230 | 2.510 |
| 8 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1930840 | 1.094 | 1.094 |
| 9 | `_pva` | v08/sim/tracking.py:74 | 1037385 | 1.085 | 12.169 |
| 10 | `command` | swarm_sim/fast_dynamics/controllers.py:18 | 128411 | 1.037 | 4.774 |
| 11 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 1258434 | 0.899 | 1.819 |
| 12 | `step` | swarm_sim/fast_dynamics/plants.py:43 | 128411 | 0.868 | 11.048 |
| 13 | `<built-in method numpy.asarray>` | ~:0 | 4970710 | 0.691 | 0.691 |
| 14 | `ndim` | numpy/_core/fromnumeric.py:3520 | 1037394 | 0.634 | 0.823 |
| 15 | `h` | v08/motion/optimize.py:75 | 2074805 | 0.622 | 0.622 |
| 16 | `<method 'reshape' of 'numpy.ndarray' objects>` | ~:0 | 3112255 | 0.612 | 0.612 |
| 17 | `_clip` | numpy/_core/_methods.py:96 | 513698 | 0.539 | 0.540 |
| 18 | `<built-in method numpy.array>` | ~:0 | 1258462 | 0.535 | 0.535 |
| 19 | `all` | numpy/_core/fromnumeric.py:2586 | 1258434 | 0.500 | 2.319 |
| 20 | `<method 'append' of 'list' objects>` | ~:0 | 5162083 | 0.458 | 0.458 |
| 21 | `<built-in method math.hypot>` | ~:0 | 4109096 | 0.453 | 0.453 |
| 22 | `<built-in method builtins.isinstance>` | ~:0 | 2568463 | 0.379 | 0.860 |
| 23 | `step` | v08/sim/kernel.py:27 | 128411 | 0.327 | 17.497 |
| 24 | `clip` | numpy/_core/fromnumeric.py:2245 | 513698 | 0.305 | 1.235 |
| 25 | `<built-in method builtins.min>` | ~:0 | 2074770 | 0.300 | 0.300 |

### verify — 按 cumulative（互斥墙钟 5.95 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `verify_segments` | v08/criteria/segment.py:78 | 1 | 0.000 | 5.802 |
| 2 | `measure_member_window` | v08/criteria/window.py:89 | 8 | 0.006 | 5.800 |
| 3 | `revisit` | task_v07/detectors.py:67 | 8 | 5.574 | 5.636 |
| 4 | `geometry_facts` | task_v07/geometry.py:15 | 48 | 0.127 | 0.214 |
| 5 | `check_validity` | v08/criteria/validity.py:72 | 1 | 0.026 | 0.142 |
| 6 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 3003 | 0.095 | 0.095 |
| 7 | `norm` | numpy/linalg/_linalg.py:2598 | 3907 | 0.022 | 0.063 |
| 8 | `sum` | numpy/_core/fromnumeric.py:2342 | 136 | 0.000 | 0.029 |
| 9 | `_wrapreduction` | numpy/_core/fromnumeric.py:66 | 136 | 0.000 | 0.029 |
| 10 | `_interp_min` | v08/criteria/validity.py:63 | 28 | 0.015 | 0.027 |
| 11 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 74884 | 0.023 | 0.023 |
| 12 | `<method 'min' of 'numpy.ndarray' objects>` | ~:0 | 48 | 0.000 | 0.015 |
| 13 | `_amin` | numpy/_core/_methods.py:43 | 48 | 0.000 | 0.015 |
| 14 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 144 | 0.000 | 0.012 |
| 15 | `all` | numpy/_core/fromnumeric.py:2586 | 80 | 0.000 | 0.012 |
| 16 | `intersect1d` | numpy/lib/_arraysetops_impl.py:666 | 28 | 0.009 | 0.010 |
| 17 | `dwell` | task_v07/detectors.py:32 | 16 | 0.005 | 0.008 |
| 18 | `_wrapfunc` | numpy/_core/fromnumeric.py:48 | 1380 | 0.001 | 0.008 |
| 19 | `<method 'append' of 'list' objects>` | ~:0 | 75372 | 0.007 | 0.007 |
| 20 | `azimuth_coverage` | task_v07/detectors.py:24 | 16 | 0.004 | 0.006 |
| 21 | `clip` | numpy/_core/fromnumeric.py:2245 | 1148 | 0.001 | 0.005 |
| 22 | `<built-in method numpy.array>` | ~:0 | 2380 | 0.005 | 0.005 |
| 23 | `approach_heading_deg` | task_v07/labels.py:117 | 8 | 0.001 | 0.004 |
| 24 | `<method 'clip' of 'numpy.ndarray' objects>` | ~:0 | 1148 | 0.000 | 0.004 |
| 25 | `_clip` | numpy/_core/_methods.py:96 | 1148 | 0.004 | 0.004 |

### verify — 按 tottime（互斥墙钟 5.95 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `revisit` | task_v07/detectors.py:67 | 8 | 5.574 | 5.636 |
| 2 | `geometry_facts` | task_v07/geometry.py:15 | 48 | 0.127 | 0.214 |
| 3 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 3003 | 0.095 | 0.095 |
| 4 | `check_validity` | v08/criteria/validity.py:72 | 1 | 0.026 | 0.142 |
| 5 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 74884 | 0.023 | 0.023 |
| 6 | `norm` | numpy/linalg/_linalg.py:2598 | 3907 | 0.022 | 0.063 |
| 7 | `_interp_min` | v08/criteria/validity.py:63 | 28 | 0.015 | 0.027 |
| 8 | `intersect1d` | numpy/lib/_arraysetops_impl.py:666 | 28 | 0.009 | 0.010 |
| 9 | `<method 'append' of 'list' objects>` | ~:0 | 75372 | 0.007 | 0.007 |
| 10 | `measure_member_window` | v08/criteria/window.py:89 | 8 | 0.006 | 5.800 |
| 11 | `<built-in method numpy.array>` | ~:0 | 2380 | 0.005 | 0.005 |
| 12 | `dwell` | task_v07/detectors.py:32 | 16 | 0.005 | 0.008 |
| 13 | `azimuth_coverage` | task_v07/detectors.py:24 | 16 | 0.004 | 0.006 |
| 14 | `_clip` | numpy/_core/_methods.py:96 | 1148 | 0.004 | 0.004 |
| 15 | `unwrap` | numpy/lib/_function_base_impl.py:1751 | 8 | 0.002 | 0.003 |
| 16 | `<method 'argsort' of 'numpy.ndarray' objects>` | ~:0 | 28 | 0.002 | 0.002 |
| 17 | `<built-in method builtins.sorted>` | ~:0 | 2267 | 0.002 | 0.002 |
| 18 | `visible_track` | v08/criteria/validity.py:43 | 8 | 0.002 | 0.002 |
| 19 | `approach_heading_deg` | task_v07/labels.py:117 | 8 | 0.001 | 0.004 |
| 20 | `<method 'nonzero' of 'numpy.ndarray' objects>` | ~:0 | 140 | 0.001 | 0.001 |
| 21 | `<method 'sort' of 'numpy.ndarray' objects>` | ~:0 | 16 | 0.001 | 0.001 |
| 22 | `diff` | numpy/lib/_function_base_impl.py:1413 | 92 | 0.001 | 0.001 |
| 23 | `stitch` | v08/sim/stitch.py:50 | 1 | 0.001 | 0.001 |
| 24 | `clip` | numpy/_core/fromnumeric.py:2245 | 1148 | 0.001 | 0.005 |
| 25 | `<method 'dot' of 'numpy.ndarray' objects>` | ~:0 | 1496 | 0.001 | 0.001 |

## o05_d3（|wall_s − 中位数 68.552| 最小；基线 wall 68.4 s，剖析 wall 60.7 s）

### orchestration — 按 cumulative（互斥墙钟 3.07 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `save_contract` | v08/runner/joint_monitoring.py:321 | 1 | 0.013 | 2.927 |
| 2 | `jsonable` | v08/runner/monitoring.py:72 | 2870642 | 1.572 | 2.316 |
| 3 | `_json_bytes` | v08/runner/joint_monitoring.py:317 | 5 | 0.003 | 2.234 |
| 4 | `canonical_json` | v08/runner/monitoring.py:97 | 5 | 0.008 | 2.231 |
| 5 | `plan_to_record` | v08/runner/monitoring.py:112 | 1 | 0.000 | 0.621 |
| 6 | `<built-in method builtins.isinstance>` | ~:0 | 9735829 | 0.558 | 0.558 |
| 7 | `dumps` | C:/Users/shy/anaconda3/envs/llm/Lib/json/__init__.py:183 | 7 | 0.000 | 0.498 |
| 8 | `encode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:183 | 7 | 0.000 | 0.498 |
| 9 | `iterencode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:205 | 7 | 0.498 | 0.498 |
| 10 | `<built-in method math.isfinite>` | ~:0 | 2173496 | 0.107 | 0.107 |
| 11 | `is_dataclass` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1294 | 314301 | 0.061 | 0.093 |
| 12 | `phase_diagnostics` | v08/runner/joint_monitoring.py:529 | 1 | 0.005 | 0.063 |
| 13 | `<built-in method numpy.asarray>` | ~:0 | 470 | 0.029 | 0.029 |
| 14 | `__call__` | v08/motion/skeleton.py:54 | 18 | 0.023 | 0.028 |
| 15 | `save` | numpy/lib/_npyio_impl.py:504 | 45 | 0.000 | 0.027 |
| 16 | `evaluate` | v08/motion/optimize.py:83 | 27 | 0.019 | 0.026 |
| 17 | `member_deviation` | v08/runner/joint_monitoring.py:515 | 1 | 0.001 | 0.024 |
| 18 | `phase_metrics` | v08/diagnostics/monitoring_skeleton.py:25 | 9 | 0.010 | 0.020 |
| 19 | `<built-in method builtins.hasattr>` | ~:0 | 314420 | 0.017 | 0.017 |
| 20 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 28 | 0.015 | 0.015 |
| 21 | `write_array` | numpy/lib/_format_impl.py:702 | 45 | 0.000 | 0.013 |
| 22 | `_find_and_load` | <frozen importlib._bootstrap>:1349 | 16 | 0.000 | 0.012 |
| 23 | `_find_and_load_unlocked` | <frozen importlib._bootstrap>:1304 | 16 | 0.000 | 0.012 |
| 24 | `<built-in method _io.open>` | ~:0 | 60 | 0.012 | 0.012 |
| 25 | `_load_unlocked` | <frozen importlib._bootstrap>:911 | 16 | 0.000 | 0.012 |

### orchestration — 按 tottime（互斥墙钟 3.07 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `jsonable` | v08/runner/monitoring.py:72 | 2870642 | 1.572 | 2.316 |
| 2 | `<built-in method builtins.isinstance>` | ~:0 | 9735829 | 0.558 | 0.558 |
| 3 | `iterencode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:205 | 7 | 0.498 | 0.498 |
| 4 | `<built-in method math.isfinite>` | ~:0 | 2173496 | 0.107 | 0.107 |
| 5 | `is_dataclass` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1294 | 314301 | 0.061 | 0.093 |
| 6 | `<built-in method numpy.asarray>` | ~:0 | 470 | 0.029 | 0.029 |
| 7 | `__call__` | v08/motion/skeleton.py:54 | 18 | 0.023 | 0.028 |
| 8 | `evaluate` | v08/motion/optimize.py:83 | 27 | 0.019 | 0.026 |
| 9 | `<built-in method builtins.hasattr>` | ~:0 | 314420 | 0.017 | 0.017 |
| 10 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 28 | 0.015 | 0.015 |
| 11 | `save_contract` | v08/runner/joint_monitoring.py:321 | 1 | 0.013 | 2.927 |
| 12 | `<built-in method _io.open>` | ~:0 | 60 | 0.012 | 0.012 |
| 13 | `<method 'tofile' of 'numpy.ndarray' objects>` | ~:0 | 45 | 0.011 | 0.011 |
| 14 | `phase_metrics` | v08/diagnostics/monitoring_skeleton.py:25 | 9 | 0.010 | 0.020 |
| 15 | `<method 'write' of '_io.BufferedWriter' objects>` | ~:0 | 50 | 0.009 | 0.009 |
| 16 | `canonical_json` | v08/runner/monitoring.py:97 | 5 | 0.008 | 2.231 |
| 17 | `<method 'searchsorted' of 'numpy.ndarray' objects>` | ~:0 | 27 | 0.007 | 0.007 |
| 18 | `phase_diagnostics` | v08/runner/joint_monitoring.py:529 | 1 | 0.005 | 0.063 |
| 19 | `_speed` | v08/diagnostics/monitoring_skeleton.py:20 | 63 | 0.004 | 0.004 |
| 20 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 576 | 0.004 | 0.004 |
| 21 | `<built-in method nt.mkdir>` | ~:0 | 17 | 0.003 | 0.004 |
| 22 | `_json_bytes` | v08/runner/joint_monitoring.py:317 | 5 | 0.003 | 2.234 |
| 23 | `<method '__exit__' of '_io._IOBase' objects>` | ~:0 | 66 | 0.003 | 0.003 |
| 24 | `<built-in method numpy._core._multiarray_umath.c_einsum>` | ~:0 | 27 | 0.003 | 0.003 |
| 25 | `<built-in method _imp.create_dynamic>` | ~:0 | 9 | 0.003 | 0.003 |

### skeleton — 按 cumulative（互斥墙钟 8.75 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `plan_attempt` | v08/motion/plan.py:34 | 2 | 0.000 | 8.750 |
| 2 | `propose_and_build` | v08/motion/intents/monitoring.py:1448 | 2 | 0.000 | 8.707 |
| 3 | `width_then_build` | v08/motion/skeleton.py:26 | 2 | 0.000 | 8.432 |
| 4 | `build` | v08/motion/intents/monitoring.py:1481 | 2 | 0.000 | 7.138 |
| 5 | `_build_with_ring` | v08/motion/intents/monitoring.py:1376 | 2 | 0.000 | 7.138 |
| 6 | `_finish_loop` | v08/motion/intents/monitoring.py:1326 | 2 | 0.000 | 7.062 |
| 7 | `assemble` | v08/motion/intents/monitoring.py:1304 | 2 | 0.013 | 6.081 |
| 8 | `build_candidate` | v08/motion/intents/monitoring.py:215 | 2 | 0.048 | 5.536 |
| 9 | `screen_member` | v08/motion/nominal_checks.py:156 | 9 | 0.001 | 2.207 |
| 10 | `revisit` | v08/motion/nominal_checks.py:77 | 9 | 2.138 | 2.168 |
| 11 | `speed_profile` | v08/sim/guidance.py:88 | 55 | 1.244 | 1.789 |
| 12 | `width_probe` | v08/motion/intents/monitoring.py:1473 | 2 | 0.000 | 1.294 |
| 13 | `_band_probe` | v08/motion/intents/monitoring.py:802 | 2 | 0.000 | 1.294 |
| 14 | `build_band_query` | v08/motion/monitoring_band.py:796 | 2 | 0.000 | 1.294 |
| 15 | `_release_delays_ref` | v08/motion/intents/monitoring.py:470 | 2 | 0.246 | 1.118 |
| 16 | `chord_sdf_range` | v08/scene/exact.py:158 | 36 | 0.114 | 1.037 |
| 17 | `prepare` | v08/motion/intents/monitoring.py:1281 | 2 | 0.000 | 0.981 |
| 18 | `map_speed_events` | v08/motion/speed.py:51 | 2 | 0.001 | 0.969 |
| 19 | `band_geometry` | v08/motion/intents/monitoring.py:572 | 2 | 0.000 | 0.897 |
| 20 | `__init__` | v08/motion/monitoring_band.py:468 | 2 | 0.002 | 0.897 |
| 21 | `member_nominal` | v08/motion/nominal.py:54 | 18 | 0.002 | 0.871 |
| 22 | `radial_margins` | v08/motion/monitoring_band.py:197 | 2 | 0.021 | 0.836 |
| 23 | `connect_poses` | v08/motion/path.py:331 | 108 | 0.014 | 0.816 |
| 24 | `_poly_sdf` | v08/scene/exact.py:90 | 194 | 0.454 | 0.722 |
| 25 | `_plan_ingress` | v08/motion/intents/monitoring.py:1068 | 2 | 0.012 | 0.683 |

### skeleton — 按 tottime（互斥墙钟 8.75 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `revisit` | v08/motion/nominal_checks.py:77 | 9 | 2.138 | 2.168 |
| 2 | `speed_profile` | v08/sim/guidance.py:88 | 55 | 1.244 | 1.789 |
| 3 | `_poly_sdf` | v08/scene/exact.py:90 | 194 | 0.454 | 0.722 |
| 4 | `_seg_point_dist` | v08/scene/exact.py:148 | 72 | 0.452 | 0.551 |
| 5 | `<built-in method numpy._core._multiarray_umath.c_einsum>` | ~:0 | 324 | 0.441 | 0.441 |
| 6 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 26270 | 0.412 | 0.412 |
| 7 | `<genexpr>` | v08/motion/intents/monitoring.py:319 | 608143 | 0.379 | 0.379 |
| 8 | `<built-in method builtins.min>` | ~:0 | 2962670 | 0.343 | 0.343 |
| 9 | `_release_delays_ref` | v08/motion/intents/monitoring.py:470 | 2 | 0.246 | 1.118 |
| 10 | `intersects` | shapely/predicates.py:747 | 292 | 0.212 | 0.212 |
| 11 | `<built-in method math.sqrt>` | ~:0 | 2950221 | 0.197 | 0.197 |
| 12 | `value` | v08/scene/field.py:158 | 6738 | 0.163 | 0.355 |
| 13 | `chord_sdf_range` | v08/scene/exact.py:158 | 36 | 0.114 | 1.037 |
| 14 | `_bezier_batch` | v08/motion/path.py:310 | 108 | 0.111 | 0.554 |
| 15 | `<method 'decompress' of 'zlib.Decompress' objects>` | ~:0 | 224 | 0.104 | 0.104 |
| 16 | `_locate` | v08/scene/field.py:86 | 6738 | 0.087 | 0.187 |
| 17 | `_linprog_highs` | scipy/optimize/_linprog_highs.py:109 | 4 | 0.071 | 0.073 |
| 18 | `<built-in method nt.stat>` | ~:0 | 1512 | 0.066 | 0.067 |
| 19 | `_clip` | numpy/_core/_methods.py:96 | 27500 | 0.064 | 0.078 |
| 20 | `_transform` | v08/scene/field.py:34 | 36 | 0.061 | 0.061 |
| 21 | `<built-in method numpy.asarray>` | ~:0 | 50291 | 0.060 | 0.060 |
| 22 | `_lane_cross_ok` | v08/motion/intents/monitoring.py:1048 | 240 | 0.049 | 0.090 |
| 23 | `build_candidate` | v08/motion/intents/monitoring.py:215 | 2 | 0.048 | 5.536 |
| 24 | `signed_distance` | v08/scene/exact.py:105 | 2605 | 0.045 | 0.463 |
| 25 | `_line_lanes_ok` | v08/motion/intents/monitoring.py:1022 | 457 | 0.045 | 0.223 |

### optimize — 按 cumulative（互斥墙钟 18.58 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `capture` | tools/v08/profile_monitoring_v15.py:391 | 1 | 0.000 | 18.576 |
| 2 | `optimize_segment` | v08/motion/optimize.py:926 | 1 | 0.012 | 18.575 |
| 3 | `solve_joint` | v08/motion/optimize.py:837 | 1 | 0.004 | 14.860 |
| 4 | `minimize` | scipy/optimize/_minimize.py:53 | 1 | 0.000 | 14.012 |
| 5 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 1 | 0.205 | 14.012 |
| 6 | `_update_fun` | scipy/optimize/_differentiable_functions.py:292 | 261 | 0.001 | 13.775 |
| 7 | `wrapped` | scipy/optimize/_differentiable_functions.py:15 | 260 | 0.003 | 13.774 |
| 8 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 520 | 0.401 | 13.772 |
| 9 | `__call__` | scipy/optimize/_optimize.py:77 | 260 | 0.000 | 13.768 |
| 10 | `fun_and_grad` | scipy/optimize/_differentiable_functions.py:340 | 260 | 0.001 | 13.743 |
| 11 | `value_grad` | v08/motion/optimize.py:773 | 261 | 0.847 | 13.413 |
| 12 | `_blocks` | v08/motion/optimize.py:636 | 263 | 2.627 | 9.033 |
| 13 | `eval` | v08/motion/optimize.py:299 | 11880 | 4.773 | 5.439 |
| 14 | `check_monitoring` | v08/motion/optimize_checks.py:363 | 1 | 0.002 | 2.874 |
| 15 | `screen_member` | v08/motion/nominal_checks.py:156 | 9 | 0.001 | 2.264 |
| 16 | `revisit` | v08/motion/nominal_checks.py:77 | 9 | 2.198 | 2.228 |
| 17 | `__matmul__` | scipy/sparse/_base.py:665 | 28593 | 0.015 | 1.928 |
| 18 | `_matmul_dispatch` | scipy/sparse/_base.py:544 | 28602 | 0.029 | 1.841 |
| 19 | `_matmul_multivector` | scipy/sparse/_compressed.py:496 | 23769 | 0.060 | 1.746 |
| 20 | `bp_t` | v08/motion/optimize.py:665 | 2131 | 1.272 | 1.279 |
| 21 | `references_from_skeleton` | v08/motion/skeleton.py:179 | 1 | 0.000 | 0.823 |
| 22 | `<built-in method scipy.sparse._sparsetools.csr_matvecs>` | ~:0 | 12006 | 0.789 | 0.789 |
| 23 | `member_nominal` | v08/motion/nominal.py:54 | 18 | 0.001 | 0.770 |
| 24 | `<built-in method scipy.sparse._sparsetools.csc_matvecs>` | ~:0 | 11763 | 0.749 | 0.749 |
| 25 | `speed_profile` | v08/sim/guidance.py:88 | 18 | 0.473 | 0.681 |

### optimize — 按 tottime（互斥墙钟 18.58 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `eval` | v08/motion/optimize.py:299 | 11880 | 4.773 | 5.439 |
| 2 | `_blocks` | v08/motion/optimize.py:636 | 263 | 2.627 | 9.033 |
| 3 | `revisit` | v08/motion/nominal_checks.py:77 | 9 | 2.198 | 2.228 |
| 4 | `bp_t` | v08/motion/optimize.py:665 | 2131 | 1.272 | 1.279 |
| 5 | `value_grad` | v08/motion/optimize.py:773 | 261 | 0.847 | 13.413 |
| 6 | `<built-in method scipy.sparse._sparsetools.csr_matvecs>` | ~:0 | 12006 | 0.789 | 0.789 |
| 7 | `<built-in method scipy.sparse._sparsetools.csc_matvecs>` | ~:0 | 11763 | 0.749 | 0.749 |
| 8 | `speed_profile` | v08/sim/guidance.py:88 | 18 | 0.473 | 0.681 |
| 9 | `solve_banded` | scipy/linalg/_basic.py:370 | 4761 | 0.467 | 0.586 |
| 10 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 520 | 0.401 | 13.772 |
| 11 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 96819 | 0.357 | 0.357 |
| 12 | `_clip` | numpy/_core/_methods.py:96 | 72258 | 0.342 | 0.376 |
| 13 | `_seg_point_dist` | v08/scene/exact.py:148 | 72 | 0.220 | 0.263 |
| 14 | `<built-in method numpy.zeros>` | ~:0 | 49862 | 0.216 | 0.216 |
| 15 | `_poly_sdf` | v08/scene/exact.py:90 | 99 | 0.210 | 0.341 |
| 16 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 1 | 0.205 | 14.012 |
| 17 | `eigvals` | numpy/linalg/_linalg.py:1181 | 180 | 0.186 | 0.187 |
| 18 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 67442 | 0.170 | 0.170 |
| 19 | `<built-in method builtins.min>` | ~:0 | 1098555 | 0.130 | 0.130 |
| 20 | `_alloc` | v08/motion/optimize.py:745 | 263 | 0.116 | 0.202 |
| 21 | `evaluate` | v08/motion/optimize.py:83 | 189 | 0.086 | 0.117 |
| 22 | `<built-in method math.sqrt>` | ~:0 | 1097874 | 0.075 | 0.075 |
| 23 | `get_index_dtype` | scipy/sparse/_sputils.py:149 | 14823 | 0.064 | 0.098 |
| 24 | `chord_sdf_range` | v08/scene/exact.py:158 | 72 | 0.064 | 0.517 |
| 25 | `<built-in method numpy.asarray>` | ~:0 | 49792 | 0.062 | 0.062 |

### simulation — 按 cumulative（互斥墙钟 27.69 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `run_tracking_group` | v08/sim/tracking_batch.py:48 | 1 | 3.468 | 27.638 |
| 2 | `step` | v08/sim/kernel.py:27 | 98027 | 0.244 | 13.282 |
| 3 | `_pva` | v08/sim/tracking.py:74 | 843225 | 0.872 | 9.854 |
| 4 | `step` | swarm_sim/fast_dynamics/plants.py:43 | 98027 | 0.659 | 8.391 |
| 5 | `pva` | v08/motion/optimize.py:108 | 843235 | 6.331 | 8.303 |
| 6 | `command` | swarm_sim/fast_dynamics/controllers.py:18 | 98027 | 0.785 | 3.620 |
| 7 | `project_acceleration` | swarm_sim/fast_dynamics/plants.py:9 | 294081 | 1.537 | 3.523 |
| 8 | `dense_state` | swarm_sim/fast_dynamics/plants.py:18 | 117633 | 0.943 | 3.111 |
| 9 | `_array3` | swarm_sim/fast_dynamics/contracts.py:43 | 666589 | 0.938 | 2.473 |
| 10 | `allclose` | numpy/_core/numeric.py:2226 | 98027 | 0.112 | 2.200 |
| 11 | `norm` | numpy/linalg/_linalg.py:2598 | 490135 | 1.239 | 1.926 |
| 12 | `isclose` | numpy/_core/numeric.py:2320 | 98027 | 0.927 | 1.913 |
| 13 | `all` | numpy/_core/fromnumeric.py:2586 | 960670 | 0.371 | 1.750 |
| 14 | `__post_init__` | swarm_sim/fast_dynamics/contracts.py:59 | 117634 | 0.187 | 1.438 |
| 15 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 960670 | 0.678 | 1.379 |
| 16 | `clip` | numpy/_core/fromnumeric.py:2245 | 392168 | 0.228 | 0.929 |
| 17 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1455840 | 0.830 | 0.830 |
| 18 | `_wrapfunc` | numpy/_core/fromnumeric.py:48 | 392177 | 0.139 | 0.701 |
| 19 | `ndim` | numpy/_core/fromnumeric.py:3520 | 843235 | 0.506 | 0.660 |
| 20 | `<built-in method builtins.isinstance>` | ~:0 | 1960786 | 0.287 | 0.655 |
| 21 | `at` | swarm_sim/fast_dynamics/engine.py:41 | 19606 | 0.015 | 0.575 |
| 22 | `_positive` | swarm_sim/fast_dynamics/contracts.py:30 | 352922 | 0.164 | 0.558 |
| 23 | `<built-in method numpy.asarray>` | ~:0 | 3969586 | 0.557 | 0.557 |
| 24 | `<method 'clip' of 'numpy.ndarray' objects>` | ~:0 | 392168 | 0.107 | 0.514 |
| 25 | `h` | v08/motion/optimize.py:75 | 1686489 | 0.499 | 0.499 |

### simulation — 按 tottime（互斥墙钟 27.69 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `pva` | v08/motion/optimize.py:108 | 843235 | 6.331 | 8.303 |
| 2 | `run_tracking_group` | v08/sim/tracking_batch.py:48 | 1 | 3.468 | 27.638 |
| 3 | `project_acceleration` | swarm_sim/fast_dynamics/plants.py:9 | 294081 | 1.537 | 3.523 |
| 4 | `norm` | numpy/linalg/_linalg.py:2598 | 490135 | 1.239 | 1.926 |
| 5 | `dense_state` | swarm_sim/fast_dynamics/plants.py:18 | 117633 | 0.943 | 3.111 |
| 6 | `_array3` | swarm_sim/fast_dynamics/contracts.py:43 | 666589 | 0.938 | 2.473 |
| 7 | `isclose` | numpy/_core/numeric.py:2320 | 98027 | 0.927 | 1.913 |
| 8 | `_pva` | v08/sim/tracking.py:74 | 843225 | 0.872 | 9.854 |
| 9 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1455840 | 0.830 | 0.830 |
| 10 | `command` | swarm_sim/fast_dynamics/controllers.py:18 | 98027 | 0.785 | 3.620 |
| 11 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 960670 | 0.678 | 1.379 |
| 12 | `step` | swarm_sim/fast_dynamics/plants.py:43 | 98027 | 0.659 | 8.391 |
| 13 | `<built-in method numpy.asarray>` | ~:0 | 3969586 | 0.557 | 0.557 |
| 14 | `ndim` | numpy/_core/fromnumeric.py:3520 | 843235 | 0.506 | 0.660 |
| 15 | `h` | v08/motion/optimize.py:75 | 1686489 | 0.499 | 0.499 |
| 16 | `<method 'reshape' of 'numpy.ndarray' objects>` | ~:0 | 2529786 | 0.490 | 0.490 |
| 17 | `_clip` | numpy/_core/_methods.py:96 | 392168 | 0.406 | 0.406 |
| 18 | `<built-in method numpy.array>` | ~:0 | 960701 | 0.401 | 0.401 |
| 19 | `all` | numpy/_core/fromnumeric.py:2586 | 960670 | 0.371 | 1.750 |
| 20 | `<built-in method math.hypot>` | ~:0 | 3366214 | 0.362 | 0.362 |
| 21 | `<method 'append' of 'list' objects>` | ~:0 | 4227407 | 0.359 | 0.359 |
| 22 | `<built-in method builtins.isinstance>` | ~:0 | 1960786 | 0.287 | 0.655 |
| 23 | `step` | v08/sim/kernel.py:27 | 98027 | 0.244 | 13.282 |
| 24 | `<built-in method builtins.min>` | ~:0 | 1686450 | 0.240 | 0.240 |
| 25 | `clip` | numpy/_core/fromnumeric.py:2245 | 392168 | 0.228 | 0.929 |

### verify — 按 cumulative（互斥墙钟 2.56 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `verify_segments` | v08/criteria/segment.py:78 | 1 | 0.000 | 2.413 |
| 2 | `measure_member_window` | v08/criteria/window.py:89 | 9 | 0.004 | 2.412 |
| 3 | `revisit` | task_v07/detectors.py:67 | 9 | 2.247 | 2.279 |
| 4 | `geometry_facts` | task_v07/geometry.py:15 | 72 | 0.117 | 0.195 |
| 5 | `check_validity` | v08/criteria/validity.py:72 | 1 | 0.025 | 0.146 |
| 6 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1575 | 0.084 | 0.084 |
| 7 | `norm` | numpy/linalg/_linalg.py:2598 | 2007 | 0.017 | 0.053 |
| 8 | `sum` | numpy/_core/fromnumeric.py:2342 | 162 | 0.000 | 0.027 |
| 9 | `_wrapreduction` | numpy/_core/fromnumeric.py:66 | 162 | 0.000 | 0.027 |
| 10 | `_interp_min` | v08/criteria/validity.py:63 | 36 | 0.014 | 0.025 |
| 11 | `<method 'min' of 'numpy.ndarray' objects>` | ~:0 | 54 | 0.000 | 0.013 |
| 12 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 41097 | 0.013 | 0.013 |
| 13 | `_amin` | numpy/_core/_methods.py:43 | 54 | 0.000 | 0.013 |
| 14 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 162 | 0.000 | 0.010 |
| 15 | `all` | numpy/_core/fromnumeric.py:2586 | 90 | 0.000 | 0.010 |
| 16 | `intersect1d` | numpy/lib/_arraysetops_impl.py:666 | 36 | 0.008 | 0.010 |
| 17 | `dwell` | task_v07/detectors.py:32 | 18 | 0.004 | 0.007 |
| 18 | `azimuth_coverage` | task_v07/detectors.py:24 | 18 | 0.003 | 0.005 |
| 19 | `_wrapfunc` | numpy/_core/fromnumeric.py:48 | 537 | 0.000 | 0.004 |
| 20 | `<method 'append' of 'list' objects>` | ~:0 | 41650 | 0.004 | 0.004 |
| 21 | `approach_heading_deg` | task_v07/labels.py:117 | 9 | 0.001 | 0.003 |
| 22 | `unwrap` | numpy/lib/_function_base_impl.py:1751 | 9 | 0.001 | 0.002 |
| 23 | `clip` | numpy/_core/fromnumeric.py:2245 | 258 | 0.000 | 0.002 |
| 24 | `flatnonzero` | numpy/_core/numeric.py:675 | 162 | 0.000 | 0.002 |
| 25 | `argsort` | numpy/_core/fromnumeric.py:1115 | 36 | 0.000 | 0.001 |

### verify — 按 tottime（互斥墙钟 2.56 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `revisit` | task_v07/detectors.py:67 | 9 | 2.247 | 2.279 |
| 2 | `geometry_facts` | task_v07/geometry.py:15 | 72 | 0.117 | 0.195 |
| 3 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 1575 | 0.084 | 0.084 |
| 4 | `check_validity` | v08/criteria/validity.py:72 | 1 | 0.025 | 0.146 |
| 5 | `norm` | numpy/linalg/_linalg.py:2598 | 2007 | 0.017 | 0.053 |
| 6 | `_interp_min` | v08/criteria/validity.py:63 | 36 | 0.014 | 0.025 |
| 7 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 41097 | 0.013 | 0.013 |
| 8 | `intersect1d` | numpy/lib/_arraysetops_impl.py:666 | 36 | 0.008 | 0.010 |
| 9 | `measure_member_window` | v08/criteria/window.py:89 | 9 | 0.004 | 2.412 |
| 10 | `<method 'append' of 'list' objects>` | ~:0 | 41650 | 0.004 | 0.004 |
| 11 | `dwell` | task_v07/detectors.py:32 | 18 | 0.004 | 0.007 |
| 12 | `azimuth_coverage` | task_v07/detectors.py:24 | 18 | 0.003 | 0.005 |
| 13 | `unwrap` | numpy/lib/_function_base_impl.py:1751 | 9 | 0.001 | 0.002 |
| 14 | `<method 'argsort' of 'numpy.ndarray' objects>` | ~:0 | 36 | 0.001 | 0.001 |
| 15 | `visible_track` | v08/criteria/validity.py:43 | 9 | 0.001 | 0.001 |
| 16 | `approach_heading_deg` | task_v07/labels.py:117 | 9 | 0.001 | 0.003 |
| 17 | `_clip` | numpy/_core/_methods.py:96 | 258 | 0.001 | 0.001 |
| 18 | `<method 'nonzero' of 'numpy.ndarray' objects>` | ~:0 | 162 | 0.001 | 0.001 |
| 19 | `<built-in method numpy.array>` | ~:0 | 820 | 0.001 | 0.001 |
| 20 | `<method 'sort' of 'numpy.ndarray' objects>` | ~:0 | 18 | 0.001 | 0.001 |
| 21 | `diff` | numpy/lib/_function_base_impl.py:1413 | 108 | 0.001 | 0.001 |
| 22 | `stitch` | v08/sim/stitch.py:50 | 1 | 0.001 | 0.001 |
| 23 | `roll` | numpy/_core/numeric.py:1226 | 45 | 0.001 | 0.001 |
| 24 | `<method 'dot' of 'numpy.ndarray' objects>` | ~:0 | 1125 | 0.001 | 0.001 |
| 25 | `<built-in method builtins.sorted>` | ~:0 | 692 | 0.000 | 0.000 |

## o16_d3（|wall_s − 中位数 68.552| 最小；基线 wall 68.7 s，剖析 wall 67.3 s）

### orchestration — 按 cumulative（互斥墙钟 2.13 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `save_contract` | v08/runner/joint_monitoring.py:321 | 1 | 0.005 | 2.039 |
| 2 | `jsonable` | v08/runner/monitoring.py:72 | 2073304 | 1.116 | 1.643 |
| 3 | `_json_bytes` | v08/runner/joint_monitoring.py:317 | 5 | 0.002 | 1.548 |
| 4 | `canonical_json` | v08/runner/monitoring.py:97 | 5 | 0.005 | 1.546 |
| 5 | `plan_to_record` | v08/runner/monitoring.py:112 | 1 | 0.000 | 0.457 |
| 6 | `<built-in method builtins.isinstance>` | ~:0 | 6951771 | 0.397 | 0.397 |
| 7 | `dumps` | C:/Users/shy/anaconda3/envs/llm/Lib/json/__init__.py:183 | 7 | 0.000 | 0.332 |
| 8 | `encode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:183 | 7 | 0.000 | 0.332 |
| 9 | `iterencode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:205 | 7 | 0.332 | 0.332 |
| 10 | `<built-in method math.isfinite>` | ~:0 | 1575039 | 0.077 | 0.077 |
| 11 | `is_dataclass` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1294 | 215888 | 0.041 | 0.063 |
| 12 | `phase_diagnostics` | v08/runner/joint_monitoring.py:529 | 1 | 0.004 | 0.044 |
| 13 | `<built-in method numpy.asarray>` | ~:0 | 158 | 0.022 | 0.022 |
| 14 | `__call__` | v08/motion/skeleton.py:54 | 6 | 0.018 | 0.022 |
| 15 | `evaluate` | v08/motion/optimize.py:83 | 9 | 0.014 | 0.021 |
| 16 | `member_deviation` | v08/runner/joint_monitoring.py:515 | 1 | 0.001 | 0.021 |
| 17 | `phase_metrics` | v08/diagnostics/monitoring_skeleton.py:25 | 3 | 0.007 | 0.012 |
| 18 | `_find_and_load` | <frozen importlib._bootstrap>:1349 | 16 | 0.000 | 0.011 |
| 19 | `_find_and_load_unlocked` | <frozen importlib._bootstrap>:1304 | 16 | 0.000 | 0.011 |
| 20 | `<built-in method builtins.hasattr>` | ~:0 | 215952 | 0.011 | 0.011 |
| 21 | `_load_unlocked` | <frozen importlib._bootstrap>:911 | 16 | 0.000 | 0.011 |
| 22 | `exec_module` | <frozen importlib._bootstrap_external>:989 | 6 | 0.000 | 0.011 |
| 23 | `run_contract` | v08/runner/joint_monitoring.py:217 | 1 | 0.000 | 0.011 |
| 24 | `sample_common` | v08/sampler/common.py:11 | 1 | 0.000 | 0.010 |
| 25 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 10 | 0.010 | 0.010 |

### orchestration — 按 tottime（互斥墙钟 2.13 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `jsonable` | v08/runner/monitoring.py:72 | 2073304 | 1.116 | 1.643 |
| 2 | `<built-in method builtins.isinstance>` | ~:0 | 6951771 | 0.397 | 0.397 |
| 3 | `iterencode` | C:/Users/shy/anaconda3/envs/llm/Lib/json/encoder.py:205 | 7 | 0.332 | 0.332 |
| 4 | `<built-in method math.isfinite>` | ~:0 | 1575039 | 0.077 | 0.077 |
| 5 | `is_dataclass` | C:/Users/shy/anaconda3/envs/llm/Lib/dataclasses.py:1294 | 215888 | 0.041 | 0.063 |
| 6 | `<built-in method numpy.asarray>` | ~:0 | 158 | 0.022 | 0.022 |
| 7 | `__call__` | v08/motion/skeleton.py:54 | 6 | 0.018 | 0.022 |
| 8 | `evaluate` | v08/motion/optimize.py:83 | 9 | 0.014 | 0.021 |
| 9 | `<built-in method builtins.hasattr>` | ~:0 | 215952 | 0.011 | 0.011 |
| 10 | `<method 'tolist' of 'numpy.ndarray' objects>` | ~:0 | 10 | 0.010 | 0.010 |
| 11 | `phase_metrics` | v08/diagnostics/monitoring_skeleton.py:25 | 3 | 0.007 | 0.012 |
| 12 | `save_contract` | v08/runner/joint_monitoring.py:321 | 1 | 0.005 | 2.039 |
| 13 | `<method 'searchsorted' of 'numpy.ndarray' objects>` | ~:0 | 9 | 0.005 | 0.005 |
| 14 | `<method 'tofile' of 'numpy.ndarray' objects>` | ~:0 | 15 | 0.005 | 0.005 |
| 15 | `canonical_json` | v08/runner/monitoring.py:97 | 5 | 0.005 | 1.546 |
| 16 | `<method 'write' of '_io.BufferedWriter' objects>` | ~:0 | 20 | 0.004 | 0.004 |
| 17 | `<built-in method _io.open>` | ~:0 | 24 | 0.004 | 0.005 |
| 18 | `phase_diagnostics` | v08/runner/joint_monitoring.py:529 | 1 | 0.004 | 0.044 |
| 19 | `_speed` | v08/diagnostics/monitoring_skeleton.py:20 | 21 | 0.003 | 0.003 |
| 20 | `basis_weights` | v08/motion/optimize.py:159 | 9 | 0.003 | 0.005 |
| 21 | `<built-in method _imp.create_dynamic>` | ~:0 | 9 | 0.003 | 0.003 |
| 22 | `_json_bytes` | v08/runner/joint_monitoring.py:317 | 5 | 0.002 | 1.548 |
| 23 | `<built-in method nt.stat>` | ~:0 | 49 | 0.002 | 0.002 |
| 24 | `<built-in method numpy._core._multiarray_umath.c_einsum>` | ~:0 | 9 | 0.002 | 0.002 |
| 25 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 192 | 0.002 | 0.002 |

### skeleton — 按 cumulative（互斥墙钟 9.46 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `plan_attempt` | v08/motion/plan.py:34 | 1 | 0.000 | 9.462 |
| 2 | `propose_and_build` | v08/motion/intents/monitoring.py:1448 | 1 | 0.000 | 9.420 |
| 3 | `width_then_build` | v08/motion/skeleton.py:26 | 1 | 0.000 | 9.101 |
| 4 | `build` | v08/motion/intents/monitoring.py:1481 | 1 | 0.000 | 7.678 |
| 5 | `_build_with_ring` | v08/motion/intents/monitoring.py:1376 | 1 | 0.000 | 7.678 |
| 6 | `_finish_loop` | v08/motion/intents/monitoring.py:1326 | 1 | 0.000 | 7.638 |
| 7 | `assemble` | v08/motion/intents/monitoring.py:1304 | 1 | 0.003 | 7.594 |
| 8 | `build_candidate` | v08/motion/intents/monitoring.py:215 | 1 | 0.019 | 7.475 |
| 9 | `speed_profile` | v08/sim/guidance.py:88 | 85 | 3.331 | 4.793 |
| 10 | `map_speed_events` | v08/motion/speed.py:51 | 1 | 0.001 | 4.571 |
| 11 | `screen_member` | v08/motion/nominal_checks.py:156 | 3 | 0.002 | 1.798 |
| 12 | `revisit` | v08/motion/nominal_checks.py:77 | 3 | 1.733 | 1.753 |
| 13 | `width_probe` | v08/motion/intents/monitoring.py:1473 | 1 | 0.000 | 1.424 |
| 14 | `_band_probe` | v08/motion/intents/monitoring.py:802 | 1 | 0.000 | 1.424 |
| 15 | `build_band_query` | v08/motion/monitoring_band.py:796 | 1 | 0.000 | 1.424 |
| 16 | `chord_sdf_range` | v08/scene/exact.py:158 | 15 | 0.131 | 1.125 |
| 17 | `band_geometry` | v08/motion/intents/monitoring.py:572 | 1 | 0.000 | 1.039 |
| 18 | `__init__` | v08/motion/monitoring_band.py:468 | 1 | 0.001 | 1.039 |
| 19 | `radial_margins` | v08/motion/monitoring_band.py:197 | 1 | 0.021 | 0.997 |
| 20 | `<built-in method builtins.min>` | ~:0 | 8017873 | 0.917 | 0.917 |
| 21 | `_poly_sdf` | v08/scene/exact.py:90 | 207 | 0.425 | 0.698 |
| 22 | `_seg_point_dist` | v08/scene/exact.py:148 | 48 | 0.478 | 0.582 |
| 23 | `<built-in method math.sqrt>` | ~:0 | 8012371 | 0.527 | 0.527 |
| 24 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 5001 | 0.414 | 0.414 |
| 25 | `shape_lp` | v08/motion/monitoring_band.py:549 | 2 | 0.001 | 0.401 |

### skeleton — 按 tottime（互斥墙钟 9.46 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `speed_profile` | v08/sim/guidance.py:88 | 85 | 3.331 | 4.793 |
| 2 | `revisit` | v08/motion/nominal_checks.py:77 | 3 | 1.733 | 1.753 |
| 3 | `<built-in method builtins.min>` | ~:0 | 8017873 | 0.917 | 0.917 |
| 4 | `<built-in method math.sqrt>` | ~:0 | 8012371 | 0.527 | 0.527 |
| 5 | `_seg_point_dist` | v08/scene/exact.py:148 | 48 | 0.478 | 0.582 |
| 6 | `_poly_sdf` | v08/scene/exact.py:90 | 207 | 0.425 | 0.698 |
| 7 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 5001 | 0.414 | 0.414 |
| 8 | `chord_sdf_range` | v08/scene/exact.py:158 | 15 | 0.131 | 1.125 |
| 9 | `<method 'decompress' of 'zlib.Decompress' objects>` | ~:0 | 256 | 0.122 | 0.122 |
| 10 | `<genexpr>` | v08/motion/intents/monitoring.py:319 | 156455 | 0.094 | 0.094 |
| 11 | `_transform` | v08/scene/field.py:34 | 41 | 0.071 | 0.071 |
| 12 | `<built-in method nt.stat>` | ~:0 | 1510 | 0.067 | 0.067 |
| 13 | `_release_delays_ref` | v08/motion/intents/monitoring.py:470 | 1 | 0.064 | 0.273 |
| 14 | `_densify_rows` | v08/motion/monitoring_turn.py:151 | 3 | 0.056 | 0.084 |
| 15 | `<built-in method numpy._core._multiarray_umath.c_einsum>` | ~:0 | 39 | 0.054 | 0.054 |
| 16 | `<built-in method _wmi.exec_query>` | ~:0 | 2 | 0.051 | 0.051 |
| 17 | `__init__` | v08/scene/field.py:150 | 6 | 0.043 | 0.155 |
| 18 | `<genexpr>` | v08/motion/intents/monitoring.py:387 | 46950 | 0.041 | 0.041 |
| 19 | `corner_values` | v08/scene/field.py:124 | 41 | 0.039 | 0.112 |
| 20 | `_linprog_highs` | scipy/optimize/_linprog_highs.py:109 | 2 | 0.038 | 0.039 |
| 21 | `value` | v08/scene/field.py:158 | 816 | 0.034 | 0.062 |
| 22 | `_clip` | numpy/_core/_methods.py:96 | 3616 | 0.031 | 0.033 |
| 23 | `<built-in method builtins.compile>` | ~:0 | 48 | 0.028 | 0.028 |
| 24 | `<built-in method _imp.create_dynamic>` | ~:0 | 61 | 0.025 | 0.025 |
| 25 | `<method 'append' of 'list' objects>` | ~:0 | 302090 | 0.022 | 0.022 |

### optimize — 按 cumulative（互斥墙钟 17.13 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `capture` | tools/v08/profile_monitoring_v15.py:391 | 1 | 0.000 | 17.130 |
| 2 | `optimize_segment` | v08/motion/optimize.py:926 | 1 | 0.009 | 17.130 |
| 3 | `solve_joint` | v08/motion/optimize.py:837 | 1 | 0.010 | 14.041 |
| 4 | `minimize` | scipy/optimize/_minimize.py:53 | 1 | 0.000 | 13.449 |
| 5 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 1 | 0.144 | 13.449 |
| 6 | `_update_fun` | scipy/optimize/_differentiable_functions.py:292 | 361 | 0.001 | 13.273 |
| 7 | `wrapped` | scipy/optimize/_differentiable_functions.py:15 | 360 | 0.016 | 13.272 |
| 8 | `fun_and_grad` | scipy/optimize/_differentiable_functions.py:340 | 360 | 0.001 | 13.262 |
| 9 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 720 | 0.703 | 13.260 |
| 10 | `__call__` | scipy/optimize/_optimize.py:77 | 360 | 0.001 | 13.253 |
| 11 | `value_grad` | v08/motion/optimize.py:773 | 361 | 0.631 | 12.581 |
| 12 | `_blocks` | v08/motion/optimize.py:636 | 363 | 1.750 | 8.595 |
| 13 | `eval` | v08/motion/optimize.py:299 | 6552 | 5.332 | 5.926 |
| 14 | `check_monitoring` | v08/motion/optimize_checks.py:363 | 1 | 0.002 | 2.197 |
| 15 | `__matmul__` | scipy/sparse/_base.py:665 | 13095 | 0.007 | 1.781 |
| 16 | `_matmul_dispatch` | scipy/sparse/_base.py:544 | 13098 | 0.014 | 1.740 |
| 17 | `screen_member` | v08/motion/nominal_checks.py:156 | 3 | 0.002 | 1.697 |
| 18 | `_matmul_multivector` | scipy/sparse/_compressed.py:496 | 10887 | 0.028 | 1.680 |
| 19 | `revisit` | v08/motion/nominal_checks.py:77 | 3 | 1.644 | 1.662 |
| 20 | `bp_t` | v08/motion/optimize.py:665 | 1034 | 1.191 | 1.195 |
| 21 | `references_from_skeleton` | v08/motion/skeleton.py:179 | 1 | 0.000 | 0.876 |
| 22 | `chord_sdf_range` | v08/scene/exact.py:158 | 18 | 0.069 | 0.802 |
| 23 | `<built-in method scipy.sparse._sparsetools.csr_matvecs>` | ~:0 | 5466 | 0.751 | 0.751 |
| 24 | `<built-in method scipy.sparse._sparsetools.csc_matvecs>` | ~:0 | 5421 | 0.735 | 0.735 |
| 25 | `semantic_lines` | v08/motion/skeleton.py:87 | 3 | 0.001 | 0.652 |

### optimize — 按 tottime（互斥墙钟 17.13 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `eval` | v08/motion/optimize.py:299 | 6552 | 5.332 | 5.926 |
| 2 | `_blocks` | v08/motion/optimize.py:636 | 363 | 1.750 | 8.595 |
| 3 | `revisit` | v08/motion/nominal_checks.py:77 | 3 | 1.644 | 1.662 |
| 4 | `bp_t` | v08/motion/optimize.py:665 | 1034 | 1.191 | 1.195 |
| 5 | `<built-in method scipy.sparse._sparsetools.csr_matvecs>` | ~:0 | 5466 | 0.751 | 0.751 |
| 6 | `<built-in method scipy.sparse._sparsetools.csc_matvecs>` | ~:0 | 5421 | 0.735 | 0.735 |
| 7 | `_compute_if_needed` | scipy/optimize/_optimize.py:70 | 720 | 0.703 | 13.260 |
| 8 | `value_grad` | v08/motion/optimize.py:773 | 361 | 0.631 | 12.581 |
| 9 | `solve_banded` | scipy/linalg/_basic.py:370 | 2187 | 0.486 | 0.613 |
| 10 | `<built-in method numpy.zeros>` | ~:0 | 22119 | 0.428 | 0.428 |
| 11 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 41076 | 0.391 | 0.391 |
| 12 | `_seg_point_dist` | v08/scene/exact.py:148 | 72 | 0.355 | 0.433 |
| 13 | `_clip` | numpy/_core/_methods.py:96 | 39645 | 0.331 | 0.352 |
| 14 | `speed_profile` | v08/sim/guidance.py:88 | 6 | 0.266 | 0.384 |
| 15 | `_poly_sdf` | v08/scene/exact.py:90 | 69 | 0.253 | 0.430 |
| 16 | `_alloc` | v08/motion/optimize.py:745 | 363 | 0.219 | 0.426 |
| 17 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 41573 | 0.182 | 0.182 |
| 18 | `eigvals` | numpy/linalg/_linalg.py:1181 | 60 | 0.156 | 0.157 |
| 19 | `_minimize_lbfgsb` | scipy/optimize/_lbfgsb_py.py:250 | 1 | 0.144 | 13.449 |
| 20 | `<built-in method builtins.min>` | ~:0 | 625959 | 0.073 | 0.073 |
| 21 | `chord_sdf_range` | v08/scene/exact.py:158 | 18 | 0.069 | 0.802 |
| 22 | `evaluate` | v08/motion/optimize.py:83 | 45 | 0.048 | 0.072 |
| 23 | `<built-in method math.sqrt>` | ~:0 | 625808 | 0.042 | 0.042 |
| 24 | `<built-in method numpy.asarray>` | ~:0 | 21185 | 0.040 | 0.040 |
| 25 | `asarray_chkfinite` | numpy/lib/_function_base_impl.py:614 | 4881 | 0.036 | 0.045 |

### simulation — 按 cumulative（互斥墙钟 36.65 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `run_tracking_group` | v08/sim/tracking_batch.py:48 | 1 | 3.554 | 36.616 |
| 2 | `step` | v08/sim/kernel.py:27 | 192127 | 0.466 | 25.098 |
| 3 | `step` | swarm_sim/fast_dynamics/plants.py:43 | 192127 | 1.257 | 15.943 |
| 4 | `_pva` | v08/sim/tracking.py:74 | 569987 | 0.638 | 7.123 |
| 5 | `command` | swarm_sim/fast_dynamics/controllers.py:18 | 192127 | 1.444 | 6.734 |
| 6 | `project_acceleration` | swarm_sim/fast_dynamics/plants.py:9 | 576381 | 2.859 | 6.636 |
| 7 | `pva` | v08/motion/optimize.py:108 | 569991 | 4.532 | 6.030 |
| 8 | `dense_state` | swarm_sim/fast_dynamics/plants.py:18 | 230553 | 1.816 | 5.997 |
| 9 | `_array3` | swarm_sim/fast_dynamics/contracts.py:43 | 1306469 | 1.800 | 4.721 |
| 10 | `allclose` | numpy/_core/numeric.py:2226 | 192127 | 0.214 | 4.138 |
| 11 | `norm` | numpy/linalg/_linalg.py:2598 | 960635 | 2.342 | 3.616 |
| 12 | `isclose` | numpy/_core/numeric.py:2320 | 192127 | 1.754 | 3.586 |
| 13 | `all` | numpy/_core/fromnumeric.py:2586 | 1882850 | 0.718 | 3.341 |
| 14 | `__post_init__` | swarm_sim/fast_dynamics/contracts.py:59 | 230554 | 0.360 | 2.782 |
| 15 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 1882850 | 1.298 | 2.623 |
| 16 | `clip` | numpy/_core/fromnumeric.py:2245 | 768532 | 0.440 | 1.776 |
| 17 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 2846501 | 1.532 | 1.532 |
| 18 | `_wrapfunc` | numpy/_core/fromnumeric.py:48 | 768535 | 0.259 | 1.336 |
| 19 | `<built-in method builtins.isinstance>` | ~:0 | 3842756 | 0.549 | 1.241 |
| 20 | `at` | swarm_sim/fast_dynamics/engine.py:41 | 38426 | 0.029 | 1.112 |
| 21 | `_positive` | swarm_sim/fast_dynamics/contracts.py:30 | 691682 | 0.306 | 1.057 |
| 22 | `<method 'clip' of 'numpy.ndarray' objects>` | ~:0 | 768532 | 0.204 | 0.986 |
| 23 | `__post_init__` | swarm_sim/fast_dynamics/contracts.py:84 | 192127 | 0.082 | 0.810 |
| 24 | `_clip` | numpy/_core/_methods.py:96 | 768532 | 0.782 | 0.782 |
| 25 | `_integer` | swarm_sim/fast_dynamics/contracts.py:37 | 268981 | 0.126 | 0.776 |

### simulation — 按 tottime（互斥墙钟 36.65 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `pva` | v08/motion/optimize.py:108 | 569991 | 4.532 | 6.030 |
| 2 | `run_tracking_group` | v08/sim/tracking_batch.py:48 | 1 | 3.554 | 36.616 |
| 3 | `project_acceleration` | swarm_sim/fast_dynamics/plants.py:9 | 576381 | 2.859 | 6.636 |
| 4 | `norm` | numpy/linalg/_linalg.py:2598 | 960635 | 2.342 | 3.616 |
| 5 | `dense_state` | swarm_sim/fast_dynamics/plants.py:18 | 230553 | 1.816 | 5.997 |
| 6 | `_array3` | swarm_sim/fast_dynamics/contracts.py:43 | 1306469 | 1.800 | 4.721 |
| 7 | `isclose` | numpy/_core/numeric.py:2320 | 192127 | 1.754 | 3.586 |
| 8 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 2846501 | 1.532 | 1.532 |
| 9 | `command` | swarm_sim/fast_dynamics/controllers.py:18 | 192127 | 1.444 | 6.734 |
| 10 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 1882850 | 1.298 | 2.623 |
| 11 | `step` | swarm_sim/fast_dynamics/plants.py:43 | 192127 | 1.257 | 15.943 |
| 12 | `_clip` | numpy/_core/_methods.py:96 | 768532 | 0.782 | 0.782 |
| 13 | `all` | numpy/_core/fromnumeric.py:2586 | 1882850 | 0.718 | 3.341 |
| 14 | `<built-in method numpy.array>` | ~:0 | 1882863 | 0.679 | 0.679 |
| 15 | `_pva` | v08/sim/tracking.py:74 | 569987 | 0.638 | 7.123 |
| 16 | `<built-in method builtins.isinstance>` | ~:0 | 3842756 | 0.549 | 1.241 |
| 17 | `step` | v08/sim/kernel.py:27 | 192127 | 0.466 | 25.098 |
| 18 | `<built-in method numpy.asarray>` | ~:0 | 3437789 | 0.455 | 0.455 |
| 19 | `clip` | numpy/_core/fromnumeric.py:2245 | 768532 | 0.440 | 1.776 |
| 20 | `ndim` | numpy/_core/fromnumeric.py:3520 | 569991 | 0.388 | 0.502 |
| 21 | `<method 'setflags' of 'numpy.ndarray' objects>` | ~:0 | 1498596 | 0.375 | 0.375 |
| 22 | `h` | v08/motion/optimize.py:75 | 1139989 | 0.366 | 0.366 |
| 23 | `__post_init__` | swarm_sim/fast_dynamics/contracts.py:59 | 230554 | 0.360 | 2.782 |
| 24 | `<method 'reshape' of 'numpy.ndarray' objects>` | ~:0 | 1710006 | 0.351 | 0.351 |
| 25 | `_positive` | swarm_sim/fast_dynamics/contracts.py:30 | 691682 | 0.306 | 1.057 |

### verify — 按 cumulative（互斥墙钟 1.81 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `verify_segments` | v08/criteria/segment.py:78 | 1 | 0.000 | 1.767 |
| 2 | `measure_member_window` | v08/criteria/window.py:89 | 3 | 0.002 | 1.766 |
| 3 | `revisit` | task_v07/detectors.py:67 | 3 | 1.673 | 1.691 |
| 4 | `geometry_facts` | task_v07/geometry.py:15 | 30 | 0.054 | 0.093 |
| 5 | `check_validity` | v08/criteria/validity.py:72 | 1 | 0.005 | 0.041 |
| 6 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 381 | 0.039 | 0.039 |
| 7 | `norm` | numpy/linalg/_linalg.py:2598 | 633 | 0.007 | 0.025 |
| 8 | `sum` | numpy/_core/fromnumeric.py:2342 | 30 | 0.000 | 0.010 |
| 9 | `_wrapreduction` | numpy/_core/fromnumeric.py:66 | 30 | 0.000 | 0.010 |
| 10 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 27074 | 0.008 | 0.008 |
| 11 | `<method 'min' of 'numpy.ndarray' objects>` | ~:0 | 15 | 0.000 | 0.007 |
| 12 | `_amin` | numpy/_core/_methods.py:43 | 15 | 0.000 | 0.007 |
| 13 | `_wrapreduction_any_all` | numpy/_core/fromnumeric.py:86 | 45 | 0.000 | 0.005 |
| 14 | `all` | numpy/_core/fromnumeric.py:2586 | 24 | 0.000 | 0.005 |
| 15 | `dwell` | task_v07/detectors.py:32 | 6 | 0.003 | 0.005 |
| 16 | `_interp_min` | v08/criteria/validity.py:63 | 3 | 0.002 | 0.004 |
| 17 | `azimuth_coverage` | task_v07/detectors.py:24 | 6 | 0.002 | 0.003 |
| 18 | `<method 'append' of 'list' objects>` | ~:0 | 27258 | 0.003 | 0.003 |
| 19 | `_wrapfunc` | numpy/_core/fromnumeric.py:48 | 75 | 0.000 | 0.002 |
| 20 | `intersect1d` | numpy/lib/_arraysetops_impl.py:666 | 3 | 0.001 | 0.002 |
| 21 | `approach_heading_deg` | task_v07/labels.py:117 | 3 | 0.001 | 0.001 |
| 22 | `unwrap` | numpy/lib/_function_base_impl.py:1751 | 3 | 0.001 | 0.001 |
| 23 | `clip` | numpy/_core/fromnumeric.py:2245 | 18 | 0.000 | 0.001 |
| 24 | `<method 'clip' of 'numpy.ndarray' objects>` | ~:0 | 18 | 0.000 | 0.001 |
| 25 | `_clip` | numpy/_core/_methods.py:96 | 18 | 0.001 | 0.001 |

### verify — 按 tottime（互斥墙钟 1.81 s）

| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |
|---|---|---|---|---|---|
| 1 | `revisit` | task_v07/detectors.py:67 | 3 | 1.673 | 1.691 |
| 2 | `geometry_facts` | task_v07/geometry.py:15 | 30 | 0.054 | 0.093 |
| 3 | `<method 'reduce' of 'numpy.ufunc' objects>` | ~:0 | 381 | 0.039 | 0.039 |
| 4 | `<method 'astype' of 'numpy.ndarray' objects>` | ~:0 | 27074 | 0.008 | 0.008 |
| 5 | `norm` | numpy/linalg/_linalg.py:2598 | 633 | 0.007 | 0.025 |
| 6 | `check_validity` | v08/criteria/validity.py:72 | 1 | 0.005 | 0.041 |
| 7 | `dwell` | task_v07/detectors.py:32 | 6 | 0.003 | 0.005 |
| 8 | `<method 'append' of 'list' objects>` | ~:0 | 27258 | 0.003 | 0.003 |
| 9 | `measure_member_window` | v08/criteria/window.py:89 | 3 | 0.002 | 1.766 |
| 10 | `_interp_min` | v08/criteria/validity.py:63 | 3 | 0.002 | 0.004 |
| 11 | `azimuth_coverage` | task_v07/detectors.py:24 | 6 | 0.002 | 0.003 |
| 12 | `intersect1d` | numpy/lib/_arraysetops_impl.py:666 | 3 | 0.001 | 0.002 |
| 13 | `_clip` | numpy/_core/_methods.py:96 | 18 | 0.001 | 0.001 |
| 14 | `unwrap` | numpy/lib/_function_base_impl.py:1751 | 3 | 0.001 | 0.001 |
| 15 | `visible_track` | v08/criteria/validity.py:43 | 3 | 0.001 | 0.001 |
| 16 | `<method 'sort' of 'numpy.ndarray' objects>` | ~:0 | 6 | 0.001 | 0.001 |
| 17 | `<method 'nonzero' of 'numpy.ndarray' objects>` | ~:0 | 45 | 0.001 | 0.001 |
| 18 | `approach_heading_deg` | task_v07/labels.py:117 | 3 | 0.001 | 0.001 |
| 19 | `stitch` | v08/sim/stitch.py:50 | 1 | 0.001 | 0.001 |
| 20 | `diff` | numpy/lib/_function_base_impl.py:1413 | 27 | 0.000 | 0.000 |
| 21 | `<built-in method _io.open>` | ~:0 | 3 | 0.000 | 0.000 |
| 22 | `<built-in method numpy.array>` | ~:0 | 176 | 0.000 | 0.000 |
| 23 | `<method 'cumsum' of 'numpy.ndarray' objects>` | ~:0 | 3 | 0.000 | 0.000 |
| 24 | `<method 'dot' of 'numpy.ndarray' objects>` | ~:0 | 450 | 0.000 | 0.000 |
| 25 | `_check` | v08/criteria/validity.py:51 | 3 | 0.000 | 0.000 |

