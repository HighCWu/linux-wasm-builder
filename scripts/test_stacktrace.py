#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise exact diagnostic C code with an old-host model, never host SysRq."""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Stacktrace(unittest.TestCase):
    def test_target_driver_frontends_without_host_sysrq(self):
        musl = ROOT / "sources/musl"
        source = ROOT / "sources/distro/distro/toolchain-smoke/stacktrace.c"
        self.assertIn("#ifndef __wasm__\n#error", source.read_text())
        self.assertIn("syscall(SYS_syslog, 4L,", source.read_text())
        with tempfile.TemporaryDirectory(prefix="stacktrace-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                        "-I", str(musl / "include")]
            for bits in (32, 64):
                common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(source)], check=True)
                result = subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror",
                                         str(source), "-o", "/dev/null"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_kernel_body_and_unterminated_control(self):
        source = pathlib.Path(os.environ.get("WASM_STACKTRACE_SOURCE",
                              ROOT / "sources/linux/arch/wasm/kernel/stacktrace.c")).read_text()
        # The host model cannot validate Linux header transitive includes.
        self.assertIn("#include <linux/pid.h>", source)
        body = re.sub(r"^#include[^\n]*\n", "", source, flags=re.M)
        self.assertNotIn("kmalloc", body)
        self.assertNotIn("%pg", body)
        harness = (ROOT / "scripts/fixtures/stacktrace_harness.c").read_text()
        marker = "/* The checker inserts the actual kernel function body here, unchanged. */"
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="stacktrace-native-") as tmp:
                path = pathlib.Path(tmp)
                unit, binary = path / "main.c", path / "test"
                unit.write_text(harness.replace(marker, body))
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                         "-fsanitize=address,undefined", "-fno-sanitize-recover=all", str(unit), "-o", str(binary)]
                # The negative control needs an actual sanitizer diagnostic,
                # not an external symbolizer walking a slow mounted checkout.
                env = {**os.environ, "ASAN_OPTIONS": os.environ.get("ASAN_OPTIONS", "") +
                       ":symbolize=0:halt_on_error=1:abort_on_error=1:disable_coredump=1"}
                subprocess.run(flags, check=True)
                result = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("honest remote task identity pass", result.stdout)
                guard = "trace[sizeof(trace) - 1] = '\\0';"
                self.assertEqual(body.count(guard), 1)
                unit.write_text(harness.replace(marker, body.replace(guard, "")))
                subprocess.run(flags, check=True)
                negative = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(negative.returncode, 0)
                self.assertRegex(negative.stderr, "AddressSanitizer|runtime error")
                self.assertNotIn("identity pass", negative.stdout)


if __name__ == "__main__":
    unittest.main()
