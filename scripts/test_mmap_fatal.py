#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact copy-body models and Wasm controller analysis, not target VFS acceptance."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCH = Path(os.environ.get("WASM_MMAP_FATAL_ARCH", ROOT / "sources/linux/arch/wasm"))


class MmapFatal(unittest.TestCase):
    def test_exact_copy_body_models_and_analysis(self):
        for cc in ("gcc", "clang"):
            subprocess.run([sys.executable, "-B", str(ARCH / "tests/run-mmap-file-host.py")],
                           env={**os.environ, "CC": cc}, check=True)
        source = (ARCH / "kernel/mmap_file.c").read_text()
        shim = (ARCH / "tests/mmap-file-host.h").read_text()
        checks = (ARCH / "tests/mmap-file-host.c").read_text()
        unit = shim + "\n" + re.sub(r"^#include[^\n]*\n", "", source, flags=re.M) + "\n" + checks
        for bits in (32, 64):
            subprocess.run(["clang", "-xc", "-std=gnu11", "--analyze", "-Xanalyzer", "-analyzer-werror",
                            "-DCONFIG_WASM_FILE_MMAP=1", "-DCONFIG_WASM_MMAP_COPY_TEST=1",
                            *(["-DCONFIG_32BIT=1"] if bits == 32 else []), "-o", "/dev/null", "-"],
                           input=unit, text=True, check=True)

    def test_wasm_controller_frontends(self):
        musl = ROOT / "sources/musl"
        source = ROOT / "sources/distro/distro/basic-init/tests/mmap-vfs-exit.c"
        with tempfile.TemporaryDirectory(prefix="mmap-fatal-abi-") as tmp:
            path = Path(tmp)
            (path / "bits").mkdir()
            templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                        "-I", str(musl / "include")]
            resource_dir = subprocess.check_output(["clang", "-print-resource-dir"], text=True).strip()
            includes += ["-isystem", str(Path(resource_dir) / "include")]
            for bits in (32, 64):
                common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(source)], check=True)
                subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(source),
                                "-o", "/dev/null"], check=True)


if __name__ == "__main__":
    unittest.main()
