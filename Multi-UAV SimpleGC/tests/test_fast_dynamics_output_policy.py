"""External output policy: positive/negative path protection for the fast dynamics entry points.

Covers the policy module, the three CLI entry points, root ownership, run-id fragment
rejection and junction escapes. External isolated directories are used throughout; system
TEMP settings are never modified, and every attempt-like output is a fresh directory.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts import benchmark_fast_dynamics, run_fast_dynamics, verify_fast_dynamics_m01  # noqa: E402
from swarm_sim.fast_dynamics import output_policy as policy  # noqa: E402

FIXTURE = PROJECT / "tests" / "fixtures" / "fast_dynamics" / "rapid_passage_0000_v00.json"
DEFAULT_ROOT = policy.default_output_root()


def make_junction(link: Path, target: Path) -> bool:
    """Create a real directory junction (does not require administrator rights)."""
    created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                             capture_output=True, text=True)
    return created.returncode == 0 and link.exists()


def directories_under(root: Path):
    """Top-level attempt directories under a root (a full attempt has nested folders)."""
    if not root.exists():
        return set()
    return {path for path in root.iterdir() if path.is_dir()}


class DefaultRootTests(unittest.TestCase):
    """R1: the default root must be the repository's *sibling* SwarmData/fast_dynamics."""

    def test_default_root_is_the_repository_parents_swarmdata_and_outside_the_repository(self):
        repository = policy.repository_root()
        expected = repository.parent / "SwarmData" / "fast_dynamics"
        resolved = policy.resolve_output_root(None, env={})
        self.assertEqual(resolved["root"], Path(os.path.realpath(expected)))
        self.assertEqual(resolved["source"], "default sibling SwarmData/fast_dynamics")
        self.assertFalse(resolved["inside_repository"])
        self.assertFalse(policy.is_inside_repository(resolved["root"]))
        self.assertEqual(resolved["root"].parent, repository.parent / "SwarmData")
        self.assertNotEqual(resolved["root"].parent, repository)
        self.assertFalse(str(resolved["root"]).startswith(str(repository) + os.sep))

    def test_default_root_does_not_depend_on_the_repository_name(self):
        # Location rule, not a hardcoded checkout name: sibling of the Git root under its parent.
        root = policy.default_output_root()
        self.assertEqual(root.name, "fast_dynamics")
        self.assertEqual(root.parent.name, "SwarmData")
        self.assertEqual(root.parent.parent, policy.repository_root().parent)
        module_text = (PROJECT / "swarm_sim" / "fast_dynamics" / "output_policy.py").read_text(encoding="utf-8")
        for needle in ("F:\\", "F:/", "C:\\", "C:/", "/home/", "/Users/"):
            self.assertNotIn(needle, module_text)

    def test_explicit_and_environment_roots_take_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            explicit = Path(temp) / "explicit_root"
            self.assertEqual(policy.resolve_output_root(explicit, env={})["source"], "argument --output-root")
            self.assertEqual(policy.resolve_output_root(explicit, env={})["root"], Path(os.path.realpath(explicit)))

            env_root = Path(temp) / "env_root"
            env = {policy.ENV_VAR: str(env_root)}
            resolved = policy.resolve_output_root(None, env=env)
            self.assertIn(policy.ENV_VAR, resolved["source"])
            self.assertEqual(resolved["root"], Path(os.path.realpath(env_root)))

    def test_unusable_roots_are_rejected(self):
        inside = PROJECT / "verification" / "policy_should_not_create_this_root"
        with self.assertRaises(policy.OutputPolicyError):
            policy.resolve_output_root(inside, env={})
        with self.assertRaises(policy.OutputPolicyError):
            policy.resolve_output_root(None, env={policy.ENV_VAR: str(inside)})
        with tempfile.TemporaryDirectory() as temp:
            as_file = Path(temp) / "not_a_directory"
            as_file.write_text("x", encoding="utf-8")
            with self.assertRaises(policy.OutputPolicyError):
                policy.resolve_output_root(as_file, env={})
        self.assertFalse(inside.exists())


class TargetOwnershipTests(unittest.TestCase):
    """R2: a target must live under the selected root, not merely outside the repository."""

    def test_target_under_the_selected_root_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            target = root / "attempt_01"
            self.assertEqual(policy.assert_new_attempt_path(target, root, kind="attempt"),
                             Path(os.path.realpath(target)))

    def test_target_outside_the_selected_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            outside = Path(temp) / "outside" / "attempt"
            with self.assertRaises(policy.OutputPolicyError):
                policy.assert_new_attempt_path(outside, root, kind="attempt")
            self.assertFalse(outside.exists())
            # A relative escape is rejected by the same resolved-path check.
            with self.assertRaises(policy.OutputPolicyError):
                policy.assert_new_attempt_path(root / ".." / "outside" / "attempt", root, kind="attempt")

    def test_target_under_the_environment_root_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            env_root = Path(temp) / "env_root"
            resolved = policy.resolve_output_root(None, env={policy.ENV_VAR: str(env_root)})
            target = Path(resolved["root"]) / "attempt_01"
            self.assertEqual(policy.assert_new_attempt_path(target, resolved["root"], kind="attempt"),
                             Path(os.path.realpath(target)))

    def test_existing_and_repository_targets_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            existing = root / "attempt_01"
            existing.mkdir(parents=True)
            with self.assertRaises(policy.OutputPolicyError):
                policy.assert_new_attempt_path(existing, root, kind="attempt")
        with self.assertRaises(policy.OutputPolicyError):
            policy.assert_new_attempt_path(PROJECT / "verification" / "policy_should_not_create_this", PROJECT, kind="attempt")
        self.assertFalse((PROJECT / "verification" / "policy_should_not_create_this").exists())


class RunIdFragmentTests(unittest.TestCase):
    """R2: attempt prefixes must not carry path fragments that escape the root."""

    def test_path_fragments_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            for prefix in ("x/../../../escaped", "..\\escape", "sub/attempt", "C:/absolute", "..", ".",
                           "/rooted", "trailing.", "CON", "  spaced  ", ""):
                with self.subTest(prefix=prefix):
                    with self.assertRaises(policy.OutputPolicyError):
                        policy.new_attempt_path(root, prefix)
            self.assertFalse((Path(temp) / "escaped").exists())
            self.assertFalse(Path(temp).parent.joinpath("escaped").exists())

    def test_valid_prefix_stays_under_the_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            target = policy.new_attempt_path(root, "fast_m1_rapid_passage")
            self.assertTrue(policy.is_within(target, root))
            self.assertTrue(target.name.endswith("_fast_m1_rapid_passage"))


class JunctionTests(unittest.TestCase):
    """R2: links must not smuggle outputs into the repository or out of the selected root."""

    def test_root_that_is_a_junction_into_the_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / "root_link"
            if not make_junction(link, PROJECT / "verification"):
                self.skipTest("junction creation unavailable")
            with self.assertRaises(policy.OutputPolicyError):
                policy.resolve_output_root(link, env={})
            with self.assertRaises(policy.OutputPolicyError):
                policy.assert_new_attempt_path(link / "policy_should_not_create_this", link, kind="attempt")
            self.assertFalse((PROJECT / "verification" / "policy_should_not_create_this").exists())

    def test_target_escaping_the_selected_root_through_a_junction_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp) / "outside"
            outside.mkdir()
            root = Path(temp) / "root"
            root.mkdir()
            link = root / "leak"
            if not make_junction(link, outside):
                self.skipTest("junction creation unavailable")
            with self.assertRaises(policy.OutputPolicyError):
                policy.assert_new_attempt_path(link / "attempt", root, kind="attempt")
            self.assertFalse((outside / "attempt").exists())

    def test_junction_target_into_the_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / "link_into_repo"
            if not make_junction(link, PROJECT / "verification"):
                self.skipTest("junction creation unavailable")
            with self.assertRaises(policy.OutputPolicyError):
                policy.assert_new_external_path(link / "policy_should_not_create_this", kind="attempt")
            self.assertFalse((PROJECT / "verification" / "policy_should_not_create_this").exists())


class RunFastDynamicsCliTests(unittest.TestCase):
    def test_invalid_ids_are_rejected_before_io_in_both_output_modes(self):
        invalid_ids = ("x/../../../escaped", "name.with.dot", "", "a" * 101,
                       "CON", "C:/absolute", "sub\\attempt", "two words", "非ASCII", ".", "..")
        for run_id in invalid_ids:
            for explicit in (False, True):
                with self.subTest(run_id=run_id, explicit=explicit), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp) / "selected_root"
                    argv = [str(FIXTURE), "--output-root", str(root), "--run-id", run_id]
                    if explicit:
                        argv.extend(["--output", str(root / "attempt")])
                    with patch.object(Path, "read_bytes", side_effect=AssertionError("task read too early")) as read, \
                            patch.object(run_fast_dynamics, "run_mission",
                                         side_effect=AssertionError("simulation started too early")) as simulate, \
                            contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as rejected:
                            run_fast_dynamics.main(argv)
                    self.assertEqual(rejected.exception.code, 2)
                    read.assert_not_called()
                    simulate.assert_not_called()
                    self.assertEqual(list(Path(temp).iterdir()), [])

    def test_valid_id_with_explicit_output_completes_the_public_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "explicit_attempt"
            run_id = "valid-ID_123"
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = run_fast_dynamics.main([str(FIXTURE), "--output-root", temp,
                                                    "--output", str(target), "--run-id", run_id])
            self.assertEqual(exit_code, 0)
            self.assertTrue((target / "completion.json").is_file())
            attempt = json.loads((target / "attempt.json").read_text(encoding="utf-8"))
            report = json.loads((target / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["run_id"], run_id)
            self.assertEqual(report["frames"], 294)
            self.assertIs(report["analysis"]["mission_success"], True)
            self.assertEqual(report["language"]["descriptions"], 4)

    def test_repository_target_is_rejected_before_any_artifact(self):
        target = PROJECT / "verification" / "policy_should_not_create_this"
        with self.assertRaises(SystemExit):
            run_fast_dynamics.main([str(FIXTURE), "--output", str(target)])
        self.assertFalse(target.exists())

    def test_output_outside_the_selected_root_is_rejected_with_zero_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "selected_root"
            outside = Path(temp) / "outside_selected_root" / "attempt"
            with patch.object(run_fast_dynamics, "run_mission", side_effect=ArithmeticError("SENTINEL")):
                with self.assertRaises(SystemExit):
                    run_fast_dynamics.main([str(FIXTURE), "--output-root", str(root),
                                            "--output", str(outside)])
            self.assertFalse(outside.exists())
            self.assertFalse(root.exists())

    def test_run_id_with_path_fragments_is_rejected_with_zero_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "selected_root"
            with self.assertRaises(SystemExit):
                run_fast_dynamics.main([str(FIXTURE), "--output-root", str(root),
                                        "--run-id", "x/../../../escaped"])
            self.assertFalse(root.exists())
            self.assertFalse((Path(temp) / "escaped").exists())

    def test_existing_attempt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            target = root / "attempt"
            target.mkdir(parents=True)
            with self.assertRaises(SystemExit):
                run_fast_dynamics.main([str(FIXTURE), "--output-root", str(root), "--output", str(target)])
            self.assertEqual(list(target.iterdir()), [])

    def test_selected_root_selects_a_fresh_external_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = run_fast_dynamics.main([str(FIXTURE), "--output-root", temp])
            self.assertEqual(exit_code, 0)
            attempts = [entry for entry in Path(temp).iterdir() if entry.is_dir()]
            self.assertEqual(len(attempts), 1)
            attempt = attempts[0]
            self.assertTrue((attempt / "completion.json").is_file())
            record = json.loads((attempt / "attempt.json").read_text(encoding="utf-8"))
            self.assertFalse(record["training_eligible"])
            self.assertEqual(Path(os.path.realpath(record["output_root"])), Path(os.path.realpath(temp)))
            report = json.loads((attempt / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["output"]["root_source"], "argument --output-root")
            self.assertEqual(report["loaded_agents"], ["uav_01", "uav_02"])
            self.assertTrue(policy.is_within(report["output"]["path"], temp))

    def test_default_run_completes_the_full_m1_chain_under_the_default_root(self):
        before = directories_under(DEFAULT_ROOT)
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = run_fast_dynamics.main([str(FIXTURE)])
        self.assertEqual(exit_code, 0)
        created = sorted(directories_under(DEFAULT_ROOT) - before)
        self.assertEqual(len(created), 1, created)
        attempt = created[0]
        self.assertTrue(policy.is_within(attempt, DEFAULT_ROOT))
        self.assertTrue((attempt / "completion.json").is_file())
        report = json.loads((attempt / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["output"]["root_source"], "default sibling SwarmData/fast_dynamics")
        self.assertEqual(Path(os.path.realpath(report["output"]["root"])), Path(os.path.realpath(DEFAULT_ROOT)))
        self.assertTrue(policy.is_within(report["output"]["path"], DEFAULT_ROOT))
        self.assertEqual(report["loaded_agents"], ["uav_01", "uav_02"])
        # The attempt is real external evidence and is kept, not deleted.


class BenchmarkCliTests(unittest.TestCase):
    def test_repository_output_is_rejected_before_measuring(self):
        target = PROJECT / "verification" / "policy_should_not_create_this.json"
        with self.assertRaises(SystemExit):
            benchmark_fast_dynamics.main(["--output", str(target)])
        self.assertFalse(target.exists())

    def test_output_outside_the_selected_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            outside = Path(temp) / "outside.json"
            with self.assertRaises(SystemExit):
                benchmark_fast_dynamics.main(["--duration", "0.1", "--repeats", "2", "--agents", "2",
                                              "--output-root", str(root), "--output", str(outside)])
            self.assertFalse(outside.exists())

    def test_output_root_writes_a_fresh_external_file(self):
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.redirect_stdout(io.StringIO()):
                benchmark_fast_dynamics.main(["--duration", "0.1", "--repeats", "2",
                                              "--agents", "2", "--output-root", temp])
            written = [entry for entry in Path(temp).iterdir() if entry.is_file()]
            self.assertEqual(len(written), 1)
            report = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], "fast_dynamics_kernel_benchmark_v1")
            self.assertEqual(Path(os.path.realpath(report["output_policy"]["root"])), Path(os.path.realpath(temp)))
            self.assertTrue(policy.is_within(report["output_policy"]["path"], temp))


class VerifyFastDynamicsCliTests(unittest.TestCase):
    def test_repository_output_is_rejected_before_running_anything(self):
        target = PROJECT / "verification" / "policy_should_not_create_this_verification"
        with patch.object(sys, "argv", ["verify_fast_dynamics_m01.py", "--output", str(target)]):
            with self.assertRaises(SystemExit):
                verify_fast_dynamics_m01.main()
        self.assertFalse(target.exists())

    def test_default_verify_is_not_self_rejected_by_the_policy(self):
        sentinel = {"reached": False}

        def stop():
            sentinel["reached"] = True
            raise RuntimeError("SENTINEL_STOP_VERIFY")

        before = directories_under(DEFAULT_ROOT)
        with patch.object(verify_fast_dynamics_m01, "source_snapshot", stop), \
                patch.object(sys, "argv", ["verify_fast_dynamics_m01.py"]):
            with self.assertRaises(RuntimeError):
                with contextlib.redirect_stdout(io.StringIO()):
                    verify_fast_dynamics_m01.main()
        self.assertTrue(sentinel["reached"], "the default verify path must reach the run body")
        created = sorted(directories_under(DEFAULT_ROOT) - before)
        self.assertEqual(len(created), 1, created)
        self.assertTrue(policy.is_within(created[0], DEFAULT_ROOT))
        self.assertEqual(list(created[0].iterdir()), [])
        shutil.rmtree(created[0])  # synthetic control: it aborted before writing evidence

    def test_custom_root_propagates_to_child_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            calls = []

            def fake_pipeline(argv=None):
                calls.append(list(argv))
                target = Path(argv[argv.index("--output") + 1])
                target.mkdir(parents=True, exist_ok=True)
                (target / "report.json").write_text(json.dumps({
                    "execution_status": "complete", "frames": 1, "end_us": 100000,
                    "analysis": {"mission_success": True, "episode_quality_eligible": True},
                    "language": {"descriptions": 4}}), encoding="utf-8")
                return 0

            def fake_run_mission(task, config=None):
                return SimpleNamespace(
                    time_us=np.array([0, 100000]), positions=np.zeros((2, 2, 3)),
                    velocities=np.zeros((2, 2, 3)), accelerations=np.zeros((2, 2, 3)),
                    events=[{"event": "phase_arrived", "phase": "p01_transit", "agent_id": "uav_01", "t_us": 100000}],
                    end_us=100000)

            with patch.object(verify_fast_dynamics_m01, "run_pipeline", fake_pipeline), \
                    patch.object(verify_fast_dynamics_m01, "run_mission", fake_run_mission), \
                    patch.object(verify_fast_dynamics_m01.unittest.defaultTestLoader, "loadTestsFromNames",
                                 lambda names: unittest.TestSuite()), \
                    patch.object(sys, "argv", ["verify_fast_dynamics_m01.py", "--output-root", str(root)]):
                with contextlib.redirect_stdout(io.StringIO()):
                    verify_fast_dynamics_m01.main()

            self.assertEqual(len(calls), 7)
            for argv in calls:
                self.assertIn("--output-root", argv)
                self.assertEqual(Path(os.path.realpath(argv[argv.index("--output-root") + 1])),
                                 Path(os.path.realpath(root)))
                self.assertTrue(policy.is_within(argv[argv.index("--output") + 1], root))
            verification_dirs = [entry for entry in Path(root).iterdir() if entry.is_dir()]
            self.assertEqual(len(verification_dirs), 1)
            report = json.loads((verification_dirs[0] / "verification.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(os.path.realpath(report["output"]["root"])), Path(os.path.realpath(root)))
            self.assertTrue(policy.is_within(report["output"]["path"], root))
            self.assertTrue(policy.is_within(verification_dirs[0], root))


if __name__ == "__main__":
    unittest.main()
