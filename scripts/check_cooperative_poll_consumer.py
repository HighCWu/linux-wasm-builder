#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile/analyze the ordinary signal consumer with actual musl Wasm headers."""

import os
from pathlib import Path
import re
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
    (path / "src/thread").mkdir(parents=True)
    unmap = path / "src/thread/__unmapself.c"
    unmap.write_text((MUSL / "src/thread/__unmapself.c").read_text())
    subprocess.run(
        ["patch", "--fuzz=0", "-s", "-p1", "-d", tmp],
        input=(ROOT / "sources/distro/distro/musl/cooperative-poll.patch").read_text(),
        text=True,
        check=True,
    )
    for cc in ("gcc", "clang"):
        for variant in (
            [],
            ["-DCOOPERATIVE_CPU_TIMERS=1"],
            ["-DCOOPERATIVE_LIBRARY_POLL=1"],
        ):
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
            for source in (
                "src/thread/wasm32/clone.c",
                "src/thread/pthread_create.c",
                "src/string/memchr.c",
                str(unmap),
            ):
                ir = path / "library.ll"
                startup = source in (
                    "src/thread/wasm32/clone.c",
                    "src/thread/pthread_create.c",
                )
                subprocess.run(
                    flags[:4]
                    + [
                        "-I",
                        str(MUSL / "src/include"),
                        "-I",
                        str(MUSL / "src/internal"),
                    ]
                    + flags[4:]
                    + [
                        "-Wno-unused-parameter",
                        "-Wno-cast-function-type",
                        "-matomics",
                        "-mbulk-memory",
                        "-fsanitize-coverage=trace-pc,no-prune,edge",
                        *(
                            ["-fno-sanitize-coverage=trace-pc,no-prune,edge"]
                            if startup
                            else []
                        ),
                        "-S",
                        "-emit-llvm",
                        str(MUSL / source),
                        "-o",
                        str(ir),
                    ],
                    check=True,
                )
                assert ("@__sanitizer_cov_trace_pc" in ir.read_text()) != startup, (
                    source
                )
                if source == str(unmap):
                    body = re.search(
                        r"^define [^\n]*@__unmapself\(.*?^}",
                        ir.read_text(),
                        re.M | re.S,
                    )
                    assert body and body[0].index("global.set __tls_base") < body[
                        0
                    ].index("@free_and_exit")
            for variant in (
                [],
                ["-DCOOPERATIVE_CPU_TIMERS=1"],
                ["-DCOOPERATIVE_LIBRARY_POLL=1"],
            ):
                if "-DCOOPERATIVE_LIBRARY_POLL=1" in variant:
                    ir = path / "consumer.ll"
                    subprocess.run(
                        flags
                        + variant
                        + [
                            "-fsanitize-coverage=trace-pc,no-prune,edge",
                            "-S",
                            "-emit-llvm",
                            str(SOURCE),
                            "-o",
                            str(ir),
                        ],
                        check=True,
                    )
                    driver = re.search(
                        r"^define [^\n]*@library_spin\(.*?^}",
                        ir.read_text(),
                        re.M | re.S,
                    )
                    assert driver and "@__sanitizer_cov_trace_pc" not in driver[0]
                    assert "load volatile ptr" in driver[0], (
                        "keep the actual libc function call"
                    )
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
                f"{cc} wasm{bits}: ordinary/CPU/libc consumers compile with instrumentation/SjLj and pass static analysis; library driver has no checkpoints; not Linux execution"
            )
