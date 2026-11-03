#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native timestamp reference and current musl Wasm frontends, not target acceptance."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/guest-tests/file-timestamps.c"

with tempfile.TemporaryDirectory(prefix="file-timestamps-") as directory:
    work = Path(directory)
    for compiler in ("gcc", "clang"):
        program = work / "timestamps"
        subprocess.run(
            [
                compiler,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(SOURCE),
                "-o",
                str(program),
            ],
            check=True,
        )
        fixture = work / "file"
        fixture.write_bytes(b"unchanged")
        result = subprocess.run(
            [str(program), str(fixture)], capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0 and result.stdout.count(" pass\n") == 3, (
            result.stdout + result.stderr
        )
        assert fixture.read_bytes() == b"unchanged"
        print(
            f"{compiler}: native signed utimensat/futimens, invalid nanoseconds and OMIT reference pass"
        )
    (work / "bits").mkdir()
    template = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    (work / "bits/alltypes.h").write_text(
        subprocess.check_output(
            ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=template, text=True
        )
    )
    for compiler in os.environ.get(
        "WASM_FILE_TIMESTAMP_COMPILERS", "clang clang-22"
    ).split():
        resource = subprocess.check_output(
            [compiler, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            flags = [
                compiler,
                f"--target=wasm{bits}",
                "-O2",
                "-nostdinc",
                "-I",
                directory,
            ]
            for part in ("arch/wasm32", "arch/generic", "include"):
                flags += ["-I", str(MUSL / part)]
            flags += ["-isystem", resource + "/include", "-Wall", "-Wextra", "-Werror"]
            subprocess.run([*flags, "-fsyntax-only", str(SOURCE)], check=True)
            subprocess.run(
                [
                    *flags,
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
                f"{compiler} wasm{bits}: current musl timestamp consumer frontend/static analysis pass"
            )
