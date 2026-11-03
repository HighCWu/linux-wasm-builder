#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native file metadata references and musl Wasm frontends, not target acceptance."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/guest-tests/file-timestamps.c"
SOURCES = [
    SOURCE,
    SOURCE.with_name("open-file-metadata.c"),
    SOURCE.with_name("file-creation-modes.c"),
]

with tempfile.TemporaryDirectory(prefix="file-timestamps-") as directory:
    work = Path(directory)
    for compiler in ("gcc", "clang"):
        for source in SOURCES:
            program = work / "metadata"
            subprocess.run(
                [
                    compiler,
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(source),
                    "-o",
                    str(program),
                ],
                check=True,
            )
            creation = source.name == "file-creation-modes.c"
            fixture = work / ("creation-root" if creation else "file")
            if creation:
                fixture.mkdir(exist_ok=True)
            else:
                fixture.write_bytes(b"unchanged" if source == SOURCE else b"old")
            result = subprocess.run(
                [str(program), str(fixture)], capture_output=True, text=True, timeout=15
            )
            assert result.returncode == 0 and result.stdout.count(" pass\n") == 3, (
                result.stdout + result.stderr
            )
            if creation:
                assert not list(fixture.iterdir())
            else:
                assert fixture.read_bytes() == (
                    b"unchanged" if source == SOURCE else b"new"
                )
            print(
                f"{compiler}: native {source.stem} three-stage syscall reference pass"
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
            for source in SOURCES:
                subprocess.run([*flags, "-fsyntax-only", str(source)], check=True)
                subprocess.run(
                    [
                        *flags,
                        "--analyze",
                        "-Xanalyzer",
                        "-analyzer-werror",
                        str(source),
                        "-o",
                        "/dev/null",
                    ],
                    check=True,
                )
            print(
                f"{compiler} wasm{bits}: current musl file metadata consumers frontend/static analysis pass"
            )
