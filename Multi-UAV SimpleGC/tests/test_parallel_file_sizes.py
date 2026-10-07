"""Exercise CI file-size policy using disposable repositories, without SITL."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[2] / ".github/scripts/check_file_sizes.py"
SPEC = importlib.util.spec_from_file_location("check_file_sizes", CHECKER)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class ParallelFileSizeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Offline test")
        self.git("config", "user.email", "offline@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "commit.gpgsign", "false")
        self.write("legacy.bin", checker.MAX_FILE_BYTES + 1)
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.repo), *arguments],
                                       text=True, encoding="utf-8")

    def write(self, name, size):
        (self.repo / name).write_bytes(b"x" * size)

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "fixture")

    def test_unchanged_legacy_large_binary_is_allowed(self):
        self.write("new source.py", 12)
        self.commit()
        self.assertEqual(checker.oversized_files(self.repo, self.base), [])

    def test_new_file_over_five_mib_is_rejected(self):
        self.write("new data.bin", checker.MAX_FILE_BYTES + 1)
        self.commit()
        self.assertEqual(checker.oversized_files(self.repo, self.base),
                         [("new data.bin", checker.MAX_FILE_BYTES + 1)])

    def test_exactly_five_mib_is_allowed(self):
        self.write("boundary.bin", checker.MAX_FILE_BYTES)
        self.commit()
        self.assertEqual(checker.oversized_files(self.repo, self.base), [])

    def test_modified_legacy_large_binary_is_rejected(self):
        self.write("legacy.bin", checker.MAX_FILE_BYTES + 2)
        self.commit()
        self.assertEqual(checker.oversized_files(self.repo, self.base),
                         [("legacy.bin", checker.MAX_FILE_BYTES + 2)])

    def test_deleted_legacy_large_binary_is_allowed(self):
        (self.repo / "legacy.bin").unlink()
        self.commit()
        self.assertEqual(checker.oversized_files(self.repo, self.base), [])

    def test_renamed_large_binary_is_rejected(self):
        (self.repo / "legacy.bin").rename(self.repo / "renamed data.bin")
        self.commit()
        self.assertEqual(checker.oversized_files(self.repo, self.base),
                         [("renamed data.bin", checker.MAX_FILE_BYTES + 1)])

    def test_committed_blob_is_checked_even_if_worktree_is_smaller(self):
        self.write("submitted.bin", checker.MAX_FILE_BYTES + 1)
        self.commit()
        self.write("submitted.bin", 1)
        self.assertEqual(checker.oversized_files(self.repo, self.base),
                         [("submitted.bin", checker.MAX_FILE_BYTES + 1)])


if __name__ == "__main__":
    unittest.main()
