#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native Linux reference semantics and Wasm source analysis, not a Wasm kernel run."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/signal-altstack.c"


class SignalAltstack(unittest.TestCase):
    def test_native_reference_and_sanitizers(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="altstack-native-") as tmp:
                binary = pathlib.Path(tmp) / "test"
                subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                                str(SOURCE), "-o", str(binary)], check=True)
                # Keep ASan's bounds checks, but neither pre-install its signal
                # stack nor relocate escaped locals to a heap-backed fake stack:
                # this workload deliberately measures the actual C stack region.
                environment = {**os.environ, "ASAN_OPTIONS": os.environ.get("ASAN_OPTIONS", "") +
                               ":use_sigaltstack=0:detect_stack_use_after_return=0:halt_on_error=1",
                               "UBSAN_OPTIONS": os.environ.get("UBSAN_OPTIONS", "") + ":halt_on_error=1"}
                result = subprocess.run([str(binary)], env=environment, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 5)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)

    def test_both_wasm_frontends_and_static_analysis(self):
        with tempfile.TemporaryDirectory(prefix="altstack-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"), "-I", str(MUSL / "include")]
            for bits in (32, 64):
                with self.subTest(bits=bits):
                    common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                    for source in (SOURCE, SOURCE.with_name("signal-stack-legacy.c"), MUSL / "src/signal/wasm32/restore.c"):
                        subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(source)], check=True)
                        analyzed = subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror",
                                                   str(source), "-o", "/dev/null"], capture_output=True, text=True)
                        self.assertEqual(analyzed.returncode, 0, analyzed.stderr)


if __name__ == "__main__":
    unittest.main()
