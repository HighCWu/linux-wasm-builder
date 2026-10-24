#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile exact strict policy with state/exit models; never restrict the host."""

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "sources/linux"
MUSL = ROOT / "sources/musl"


def source(name):
    if "WASM_SECCOMP_SOURCE_ROOT" in os.environ:
        return (Path(os.environ["WASM_SECCOMP_SOURCE_ROOT"]) / name).read_text()
    file = LINUX / name
    if file.is_file():
        return file.read_text()
    return subprocess.check_output(
        ["git", "-C", str(LINUX), "show", "HEAD:" + name], text=True
    )


def function(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


kernel = source("kernel/seccomp.c")
arch = source("arch/wasm/include/asm/seccomp.h")
generic = source("include/asm-generic/seccomp.h")
numbers = source("include/uapi/asm-generic/unistd.h")
kconfig = source("arch/wasm/Kconfig")
assert "select HAVE_ARCH_SECCOMP\n" in kconfig
assert "select HAVE_ARCH_SECCOMP_FILTER" not in kconfig
entry = source("arch/wasm/kernel/syscall.c")
assert 'export_name("seccomp_strict_v1")' in entry
assert "READ_ONCE(current->seccomp.mode) == SECCOMP_MODE_STRICT" in entry
worker = (ROOT / "sources/distro/packages/kernel/src/worker.ts").read_text()
assert worker.count("kernel_instance.exports.seccomp_strict_v1?.() === 1") == 2
assert "dispatch_fork_checkpoint(" in worker and "dispatch_fork_syscall(" in worker
assert entry.index("syscall_enter_from_user_mode_work(regs, nr)") < entry.index(
    "syscall_table[nr](regs)"
)
common = source("include/linux/entry-common.h")
assert common.index("arch_ptrace_report_syscall_entry(regs)") < common.index(
    "__secure_computing()"
)
policy = re.search(
    r"static const int mode1_syscalls\[\] = \{.*?\n\};", kernel, re.S
).group()
policy += "\n" + function(
    kernel, "static void __secure_computing_strict(int this_syscall)"
)
policy += "\n" + function(kernel, "void secure_computing_strict(int this_syscall)")
driver = r"""
#include <setjmp.h>
#include <signal.h>
#include <stdlib.h>
#define SECCOMP_MODE_DISABLED 0
#define SECCOMP_MODE_STRICT 1
#define SECCOMP_MODE_DEAD 3
#define PT_SUSPEND_SECCOMP 0
#define CONFIG_CHECKPOINT_RESTORE 0
#define IS_ENABLED(x) (x)
#define unlikely(x) (x)
#define SECCOMP_RET_KILL_THREAD 0
static struct { struct { int mode; } seccomp; int ptrace; } state, *current = &state;
static jmp_buf failure;
static int logged;
static void seccomp_log(int nr, int sig, int action, int force)
{ (void)nr; (void)action; (void)force; if(sig!=SIGKILL)abort(); ++logged; }
static void do_exit(int sig) { if(sig!=SIGKILL)abort(); longjmp(failure,1); }
#define true 1
#define BUG() abort()
#include <asm/seccomp.h>
POLICY
int main(void) {
    /* Include negative and out-of-table syscall numbers too. */
    for(volatile int nr=-2;nr<=__NR_syscalls+1;++nr) {
        state.seccomp.mode=SECCOMP_MODE_STRICT;logged=0;
        int killed=setjmp(failure);
        if(!killed)secure_computing_strict(nr);
        int allowed=nr==__NR_read||nr==__NR_write||nr==__NR_exit;
        if(allowed ? killed||logged||state.seccomp.mode!=SECCOMP_MODE_STRICT :
                     !killed||logged!=1||state.seccomp.mode!=SECCOMP_MODE_DEAD)return 1;
        state.seccomp.mode=SECCOMP_MODE_DISABLED;logged=0;
        if(setjmp(failure))return 2;
        secure_computing_strict(nr);
        if(logged||state.seccomp.mode!=SECCOMP_MODE_DISABLED)return 3;
    }
    return 0;
}
""".replace("POLICY", policy)
with tempfile.TemporaryDirectory(prefix="seccomp-strict-model-") as tmp:
    path = Path(tmp)
    for folder in ("asm", "asm-generic", "linux", "bits"):
        (path / folder).mkdir()
    (path / "asm-generic/seccomp.h").write_text(generic)
    # Read syscall constants from the pinned kernel, not host architecture.
    constants = "\n".join(
        line
        for line in numbers.splitlines()
        if re.match(r"#define\s+__NR_(?:read|write|exit|syscalls)\s+\d+\s*$", line)
    )
    (path / "linux/unistd.h").write_text(constants + "\n")
    test = path / "policy.c"
    test.write_text(driver)
    for cc in ("gcc", "clang"):
        for bad in (False, True):
            header = arch if not bad else arch.replace("(-1)", "172")
            assert not bad or header != arch
            (path / "asm/seccomp.h").write_text(header)
            binary = path / "policy"
            subprocess.run(
                [
                    cc,
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    tmp,
                    str(test),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            result = subprocess.run([str(binary)], timeout=10)
            assert result.returncode == (1 if bad else 0), (cc, bad, result.returncode)
    # Workload compilation only: never execute native seccomp/fork policy here.
    workload = ROOT / "sources/distro/distro/seccomp-strict/runtime.c"
    for cc in ("gcc", "clang"):
        subprocess.run(
            [
                cc,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-c",
                str(workload),
                "-o",
                str(path / "native.o"),
            ],
            check=True,
        )
    uapi = source("include/uapi/linux/seccomp.h")
    (path / "linux/seccomp.h").write_text(
        "\n".join(
            line
            for line in uapi.splitlines()
            if re.match(r"#define\s+SECCOMP_(?:SET_MODE_\w+|MODE_\w+)\s+\d+\b", line)
        )
        + "\n"
    )
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.run(
        ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
        input=templates,
        text=True,
        capture_output=True,
        check=True,
    )
    (path / "bits/alltypes.h").write_text(generated.stdout)
    musl_numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(
        musl_numbers + musl_numbers.replace("__NR_", "SYS_")
    )
    unistd = (MUSL / "include/unistd.h").read_text()
    gate = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
    assert gate in unistd
    (path / "unistd.h").write_text(
        unistd.replace(gate, "pid_t fork(void);\npid_t _Fork(void);")
    )
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output(
            [cc, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            flags = [
                cc,
                f"--target=wasm{bits}",
                "-nostdinc",
                "-I",
                tmp,
                "-I",
                str(MUSL / "arch/wasm32"),
                "-I",
                str(MUSL / "arch/generic"),
                "-I",
                str(MUSL / "src/include"),
                "-I",
                str(MUSL / "src/internal"),
                "-I",
                str(MUSL / "include"),
                "-isystem",
                resource + "/include",
            ]
            subprocess.run(
                [*flags, "-Wall", "-Wextra", "-Werror", "-fsyntax-only", str(workload)],
                check=True,
            )
            subprocess.run(
                [
                    *flags,
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    "-o",
                    "/dev/null",
                    str(workload),
                ],
                check=True,
            )
print(
    "exact strict allowlist/state/kill models and rejection control passed; workload frontends/analysis passed; no native seccomp execution"
)
