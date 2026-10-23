#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Existing gated musl bodies and standard terminal/session workload, not Wasm acceptance."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
DISTRO = ROOT / "sources/distro/distro"
workload = DISTRO / "fork-continuation/terminal-process.c"
patch = DISTRO / "musl/fork-continuation.patch"
files = ["include/unistd.h", "include/pty.h", "src/legacy/daemon.c", "src/misc/forkpty.c",
         "src/process/fork.c", "src/process/_Fork.c", "arch/wasm32/syscall_arch.h", "src/thread/wasm32/clone.c"]
compilers = os.environ.get("WASM_TERMINAL_COMPILERS", "clang clang-22").split()
assert compilers
with tempfile.TemporaryDirectory(prefix="wasm-terminal-") as tmp:
    work = Path(tmp)
    overlay = work / "patched"
    for name in files:
        destination = overlay / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MUSL / name, destination)
    subprocess.run(["patch", "-p1", "-d", str(overlay), "-i", str(patch)], check=True)
    for name in ("src/legacy/daemon.c", "src/misc/forkpty.c"):
        assert (overlay / name).read_text().replace(
            "#if !defined(__wasm__) || defined(WASM_FORK_CONTINUATION)", "#ifndef __wasm__"
        ) == (MUSL / name).read_text(), "restore existing bodies, do not invent wrappers"
    recipe = (DISTRO / "musl/package.nix").read_text()
    assert '// lib.optionalAttrs enableForkContinuation' in recipe
    assert 'lib.optionalString enableForkContinuation " -DWASM_FORK_CONTINUATION=1"' in recipe
    assert 'patches = [ ./fork-continuation.patch ];' in recipe
    (work / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                               text=True, capture_output=True, check=True)
    (work / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (work / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    probe = work / "probe.c"
    probe.write_text("#define _GNU_SOURCE\n#include <unistd.h>\n#include <pty.h>\n"
                     "int (*d)(int,int)=daemon;\n"
                     "int (*p)(int*,char*,const struct termios*,const struct winsize*)=forkpty;\n")
    for cc in compilers:
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-std=c99", "-nostdinc", "-D_XOPEN_SOURCE=700", "-I", tmp]
            for path in ("arch/wasm32", "arch/generic", "include"):
                flags += ["-I", str(MUSL / path)]
            flags += ["-isystem", str(Path(resource) / "include")]
            baseline = subprocess.run([*flags, "-fsyntax-only", str(probe)], capture_output=True, text=True)
            assert baseline.returncode and "daemon" in baseline.stderr and "forkpty" in baseline.stderr, "default declarations stay hidden"
            profile = [*flags[:4], "-DWASM_FORK_CONTINUATION=1", "-I", str(overlay / "include"), *flags[4:]]
            subprocess.run([*profile, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(probe)], check=True)
            for source in (overlay / "src/legacy/daemon.c", overlay / "src/misc/forkpty.c", workload):
                subprocess.run([*profile, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(source)], check=True)
                subprocess.run([*profile, "--analyze", "-Xanalyzer", "-analyzer-werror", str(source), "-o", "/dev/null"], check=True)
            print(f"{cc} wasm{bits}: original-body profile gating, default refusal and frontend/static checks passed")
    for cc in ("gcc", "clang"):
        objects = []
        for index, name in enumerate(("src/legacy/daemon.c", "src/misc/forkpty.c", "src/misc/login_tty.c")):
            obj = work / f"{cc}-{index}.o"
            # The unchanged musl body intentionally ignores an error-pipe write.
            # glibc's fortified declaration adds a host-only unused-result warning.
            subprocess.run([cc, "-D_GNU_SOURCE=", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-result",
                            "-c", str(MUSL / name), "-o", str(obj)], check=True)
            objects.append(str(obj))
        binary = work / cc
        subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", str(workload), *objects, "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count(" pass\n") == 3 and result.stdout.count("::vm-test::pass") == 1
        print(f"{cc}: actual upstream daemon/forkpty/login_tty bodies and terminal/session reference passed")
