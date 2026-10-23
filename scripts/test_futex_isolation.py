#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native queued-wait reference and optional-profile header analysis, not Wasm runtime acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/fork-continuation/futex-isolation.c"


class FutexIsolation(unittest.TestCase):
    def test_native_reference_and_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="futex-native-") as tmp:
            binary = Path(tmp) / "test"
            for cc in ("gcc", "clang"):
                subprocess.run([cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                                "-fsanitize=address,undefined", str(SOURCE), "-o", str(binary)], check=True)
                for iteration in range(3):
                    with self.subTest(cc=cc, iteration=iteration):
                        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=65,
                                                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1",
                                                     "UBSAN_OPTIONS": "halt_on_error=1"})
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertEqual(result.stdout.count(" pass\n"), 2)
                        self.assertEqual(result.stdout.count("::vm-test::pass"), 1)

    def test_optional_fork_profile_frontends(self):
        musl = ROOT / "sources/musl"
        with tempfile.TemporaryDirectory(prefix="futex-abi-") as tmp:
            path = Path(tmp)
            (path / "bits").mkdir()
            templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            # Match the EXISTING optional profile patch's declaration gate,
            # never change the pinned musl source or default libc headers.
            unistd = (musl / "include/unistd.h").read_text()
            gate = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
            self.assertIn(gate, unistd)
            (path / "unistd.h").write_text(unistd.replace(gate, "pid_t fork(void);\npid_t _Fork(void);"))
            includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                        "-I", str(musl / "include")]
            for bits in (32, 64):
                common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
                subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(SOURCE),
                                "-o", "/dev/null"], check=True)


if __name__ == "__main__":
    unittest.main()
