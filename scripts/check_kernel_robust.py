#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native kernel reference and Wasm frontend review; not Wasm owner-death acceptance."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/kernel-robust/runtime.c"
MUSL = ROOT / "sources/musl"
with tempfile.TemporaryDirectory(prefix="kernel-robust-") as tmp:
    path = Path(tmp)
    for cc in ("gcc", "clang"):
        for mode in ("normal", "no-registration"):
            binary = path / "native"
            result = subprocess.run(
                [
                    cc,
                    "-O2",
                    "-pthread",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    *(["-DROBUST_SKIP_REGISTRATION=1"] if mode != "normal" else []),
                    str(SOURCE),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=15
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
                    and "kernel-owned owner-death transition" in result.stdout
                ), result.stdout + result.stderr
        print(
            f"{cc}: actual Linux raw-exit/SIGKILL wake, pending/faulted list reference and missing-registration refusal pass"
        )
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    (path / "bits/alltypes.h").write_text(
        subprocess.check_output(
            ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
            input=templates,
            text=True,
        )
    )
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    (path / "linux").mkdir()
    # The actual fixed UAPI declarations; only its scalar/compiler includes are
    # modeled here. Full installed kernel headers are used by the target build.
    header = os.environ.get("WASM_ROBUST_UAPI")
    uapi = (
        Path(header).read_text()
        if header
        else subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT / "sources/linux"),
                "show",
                "HEAD:include/uapi/linux/futex.h",
            ],
            text=True,
        )
    )
    (path / "linux/futex.h").write_text(uapi)
    (path / "linux/types.h").write_text(
        "typedef unsigned int __u32;\ntypedef unsigned long long __u64;\n"
    )
    (path / "linux/compiler.h").write_text("#define __user\n")
    for cc in os.environ.get("WASM_ROBUST_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output(
            [cc, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-O2", "-nostdinc", "-I", tmp]
            for include in ("arch/wasm32", "arch/generic", "include"):
                flags += ["-I", str(MUSL / include)]
            flags += ["-isystem", resource + "/include", "-Wall", "-Wextra", "-Werror"]
            subprocess.run(
                flags
                + [
                    "-matomics",
                    "-mbulk-memory",
                    "-mllvm",
                    "-wasm-enable-sjlj",
                    "-c",
                    str(SOURCE),
                    "-o",
                    str(path / "robust.o"),
                ],
                check=True,
            )
            subprocess.run(
                flags
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
                f"{cc} wasm{bits}: public libc/fixed futex UAPI frontend and static analysis pass; not Wasm kernel execution"
            )
