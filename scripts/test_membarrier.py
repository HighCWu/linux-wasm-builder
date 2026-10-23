#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native syscall reference, negative controls and two Wasm frontends; not target execution."""
import pathlib
import os
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/membarrier.c"


class Membarrier(unittest.TestCase):
    def test_native_and_refusal_controls(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="membarrier-native-") as tmp:
                binary = pathlib.Path(tmp) / "test"
                flags = [cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                         "-fsanitize=address,undefined", str(SOURCE)]
                subprocess.run([*flags, "-o", str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 3)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                for defines, reason in (([], "query exposes"),
                                        (["-DMEMBARRIER_FALSE_SUCCESS"], "invalid flags")):
                    subprocess.run([*flags, *defines,
                                    str(ROOT / "scripts/fixtures/membarrier_disabled.c"),
                                    "-Wl,--wrap=syscall", "-o", str(binary)], check=True)
                    failed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertIn(reason, failed.stdout)
                    self.assertNotIn("::vm-test::pass", failed.stdout)

    def test_wasm_frontends_and_static_analysis(self):
        with tempfile.TemporaryDirectory(prefix="membarrier-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "include")]
            resource = subprocess.run(["clang", "-print-resource-dir"], capture_output=True,
                                      text=True, check=True).stdout.strip()
            includes.extend(["-isystem", str(pathlib.Path(resource) / "include")])
            for bits in (32, 64):
                with self.subTest(bits=bits):
                    common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                    subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
                    result = subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror",
                                             str(SOURCE), "-o", "/dev/null"], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_task_handoff_has_explicit_full_barrier(self):
        arch = pathlib.Path(os.environ.get("WASM_MEMBARRIER_ARCH_SOURCE", ROOT / "sources/linux/arch/wasm"))
        process = (arch / "kernel/process.c").read_text()
        switch = process.split("struct task_struct *__switch_to(", 1)[1].split("return prev;", 1)[0]
        self.assertIn("if (IS_ENABLED(CONFIG_MEMBARRIER))\n\t\tsmp_mb();", switch)
        for name in ("defconfig", "wasm32_defconfig", "wasm64_defconfig"):
            config = (arch / "configs" / name).read_text()
            self.assertNotIn("CONFIG_MEMBARRIER", config, "use upstream default, not a replacement override")


if __name__ == "__main__":
    unittest.main()
