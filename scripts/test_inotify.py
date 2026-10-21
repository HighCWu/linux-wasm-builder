#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Lightweight native workload and existing Wasm libc ABI checks, not Wasm execution."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/inotify.c"
MUSL = ROOT / "sources/musl"


class Inotify(unittest.TestCase):
    def test_native_workload_and_cookie_negative_control(self):
        for compiler in ("gcc", "clang"):
            with self.subTest(compiler=compiler), tempfile.TemporaryDirectory(prefix="inotify-") as tmp:
                binary = pathlib.Path(tmp) / "test"
                for broken in (False, True):
                    text = SOURCE.read_text().replace("/tmp/inotify-XXXXXX", tmp + "/events-XXXXXX")
                    if broken:
                        text = text.replace("to = event.cookie", "to = 0")
                    source = pathlib.Path(tmp) / "test.c"
                    source.write_text(text)
                    subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                    "-fsanitize=address,undefined", str(source), "-o", str(binary)], check=True)
                    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                    if broken:
                        self.assertNotEqual(run.returncode, 0)
                        self.assertIn("event masks and rename cookie", run.stdout)
                        self.assertNotIn("::vm-test::pass", run.stdout)
                    else:
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                        self.assertEqual(run.stdout.count("::vm-test::pass"), 1)
                        self.assertEqual(run.stdout.count(" pass\n"), 3)

    def test_existing_musl_headers_and_workload_both_widths(self):
        with tempfile.TemporaryDirectory(prefix="inotify-abi-") as tmp:
            bits = pathlib.Path(tmp) / "bits"
            bits.mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                                       input=templates, capture_output=True, text=True, check=True)
            (bits / "alltypes.h").write_text(generated.stdout)
            for target in ("wasm32", "wasm64"):
                with self.subTest(target=target):
                    subprocess.run(["clang", f"--target={target}", "-fsyntax-only", "-std=c11",
                                    "-nostdinc", "-Wall", "-Wextra", "-Werror", "-isystem", tmp,
                                    "-isystem", str(MUSL / "arch/wasm32"), "-isystem", str(MUSL / "arch/generic"),
                                    "-isystem", str(MUSL / "include"), str(SOURCE)], check=True)


if __name__ == "__main__":
    unittest.main()
