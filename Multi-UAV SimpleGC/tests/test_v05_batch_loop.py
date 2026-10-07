"""Run the real PowerShell loop only against an isolated fake CLI and ledger."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PWSH = Path("C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe")
CONDA = "C:/Users/shy/anaconda3/Scripts/conda.exe"

FAKE_CLI = r"""
$ErrorActionPreference = 'Stop'
if (($args -join '|') -ne 'run|-n|llm|--no-capture-output|python|scripts/run_v05_batch.py|next') {
    throw "Unexpected fake CLI arguments: $args"
}
if ((Get-Location).Path -ne $PSScriptRoot) { throw 'Loop did not enter its own project' }
Add-Content -LiteralPath "$PSScriptRoot/calls.txt" -Value 'next' -Encoding utf8
Write-Output 'fake controller stdout'
Write-Error 'fake controller stderr' -ErrorAction Continue
$path = "$PSScriptRoot/verification/v05_batch_20261002/control.json"
$state = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -AsHashtable
$mode = (Get-Content -LiteralPath "$PSScriptRoot/fake_mode.txt" -Raw).Trim()
if ($mode -eq 'command_error') { exit 7 }
if ($mode -eq 'no_progress') { exit 0 }
if ($mode -eq 'active_return') {
    $state.active_attempt = @{logical_index=$state.records.Count}
} else {
    $state.records += @{logical_index=$state.records.Count; attempt_index=0}
    $state.aggregate.logical_completed += $(if ($mode -eq 'wrong_progress') {2} else {1})
    if ($mode -eq 'gate_stop') { $state.stopped_reason = 'truth_separation gate stop' }
    if ($state.aggregate.logical_completed -eq 240) { $state.completed = $true }
}
$state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding utf8
if ($mode -eq 'gate_stop') { exit 1 }
exit 0
"""


@unittest.skipUnless(PWSH.is_file(), "PowerShell 7 runtime unavailable")
class BatchLoopTests(unittest.TestCase):
    def run_loop(self, *, count=37, mode="complete", stopped=None, active=None, completed=False,
                 missing_active=False, prior_log=""):
        with tempfile.TemporaryDirectory(prefix="v05_loop_isolated_") as name:
            temporary = Path(name)
            project, outside = temporary / "project", temporary / "outside"
            (project / "scripts").mkdir(parents=True)
            outside.mkdir()
            (project / ".conda-env").write_text("llm\n", encoding="utf-8")
            fake = project / "fake_conda.ps1"
            fake.write_text(FAKE_CLI, encoding="utf-8")
            source = (ROOT / "scripts/run_v05_batch_loop.ps1").read_text(encoding="utf-8-sig")
            self.assertEqual(source.count(CONDA), 1)
            # Only the test copy's executable is substituted. The production
            # loop has no test hook; no real controller or simulator is called.
            script = project / "scripts/run_v05_batch_loop.ps1"
            script.write_text(source.replace(CONDA, fake.as_posix()), encoding="utf-8")
            control = project / "verification/v05_batch_20261002/control.json"
            control.parent.mkdir(parents=True)
            state = dict(records=[dict(logical_index=i, attempt_index=0) for i in range(count)],
                         aggregate=dict(logical_completed=count), active_attempt=active,
                         stopped_reason=stopped, completed=completed)
            if missing_active:
                state.pop("active_attempt")
            control.write_text(json.dumps(state), encoding="utf-8")
            (project / "fake_mode.txt").write_text(mode, encoding="utf-8")
            log = project / "tmp_v05/batch_execution_20261002/batch_loop.log"
            log.parent.mkdir(parents=True)
            log.write_text(prior_log, encoding="utf-8")
            result = subprocess.run([str(PWSH), "-NoProfile", "-NonInteractive", "-File", str(script)],
                                    cwd=outside, capture_output=True, text=True, encoding="utf-8", timeout=30)
            calls = (project / "calls.txt").read_text(encoding="utf-8-sig").splitlines() if (project / "calls.txt").exists() else []
            return result, calls, json.loads(control.read_text(encoding="utf-8-sig")), log.read_text(encoding="utf-8-sig")

    def test_finishes_at_240_from_foreign_cwd_and_appends_log(self):
        result, calls, state, log = self.run_loop(count=238, prior_log="ORIGINAL EVIDENCE\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls, ["next", "next"])
        self.assertEqual(len(state["records"]), 240)
        self.assertTrue(state["completed"])
        self.assertTrue(log.startswith("ORIGINAL EVIDENCE\n"))
        self.assertIn("fake controller stdout", log)
        self.assertIn("fake controller stderr", log)
        self.assertIn("completed=240/240 attempts=240/264", log)

    def test_gate_stop_does_not_retry(self):
        result, calls, state, log = self.run_loop(mode="gate_stop")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(calls, ["next"])
        self.assertEqual(len(state["records"]), 38)
        self.assertIn("truth_separation gate stop", log)
        self.assertIn("completed=38/240 attempts=38/264", log)

    def test_already_stopped_does_not_invoke_cli(self):
        result, calls, _, log = self.run_loop(stopped="onboard_mission_parameters")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, [])
        self.assertIn("onboard_mission_parameters", log)

    def test_active_attempt_does_not_invoke_cli(self):
        result, calls, _, log = self.run_loop(active={})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        self.assertIn("Unresolved active_attempt", log)

    def test_missing_active_field_does_not_invoke_cli(self):
        result, calls, _, log = self.run_loop(missing_active=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        self.assertIn("missing active_attempt", log)

    def test_nonzero_command_stops_without_retry(self):
        result, calls, state, log = self.run_loop(mode="command_error")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, ["next"])
        self.assertEqual(len(state["records"]), 37)
        self.assertIn("exit=7", log)

    def test_no_progress_stops_without_retry(self):
        result, calls, _, log = self.run_loop(mode="no_progress")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, ["next"])
        self.assertIn("Unexpected attempt/completion count change", log)

    def test_wrong_progress_stops_without_retry(self):
        result, calls, _, log = self.run_loop(mode="wrong_progress")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, ["next"])
        self.assertIn("Unexpected attempt/completion count change", log)

    def test_active_return_stops_without_retry(self):
        result, calls, _, log = self.run_loop(mode="active_return")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, ["next"])
        self.assertIn("unresolved active_attempt", log)

    def test_already_complete_does_not_invoke_cli(self):
        result, calls, _, log = self.run_loop(count=240, completed=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertIn("All 240 complete", log)


if __name__ == "__main__":
    unittest.main()
