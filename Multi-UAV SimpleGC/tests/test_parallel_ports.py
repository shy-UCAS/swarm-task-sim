"""Port block bounds and both prepare CLI contracts; no simulator processes."""
import io
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_parallel_batch as production_cli
from scripts import prepare_parallel_subset as subset_cli
from swarm_sim import parallel_batch as batch
from swarm_sim.generation import save_json


class PortConfigurationTests(unittest.TestCase):
    def test_default_and_custom_disjoint_blocks_and_upper_boundary(self):
        self.assertEqual(batch.port_blocks(4, 4), batch.port_blocks(4, 4, 19100))
        self.assertEqual(batch.port_blocks(4, 4, 20100), [
            dict(shard_id=i, base_port=20100+100*i, end_port=20199+100*i) for i in range(4)])
        self.assertEqual(batch.port_blocks(1, 10, 64901)[0]["end_port"], 65000)
        self.assertEqual(batch.shard_base_port({}, 3), 19400)

    def test_invalid_port_types_and_block_overflow_rejected(self):
        for value in (True, 20100.0, "20100", 0, 1023, 64902, 65535):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "base_port"):
                batch.port_blocks(1, 1, value)
        with self.assertRaisesRegex(ValueError, "base_port"):
            batch.port_blocks(4, 4, 64701)

    def test_production_cli_default_and_explicit_base_port(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, SIM_DATA_ROOT=temp):
            args = ["prepare", "--batch-id", "fixture", "--profile", "profile.json", "--max-attempts", "2",
                    "--storage-bytes-per-attempt", "1", "--export-reserve-bytes", "1"]
            for extra, expected in (([], 19100), (["--base-port", "20100"], 20100)):
                with patch.object(production_cli, "prepare", return_value=dict(tasks=[{}], shards=2)) as prep, \
                        redirect_stdout(io.StringIO()):
                    self.assertEqual(production_cli.main(args+extra), 0)
                    self.assertEqual(prep.call_args.kwargs["base_port"], expected)

    def test_subset_cli_default_and_explicit_base_port(self):
        with tempfile.TemporaryDirectory() as temp:
            ids = Path(temp) / "ids.json"
            save_json(ids, ["mission"])
            args = ["--batch-id", "fixture", "--source-bundle", temp, "--mission-ids", str(ids),
                    "--max-attempts", "2", "--storage-bytes-per-attempt", "1", "--export-reserve-bytes", "1"]
            for extra, expected in (([], 19100), (["--base-port", "20100"], 20100)):
                with patch.object(subset_cli, "prepare_subset", return_value=dict(root=temp, tasks=[{}], shards=4)) as prep, \
                        redirect_stdout(io.StringIO()):
                    subset_cli.main(args+extra)
                    self.assertEqual(prep.call_args.kwargs["base_port"], expected)


if __name__ == "__main__":
    unittest.main()
