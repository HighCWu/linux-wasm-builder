#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real native clone/SEM_UNDO reference and Wasm frontend checks, not target acceptance."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/clone-sharing/runtime.c"
MUSL = ROOT / "sources/musl"
with tempfile.TemporaryDirectory(prefix="clone-semundo-") as tmp:
    work = Path(tmp)
    for cc in ("gcc", "clang"):
        for mode in ("normal", "drop-sharing"):
            source = work / "runtime.c"
            text = SOURCE.read_text()
            if mode != "normal":
                changed = text.replace(
                    "shared ? CLONE_SYSVSEM : 0", "0 /* omitted shared undo */"
                )
                assert changed != text
                text = changed
            source.write_text(text)
            binary = work / "reference"
            fixture = work / f"{cc}-{mode}"
            subprocess.run(
                [
                    cc,
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-DROOT=" + json.dumps(str(fixture)),
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            result = subprocess.run(
                [str(binary)], cwd="/", capture_output=True, text=True, timeout=15
            )
            if mode == "normal":
                assert (
                    result.returncode == 0
                    and result.stdout.count("::vm-test::pass") == 1
                ), result.stdout + result.stderr
                assert result.stdout.count(" pass\n") == 3
            else:
                assert (
                    result.returncode != 0
                    and "shared undo survives child exit" in result.stderr
                ), result.stdout + result.stderr
        print(
            f"{cc}: real native clone shared/private SEM_UNDO, last-exit cleanup and omitted-sharing negative control pass"
        )
    exit_source = SOURCE.parent.parent / "clone-exit-signal/runtime.c"
    for cc in ("gcc", "clang"):
        for negative in (False, True):
            source = work / "exit-reference.c"
            text = exit_source.read_text()
            if negative:
                changed = text.replace(
                    "CLONE_PIDFD | signal", "CLONE_PIDFD | (signal * 0) | SIGCHLD"
                )
                assert changed != text
                text = changed
            source.write_text(text)
            binary = work / "exit-reference"
            subprocess.run(
                [
                    cc,
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=15
            )
            if negative:
                assert (
                    result.returncode != 0 and "ordinary wait excludes" in result.stderr
                ), result.stdout + result.stderr
            else:
                assert result.returncode == 0 and result.stdout.count(" pass\n") == 3, (
                    result.stdout + result.stderr
                )
        print(
            f"{cc}: real native notification/PIDFD/WCLONE semantics and forced-SIGCHLD negative control pass"
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
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (work / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    (work / "linux").mkdir()
    supplied = os.environ.get("WASM_CLONE_SEMUNDO_UAPI")
    header = (
        Path(supplied).read_text()
        if supplied
        else subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT / "sources/linux"),
                "show",
                "HEAD:include/uapi/linux/sched.h",
            ],
            text=True,
        )
    )
    (work / "linux/sched.h").write_text(header)
    (work / "linux/types.h").write_text(
        "#define __aligned_u64 unsigned long long __attribute__((aligned(8)))\n"
    )
    for cc in os.environ.get("WASM_CLONE_SEMUNDO_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output(
            [cc, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-O2", "-nostdinc", "-I", tmp]
            # The optional profile restores this existing declaration. No libc
            # implementation or new API is supplied by the lightweight fixture.
            declaration = work / "fork.h"
            declaration.write_text("int fork(void);\n")
            flags += ["-include", str(declaration)]
            for directory in ("arch/wasm32", "arch/generic", "include"):
                flags += ["-I", str(MUSL / directory)]
            flags += ["-isystem", resource + "/include", "-Wall", "-Wextra", "-Werror"]
            for consumer in (
                SOURCE,
                SOURCE.parent.parent / "clone-flags64/runtime.c",
                exit_source,
            ):
                subprocess.run([*flags, "-fsyntax-only", str(consumer)], check=True)
                subprocess.run(
                    [
                        *flags,
                        "--analyze",
                        "-Xanalyzer",
                        "-analyzer-werror",
                        str(consumer),
                        "-o",
                        "/dev/null",
                    ],
                    check=True,
                )
            print(
                f"{cc} wasm{bits}: clone SEM_UNDO/NNP/exit-signal consumers frontend and static analysis pass; not target acceptance"
            )
