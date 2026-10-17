# R1 历史回归故障核实

保留原 R1 FAIL；只使用已锁定日志及 Git 对象逐项复核。四项故障机制相同。

注意：后两项含尚未执行到的间距/驻留审计断言，不能称其完全不涉及安全合同。最终 G-1/G-5 优先，允许登记精确历史故障；这不证明这些断言已通过，也不豁免物理、航点或独立审计硬门禁。

## test_v07_s2_revision_continuous.ContinuousRevisionTests.test_five_calibration_round_limit_and_zero_flights_for_empty_pool

BASELINE_REPRODUCED / ERROR
unittest.mock fails before running calibration/spacing assertions: old calibrate_episode patch target is absent in both revisions. Safety-related downstream assertions are NOT proven by this failed test.

固定 FE 基线：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-int\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 193, in test_five_calibration_round_limit_and_zero_flights_for_empty_pool
    with TemporaryDirectory() as directory, patch('task_v07.expansion.candidate_search.episode_candidate_pool',return_value=(pool,dict(search))), \
  File "C:\Users\shy\anaconda3\envs\llm\Lib\unittest\mock.py", line 1458, in __enter__
    original, local = self.get_original()
                      ^^^^^^^^^^^^^^^^^^^
  File "C:\Users\shy\anaconda3\envs\llm\Lib\unittest\mock.py", line 1431, in get_original
    raise AttributeError(
AttributeError: <module 'scripts.run_v07_s2_episode_batch' from 'F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\Simulation-fe-int\\Multi-UAV SimpleGC\\scripts\\run_v07_s2_episode_batch.py'> does not have the attribute 'calibrate_episode'
```
当前候选原 R1：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-m3r3\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 193, in test_five_calibration_round_limit_and_zero_flights_for_empty_pool
    with TemporaryDirectory() as directory, patch('task_v07.expansion.candidate_search.episode_candidate_pool',return_value=(pool,dict(search))), \
  File "C:\Users\shy\anaconda3\envs\llm\Lib\unittest\mock.py", line 1458, in __enter__
    original, local = self.get_original()
                      ^^^^^^^^^^^^^^^^^^^
  File "C:\Users\shy\anaconda3\envs\llm\Lib\unittest\mock.py", line 1431, in get_original
    raise AttributeError(
AttributeError: <module 'scripts.run_v07_s2_episode_batch' from 'F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\Simulation-fe-m3r3\\Multi-UAV SimpleGC\\scripts\\run_v07_s2_episode_batch.py'> does not have the attribute 'calibrate_episode'
```

## test_v07_s2_revision_continuous.ContinuousRevisionTests.test_variable_observation_dwell_preserves_eighty_percent_criterion

BASELINE_REPRODUCED / ERROR
KeyError reading obsolete minimum_dwell condition in the current criteria-r1 label schema. This test also contains a P0 audit assertion, which is unreached; do NOT claim its contract verified.

固定 FE 基线：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-int\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 132, in test_variable_observation_dwell_preserves_eighty_percent_criterion
    self.assertFalse(labels['agents']['a']['result']['conditions']['minimum_dwell'])
                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^
KeyError: 'minimum_dwell'
```
当前候选原 R1：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-m3r3\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 132, in test_variable_observation_dwell_preserves_eighty_percent_criterion
    self.assertFalse(labels['agents']['a']['result']['conditions']['minimum_dwell'])
                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^
KeyError: 'minimum_dwell'
```

## test_v07_s2_revision_continuous.ContinuousRevisionTests.test_115_percent_filter_then_seeded_order

BASELINE_REPRODUCED / FAIL
Old literal 1.15 conflicts with the unchanged FE generator configuration 1.30; candidate selection preference, not physics/safety.

固定 FE 基线：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-int\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 79, in test_115_percent_filter_then_seeded_order
    self.assertEqual({c['cost'] for c in selected},{100,114.9,115})
AssertionError: Items in the first set but not the second:
115.1
```
当前候选原 R1：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-m3r3\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 79, in test_115_percent_filter_then_seeded_order
    self.assertEqual({c['cost'] for c in selected},{100,114.9,115})
AssertionError: Items in the first set but not the second:
115.1
```

## test_v07_s2_revision_continuous.ContinuousRevisionTests.test_each_group_has_its_own_115_percent_bound

BASELINE_REPRODUCED / FAIL
Same stale 1.15 preference; current per-group ratio comes from unchanged generator configuration 1.30.

固定 FE 基线：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-int\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 103, in test_each_group_has_its_own_115_percent_bound
    self.assertEqual([c['index'] for c in selected],[2])
AssertionError: Lists differ: [3, 2] != [2]

First differing element 0:
3
2

First list contains 1 additional elements.
First extra element 1:
2

- [3, 2]
+ [2]
```
当前候选原 R1：
```
Traceback (most recent call last):
  File "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-m3r3\Multi-UAV SimpleGC\tests\test_v07_s2_revision_continuous.py", line 103, in test_each_group_has_its_own_115_percent_bound
    self.assertEqual([c['index'] for c in selected],[2])
AssertionError: Lists differ: [3, 2] != [2]

First differing element 0:
3
2

First list contains 1 additional elements.
First extra element 1:
2

- [3, 2]
+ [2]
```
