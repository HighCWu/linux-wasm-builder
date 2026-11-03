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
        for mode in ("normal", "drop-sharing", "drop-io"):
            source = work / "runtime.c"
            text = SOURCE.read_text()
            if mode == "drop-sharing":
                changed = text.replace(
                    "shared ? CLONE_SYSVSEM : 0", "0 /* omitted shared undo */"
                )
                assert changed != text
                text = changed
            if mode == "drop-io":
                changed = text.replace("create(legacy, CLONE_IO)", "create(legacy, 0)")
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
                assert result.stdout.count(" pass\n") == 4
            else:
                assert (
                    result.returncode != 0
                    and (
                        "shared I/O priority reaches parent"
                        if mode == "drop-io"
                        else "shared undo survives child exit"
                    )
                    in result.stderr
                ), result.stdout + result.stderr
        print(
            f"{cc}: real native shared/private SEM_UNDO and IO priority, cleanup and omitted-flag negative controls pass"
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
    trace_source = SOURCE.parent.parent / "clone-untraced/runtime.c"
    for cc in ("gcc", "clang"):
        for negative in (None, "UNTRACED", "PTRACE"):
            binary = work / "trace-reference"
            subprocess.run(
                [
                    cc,
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    *(["-DDROP_" + negative] if negative else []),
                    str(trace_source),
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
                    result.returncode != 0
                    and (
                        "UNTRACED suppresses forced child tracing"
                        if negative == "UNTRACED"
                        else "explicit PTRACE child inherits SIGSTOP"
                    )
                    in result.stderr
                ), result.stdout + result.stderr
            else:
                assert (
                    result.returncode == 0
                    and result.stdout.count(" pass\n") == 3
                    and result.stdout.count("::vm-test::pass") == 1
                ), result.stdout + result.stderr
        print(
            f"{cc}: native forced/explicit ptrace, UNTRACED combinations and dropped-flag negative controls pass"
        )
    parent_source = SOURCE.parent.parent / "clone-parent/runtime.c"
    for cc in ("gcc", "clang"):
        binary = work / "parent-reference"
        subprocess.run(
            [
                cc,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(parent_source),
                "-o",
                str(binary),
            ],
            check=True,
        )
        result = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0 and result.stdout.count(" pass\n") == 2, (
            result.stdout + result.stderr
        )
        print(
            f"{cc}: real native CLONE_PARENT grandparent wait while caller stays alive pass"
        )
    pidfd_source = SOURCE.parent.parent / "pidfd-getfd/runtime.c"
    for cc in ("gcc", "clang"):
        binary = work / "pidfd-getfd"
        subprocess.run(
            [
                cc,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(pidfd_source),
                "-o",
                str(binary),
            ],
            check=True,
        )
        target = work / "pidfd-child-only-file"
        result = subprocess.run(
            [str(binary), str(target)], capture_output=True, text=True, timeout=20
        )
        assert not target.exists(), (
            "child-owned native file must be removed on both paths"
        )
        if result.returncode == 77:
            assert (
                "host policy" in result.stderr
                and "::vm-test::pass" not in result.stdout
            )
            print(
                f"{cc}: host policy blocks native pidfd_getfd; compiled only, no runtime acceptance"
            )
        else:
            assert result.returncode == 0 and result.stdout.count(" pass\n") == 3, (
                result.stdout + result.stderr
            )
            subprocess.run(
                [
                    cc,
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-DFORCE_LOCAL_DUP",
                    str(pidfd_source),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            negative = subprocess.run(
                [str(binary), str(target)], capture_output=True, text=True, timeout=20
            )
            assert (
                negative.returncode != 0
                and "copied descriptor reads child data" in negative.stderr
            ), negative.stdout + negative.stderr
            target.unlink(missing_ok=True)
            print(
                f"{cc}: native pidfd_getfd three stages and local-dup negative control pass"
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
    for name, variable in (
        ("ioprio.h", "WASM_CLONE_IOPRIO_UAPI"),
        ("stddef.h", "WASM_CLONE_STDDEF_UAPI"),
    ):
        supplied = os.environ.get(variable)
        data = (
            Path(supplied).read_text()
            if supplied
            else subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(ROOT / "sources/linux"),
                    "show",
                    "HEAD:include/uapi/linux/" + name,
                ],
                text=True,
            )
        )
        (work / "linux" / name).write_text(data)
    (work / "linux/types.h").write_text(
        "#ifndef CLONE_UAPI_SCALARS\n#define CLONE_UAPI_SCALARS\n"
        "typedef unsigned short __u16;\n"
        "#define __aligned_u64 unsigned long long __attribute__((aligned(8)))\n#endif\n"
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
                SOURCE.parent.parent / "clone-lifecycle/runtime.c",
                parent_source,
                SOURCE.parent.parent / "clone-empty-mount/runtime.c",
                trace_source,
                exit_source,
                pidfd_source,
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
                f"{cc} wasm{bits}: clone resource/lifecycle consumers frontend and static analysis pass; not target acceptance"
            )
