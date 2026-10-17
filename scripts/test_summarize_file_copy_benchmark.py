# SPDX-License-Identifier: MIT
import unittest
from itertools import permutations
from summarize_file_copy_benchmark import COMPONENT_ORDER, summarize


def fixture(bits=64):
    rows = []
    for length in (65536, 131072):
        for trial in range(1, 6):
            for mode in (("mmap", "pread") if trial % 2 else ("pread", "mmap")):
                elapsed = 64000 if mode == "pread" else 128000
                checksum = (length // 4096 * 11 + 230) * 64
                rows.append(f"prefix> file-copy-bench,{bits},{mode},{length},{trial},64,{elapsed},{checksum}")
    return rows + ["file mmap: warm paired copy benchmark completed; no speed threshold", "::vm-test::pass"]


def components_fixture(bits=64):
    rows = []
    for length in (65536, 131072):
        for trial, order in enumerate(COMPONENT_ORDER, 1):
            for mode in order:
                elapsed = {"pread": 64000, "anon-pread": 128000, "mmap": 384000}[mode]
                checksum = (length // 4096 * 11 + 230) * 64
                rows.append(f"file-copy-components,{bits},{mode},{length},{trial},64,{elapsed},{checksum}")
    return rows + ["file mmap: warm three-path diagnostic completed; no speed threshold", "::vm-test::pass"]


class FileCopyBenchmarkTests(unittest.TestCase):
    def test_components(self):
        self.assertEqual(set(COMPONENT_ORDER), set(permutations(("pread", "mmap", "anon-pread"))))
        for bits in (32, 64):
            report = summarize(components_fixture(bits), bits, components=True)
            self.assertIn("| 65536 | 1.000 | 2.000 | 6.000 | 2.000 | 3.000 | 6.000 |", report)
            self.assertIn("not additive", report)
        for rows in [components_fixture()[1:], components_fixture()[:-1],
                     components_fixture() + [fixture()[0]], fixture(),
                     components_fixture()[:1] + components_fixture(),
                     [row.replace(",6,64,", ",7,64,") for row in components_fixture()],
                     [row.replace(",anon-pread,", ",unknown,") for row in components_fixture()],
                     [row.replace(",384000,", ",0,") for row in components_fixture()],
                     [row.replace(",25984", ",25985") for row in components_fixture()],
                     [row.replace(",64,mmap,", ",32,mmap,") for row in components_fixture()]]:
            with self.subTest(rows=rows[:1]), self.assertRaises(ValueError):
                summarize(rows, 64, components=True)
        for rows in [components_fixture(), fixture() + [components_fixture()[0]]]:
            with self.assertRaises(ValueError):
                summarize(rows, 64)
        rows = components_fixture()
        rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaises(ValueError):
            summarize(rows, 64, components=True)

    def test_components_uses_paired_ratios(self):
        rows = components_fixture()
        for index, row in enumerate(rows):
            fields = row.split(",")
            if len(fields) != 8 or fields[3] != "65536":
                continue
            trial = int(fields[4])
            if fields[2] == "pread":
                fields[6] = str(trial * 64000)
            elif fields[2] == "anon-pread":
                fields[6] = str((100 if trial == 1 else trial) * 64000)
            rows[index] = ",".join(fields)
        self.assertIn("| 65536 | 3.500 | 4.500 | 6.000 | 1.000 |", summarize(rows, 64, components=True))

    def test_both_widths(self):
        for bits in (32, 64):
            report = summarize(fixture(bits), bits)
            self.assertIn(f"wasm{bits}", report)
            self.assertIn("| 65536 | 1.000 | 2.000 | 2.000 |", report)
            self.assertIn("| 131072 | 1.000 | 2.000 | 2.000 |", report)

    def test_rejects_invalid_records_and_run_markers(self):
        for old, new in [
            (",64,mmap,", ",32,mmap,"),
            (",mmap,", ",unknown,"),
            (",65536,", ",65537,"),
            (",1,64,", ",6,64,"),
            (",1,64,", ",1,63,"),
            (",128000,", ",0,"),
            (",128000,", ",-1,"),
            (",128000,", ",NaN,"),
            (",25984", ",25985"),
        ]:
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                rows = fixture()
                rows[0] = rows[0].replace(old, new)
                summarize(rows, 64)
        for rows in [
            [], fixture()[1:], fixture()[:-1], fixture()[:-2] + ["::vm-test::pass"],
            fixture()[:1] + fixture(), fixture() + fixture()[:1],
            fixture() + ["::vm-test::pass"], fixture() + [fixture()[-2]],
            fixture() + ["::vm-test::fail: invalid"],
            fixture() + ["host-workload-only: no target evidence"],
        ]:
            with self.subTest(rows=rows[:1]), self.assertRaises(ValueError):
                summarize(rows, 64)

    def test_uses_median_of_paired_ratios_not_ratio_of_medians(self):
        rows = fixture()
        # Ratios [100, 1, 1, 1, 1] have median 1; ratio of medians differs.
        for index, elapsed in enumerate((6400, 64000, 128000, 192000, 256000)):
            row = 2 * index + (1 if index % 2 == 0 else 0)
            rows[row] = rows[row].replace(",64000,", f",{elapsed},")
            new_mmap = 640000 if index == 0 else elapsed
            mapping_row = 2 * index + (0 if index % 2 == 0 else 1)
            rows[mapping_row] = rows[mapping_row].replace(",128000,", f",{new_mmap},")
        self.assertIn("| 65536 | 2.000 | 3.000 | 1.000 |", summarize(rows, 64))


if __name__ == "__main__":
    unittest.main()
