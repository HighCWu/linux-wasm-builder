#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native standard-interface reference and Wasm frontends, not a kernel boot."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/cpu-accounting/runtime.c"
SHIM = r'''
#define _GNU_SOURCE
#include <sys/resource.h>
#include <sys/time.h>
#ifdef LOST_USER
int __real_getrusage(__rusage_who_t,struct rusage *);
int __wrap_getrusage(__rusage_who_t who,struct rusage *value) {
    int result=__real_getrusage(who,value);
    if(!result) value->ru_utime=(struct timeval){0};
    return result;
}
#endif
#ifdef LOST_VIRTUAL
int __real_setitimer(__itimer_which_t,const struct itimerval *,struct itimerval *);
int __wrap_setitimer(__itimer_which_t which,const struct itimerval *value,struct itimerval *old) {
    if(which==ITIMER_VIRTUAL) {
        struct itimerval off={0};
        return __real_setitimer(which,&off,old);
    }
    return __real_setitimer(which,value,old);
}
#endif
'''
with tempfile.TemporaryDirectory(prefix="cpu-accounting-") as tmp:
    path = Path(tmp)
    shim, binary = path / "broken.c", path / "reference"
    shim.write_text(SHIM)
    for cc in os.environ.get("CPU_ACCOUNTING_COMPILERS", "gcc clang").split():
        for variant in (None, "LOST_USER", "LOST_VIRTUAL"):
            extra = [] if variant is None else [str(shim), "-D" + variant,
                "-Wl,--wrap=" + ("getrusage" if variant == "LOST_USER" else "setitimer")]
            subprocess.run([cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                            str(SOURCE), *extra, "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if variant is None:
                assert result.returncode == 0, result.stdout + result.stderr
                assert result.stdout.count(" pass\n") == 4, result.stdout
                assert result.stdout.count("::vm-test::pass") == 1, result.stdout
            else:
                assert result.returncode != 0 and "::vm-test::pass" not in result.stdout, result.stdout
                expected = "user execution was not charged" if variant == "LOST_USER" else "blocked sleep consumed"
                assert expected in result.stdout, result.stdout
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    types = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                           capture_output=True, text=True, check=True).stdout
    (path / "bits/alltypes.h").write_text(types)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-matomics", "-mbulk-memory", "-nostdinc",
                     "-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                     "-I", str(MUSL / "include"), "-isystem", resource + "/include"]
            subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
            subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null", str(SOURCE)], check=True)
print("CPU accounting native reference, lost-user/timer controls and Wasm frontend/analysis passed")
