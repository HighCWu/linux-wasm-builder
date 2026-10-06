# SPDX-License-Identifier: MIT
import shutil
import tempfile
import unittest
from pathlib import Path

from compare_mmap_benchmarks import compare, load

ROOT = Path(__file__).resolve().parent.parent


class PairedComparison(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for trial in (1, 2, 3):
            for mode in ("off", "on"):
                source = ROOT / "docs" / "benchmarks" / f"mmap-wasm32-dedup-{mode}-20261006.csv"
                shutil.copyfile(source, self.directory / f"trial-{trial}-{mode}.csv")

    def test_known_summary_and_controls(self):
        report = compare(self.directory)
        self.assertIn("| fragment | 256 | 25 | 1 | 193.438 | 31.484 | 6.14 [6.14–6.14] |", report)
        self.assertIn("| fragment | 64 | 0 | 1 | — | — | — |", report)
        self.assertEqual(len(report.splitlines()), 17)

    def test_missing_trial(self):
        (self.directory / "trial-3-on.csv").unlink()
        with self.assertRaises(OSError):
            compare(self.directory)

    def test_mismatched_operations(self):
        path = self.directory / "trial-2-on.csv"
        text = path.read_text().replace("mmap-bench,scale,16,0,1,1,16,", "mmap-bench,scale,16,0,1,1,17,")
        text = text.replace("mmap-bench,scale,16,0,1,2,16,", "mmap-bench,scale,16,0,1,2,17,")
        text = text.replace("mmap-bench,scale,16,0,1,3,16,", "mmap-bench,scale,16,0,1,3,17,")
        path.write_text(text)
        with self.assertRaisesRegex(ValueError, "operation counts differ"):
            compare(self.directory)

    def test_duplicate_sample(self):
        path = self.directory / "trial-1-off.csv"
        path.write_text(path.read_text().replace("mmap-bench,scale,16,0,1,2,", "mmap-bench,scale,16,0,1,1,"))
        with self.assertRaisesRegex(ValueError, "duplicate sample"):
            load(path)


if __name__ == "__main__":
    unittest.main()
