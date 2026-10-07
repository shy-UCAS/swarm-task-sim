"""Published runtime must retain the real WP-S evidence dependency; no SITL."""

import json
from pathlib import Path
import tempfile
import unittest

from swarm_sim.run_provenance import verify_preflight_files

ROOT = Path(__file__).resolve().parents[1]


def minimal_baseline(root):
    confirmation_path = Path('docs/v04_spike_go_confirmation.json')
    confirmation = json.loads((ROOT / confirmation_path).read_text(encoding='utf-8'))
    required = []
    for link in confirmation['original_unknown_reports']:
        metric = Path(link['path'])
        required.extend((metric, metric.parent / 'metadata.json', metric.parent / 'firmware_parameters.json'))
    paths = [confirmation_path, *(Path(link['path']) for link in confirmation['evidence']), *required]
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / rel).read_bytes())
    return required


class PublishedBaselineTests(unittest.TestCase):
    def preflight(self, root):
        return verify_preflight_files(ROOT / 'ArducopterSITL/arducopter.exe',
                                      ROOT / 'ArducopterSITL/copter.parm', root)

    def test_minimal_published_baseline_passes_without_full_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            required = minimal_baseline(root)
            self.assertEqual(len(required), 6)
            self.assertEqual(self.preflight(root)['status'], 'files_verified')
            self.assertEqual(len(list((root / 'runs').rglob('*.json'))), 6)

    def test_missing_any_required_baseline_file_rejects_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in minimal_baseline(root):
                path = root / rel
                before = path.read_bytes()
                with self.subTest(path=rel.as_posix()):
                    path.unlink()
                    try:
                        with self.assertRaises(FileNotFoundError):
                            self.preflight(root)
                    finally:
                        path.write_bytes(before)


if __name__ == '__main__':
    unittest.main()
