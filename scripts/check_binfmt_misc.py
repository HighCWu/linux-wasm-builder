#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile/analyze real interpreted-exec workloads; never run host mount/setuid code."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCES = ROOT / "sources/distro/distro/binfmt-misc"
with tempfile.TemporaryDirectory(prefix="binfmt-misc-analysis-") as tmp:
    path = Path(tmp)
    for cc in ("gcc", "clang"):
        for filename in ("runtime.c", "helper.c"):
            subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCES / filename),
                            "-o", str(path / filename.removesuffix(".c"))], check=True)
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (path / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    unistd = (MUSL / "include/unistd.h").read_text()
    gate = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
    assert gate in unistd
    (path / "unistd.h").write_text(unistd.replace(gate, "pid_t fork(void);\npid_t _Fork(void);"))
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-nostdinc", "-I", tmp,
                     "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                     "-I", str(MUSL / "include"), "-isystem", resource + "/include"]
            for filename in ("runtime.c", "helper.c"):
                source = str(SOURCES / filename)
                subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", source], check=True)
                subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null", source], check=True)
print("binfmt_misc native compilation and Wasm32/64 frontend/static analysis passed; no host privileged execution")
