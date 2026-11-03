#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile/analyze the ordinary signal consumer with actual musl Wasm headers."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/cooperative-poll/runtime.c"
with tempfile.TemporaryDirectory(prefix="cooperative-poll-consumer-") as tmp:
    path = Path(tmp)
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.check_output(
        ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates, text=True
    )
    (path / "bits/alltypes.h").write_text(generated)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    for cc in ("gcc", "clang"):
        for variant in ([], ["-DCOOPERATIVE_CPU_TIMERS=1"]):
            subprocess.run(
                [
                    cc,
                    "-O2",
                    "-pthread",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    *variant,
                    "-c",
                    str(SOURCE),
                    "-o",
                    str(path / "native.o"),
                ],
                check=True,
            )
    for cc in os.environ.get("WASM_POLL_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output(
            [cc, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-O2", "-nostdinc", "-I", tmp]
            for include in ("arch/wasm32", "arch/generic", "include"):
                flags += ["-I", str(MUSL / include)]
            flags += ["-isystem", resource + "/include", "-Wall", "-Wextra", "-Werror"]
            for variant in ([], ["-DCOOPERATIVE_CPU_TIMERS=1"]):
                subprocess.run(
                    flags
                    + variant
                    + [
                        "-matomics",
                        "-mbulk-memory",
                        "-mllvm",
                        "-wasm-enable-sjlj",
                        "-fsanitize-coverage=trace-pc,no-prune,edge",
                        "-c",
                        str(SOURCE),
                        "-o",
                        str(path / "consumer.o"),
                    ],
                    check=True,
                )
                subprocess.run(
                    flags
                    + variant
                    + [
                        "--analyze",
                        "-Xanalyzer",
                        "-analyzer-werror",
                        str(SOURCE),
                        "-o",
                        "/dev/null",
                    ],
                    check=True,
                )
            print(
                f"{cc} wasm{bits}: ordinary/CPU timer consumers compile with instrumentation/SjLj and pass static analysis; not Linux execution"
            )
