import copy
import unittest
import numpy as np
from scripts.revalidate_m3_r3_r1 import parse_log,regression,array_diff,normalized,OLD

class R1GateTests(unittest.TestCase):
    def setUp(self):
        self.base=parse_log((OLD/'R1_fixed_base_attribution.txt').read_text())
        self.current=parse_log((OLD/'unit_tests.txt').read_text())
        self.white=list(self.base['failures'])
    def test_exact_known_failures_are_not_passes(self):
        r=regression(self.current,self.base,self.white)
        self.assertEqual((r['status'],r['executed'],r['passed'],r['baseline_known_failure']),('PASS',209,205,4))
    def test_changed_failure_location_is_new_regression(self):
        key=self.white[0]
        self.current['failures'][key]['traceback']+='\nnew frame'
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_changed_exception_is_new_regression(self):
        self.current['failures'][self.white[0]]['kind']='FAIL'
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_unexpected_skip_blocks(self):
        key=next(k for k,v in self.current['outcomes'].items() if v=='ok')
        self.current['outcomes'][key]="skipped 'unexpected'"
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_missing_test_blocks(self):
        del self.current['outcomes'][next(iter(self.base['outcomes']))]
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_signed_zero_difference_is_not_hidden(self):
        diff=array_diff(np.array([0.]),np.array([-0.]))
        self.assertEqual(diff['index'],[0])
        self.assertNotEqual(diff['actual_bytes'],diff['historical_bytes'])
    def test_incomplete_log_rejected(self):
        with self.assertRaises(ValueError):parse_log('test_one (a.b.test_one) ... ok\nRan 2 tests in 0.1s\nOK\n')

    def test_end_to_end_startup_dry_run_validates_locked_inputs(self):
        import json,subprocess,sys
        from scripts.revalidate_m3_r3_r1 import PROJECT
        run=subprocess.run([sys.executable,'-B',str(PROJECT/'scripts/revalidate_m3_r3_r1.py'),'--dry-run'],
                           cwd=PROJECT,capture_output=True,text=True,timeout=120)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        result=json.loads(run.stdout)
        self.assertEqual(result['status'],'DRY_RUN_PASS')
        self.assertEqual(result['input_files'],8608)
        self.assertEqual({p.replace('\\','/').rsplit('/',1)[-1] for p in result['mutable_paths']},{'route_tracker.py','contracts.py'})

    def test_fixed_baseline_archive_from_subproject_directory(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.revalidate_m3_r3_r1 import export_baseline,digest,CONFIG_SHA,PROJECT
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            base=export_baseline(folder/'baseline.zip',folder/'baseline_checkout')
            self.assertEqual(digest(base/'configs/fast_dynamics/m3_r2_20261013_v1.json'),CONFIG_SHA)
            self.assertEqual(digest(base/'tests/test_v07_s2_revision_continuous.py'),digest(PROJECT/'tests/test_v07_s2_revision_continuous.py'))
            self.assertTrue((base/'swarm_sim/fast_dynamics/route_tracker.py').is_file())

    def test_subtest_errors_remain_errors_and_count_parent_once(self):
        from scripts.revalidate_m3_r3_r1 import DATA
        log=DATA/'fast_dynamics/m3/m3_r3_r1_revalidate03/baseline_tests.txt'
        result=parse_log(log.read_text())
        key='test_fast_dynamics_artifacts_m2.M2PublicChainTests.test_rehashed_wrong_planned_phases_is_rejected_even_on_reuse_hit'
        self.assertEqual(result['count'],200)
        self.assertEqual(result['outcomes'][key],'ERROR')
        self.assertIn('(reuse=False)',result['failures'][key]['traceback'])
        self.assertIn('(reuse=True)',result['failures'][key]['traceback'])
        self.assertIn('cannot find source Git baseline',result['failures'][key]['traceback'])

    def test_isolated_environment_retains_git_workflow_and_fixture(self):
        import json,os,subprocess,sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.revalidate_m3_r3_r1 import export_baseline,BASE
        with TemporaryDirectory() as directory:
            folder=Path(directory);base=export_baseline(folder/'baseline.zip',folder/'baseline_checkout')
            self.assertTrue((base.parent/'.github/workflows/unit-tests.yml').is_file())
            env=dict(os.environ,PYTHONPATH=str(base)+os.pathsep+str(base/'tests'),PYTHONSAFEPATH='1')
            identity=subprocess.run([sys.executable,'-B','-c','from swarm_sim.fast_dynamics.artifacts import _git_revision; print(_git_revision())'],cwd=base,env=env,capture_output=True,text=True)
            self.assertEqual(identity.returncode,0,identity.stderr)
            self.assertEqual(identity.stdout.strip(),BASE)
            modules=['test_fast_dynamics_artifacts.FastDynamicsArtifactsTests.test_complete_public_chain_and_source_identity',
                     'test_fast_dynamics_artifacts_m2.M2PublicChainTests.test_actual_m2_public_export_load_audit_describe',
                     'test_v07_m2_timing_rehearsal.M2Checks.test_A8_partial_finish_uses_conservative_budget']
            run=subprocess.run([sys.executable,'-B','-m','unittest','-v',*modules],cwd=base,env=env,capture_output=True,text=True,timeout=120)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
