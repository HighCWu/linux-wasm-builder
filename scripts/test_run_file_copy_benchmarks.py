# SPDX-License-Identifier: MIT
"""Host orchestration substitutes only; these tests do not boot Linux/Wasm."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_summarize_file_copy_benchmark import components_fixture, fixture


class FreshBootTests(unittest.TestCase):
    def run_case(self, bits=64, invalid=False, exit_code=0, existing=False, components=False):
        with tempfile.TemporaryDirectory(prefix="file-copy-orchestration-") as temp:
            root = Path(temp)
            assets = root / "assets with spaces"
            for name in ("initramfs.cpio", "components.cpio", "disk.img", "kernel/dist/index.js", "runner/run-test.js"):
                path = assets / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            node = fake_bin / "node"
            node.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
if sys.argv[1] == "-e":
    print('{"substitute":true}')
else:
    with open(os.environ["MOCK_CALLS"], "a") as stream:
        stream.write(json.dumps(sys.argv[1:]) + "\\n")
    print(Path(os.environ["MOCK_LOG"]).read_text(), end="")
    sys.exit(int(os.environ["MOCK_EXIT"]))
''')
            node.chmod(0o755)
            log = root / "input.log"
            rows = components_fixture(bits) if components else fixture(bits)
            log.write_text("\n".join(rows[:-1] if invalid else rows) + "\n")
            calls = root / "calls.jsonl"
            output = root / "output"
            if existing:
                output.mkdir()
            result = subprocess.run(
                ["bash", str(Path(__file__).with_name("run_file_copy_benchmarks.sh")),
                 str(assets), str(bits), str(output)] + (["components"] if components else []),
                env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}",
                     "MOCK_CALLS": str(calls), "MOCK_LOG": str(log), "MOCK_EXIT": str(exit_code)},
                capture_output=True, text=True, timeout=20,
            )
            invocations = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            if existing:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(invocations, [])
            elif invalid or exit_code:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(invocations), 1)
                self.assertFalse((output / "boot-2.log").exists())
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(invocations), 3)
                self.assertTrue((output / "runtime.json").exists())
                for trial in (1, 2, 3):
                    self.assertIn(f"wasm{bits}", (output / f"boot-{trial}.md").read_text())
            for args in invocations:
                self.assertEqual(args, [str(assets / "runner/run-test.js"), "--cpus", "1",
                                       "--snapshot-first-disk", "--readonly-disks",
                                       str(assets / "kernel/dist/index.js"),
                                       str(assets / ("components.cpio" if components else "initramfs.cpio")), str(assets / "disk.img")])

    def test_three_separate_boots_for_both_widths(self):
        for bits in (32, 64):
            for components in (False, True):
                with self.subTest(bits=bits, components=components):
                    self.run_case(bits, components=components)

    def test_stops_after_invalid_evidence_or_nonzero_runner(self):
        self.run_case(invalid=True)
        self.run_case(exit_code=7)
        self.run_case(invalid=True, components=True)

    def test_refuses_previous_output(self):
        self.run_case(existing=True)


if __name__ == "__main__":
    unittest.main()
