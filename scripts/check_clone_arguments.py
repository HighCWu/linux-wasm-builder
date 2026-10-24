#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Existing public clone argument positions; compile real musl, not a replacement wrapper."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
source = (MUSL / "src/linux/clone.c").read_text()
prefix, rest = source.split("#ifdef __wasm__\n", 1)
fixed, rest = rest.split("#else\n", 1)
old, suffix = rest.split("#endif\n", 1)
baseline = prefix + old + suffix
# Exact tombl-based 015d1ac3 file: the non-Wasm branch and the function set
# must remain unchanged. The new branch only restores Wasm argument routing.
assert (
    hashlib.sha256(baseline.encode()).hexdigest()
    == "9bc3842be515a26e5b451a11cd8c12e61c6605ecf40ea34b1dcbf6ecd2c19985"
)
assert "CLONE_CHILD_SETTID" in fixed
DRIVER = r"""
#define _GNU_SOURCE
#include <errno.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <unistd.h>
volatile int __abort_lock[1];
void __lock(volatile int *p) { (void)p; }
void __unlock(volatile int *p) { (void)p; }
void __post_Fork(int p) { (void)p; }
void __block_all_sigs(void *p) { (void)p; }
void __restore_sigs(void *p) { (void)p; }
static int error;
int *__errno_location(void) { return &error; }
int *___errno_location(void) { return &error; }
static int mode, calls;
static int callback(void *p) { (void)p; return 0; }
int __clone(int (*fn)(void *), void *stack, int flags, void *arg, ...) {
    if(fn!=callback||stack!=(void *)0x10000||arg!=(void *)0x20000)return -EIO;
    if(!(flags&CLONE_VM))return -EIO;
    va_list ap;va_start(ap,arg);
    pid_t *ptid=va_arg(ap,pid_t *);
    void *tls=va_arg(ap,void *);
    pid_t *ctid=va_arg(ap,pid_t *);
    va_end(ap);calls++;
    if(ptid!=(mode?(pid_t *)0x12345678:0))return -EIO;
    if(tls!=(mode>=2?(void *)0x23456780:0))return -EIO;
    if(ctid!=(mode>=2?(pid_t *)0x34567890:0))return -EIO;
    return 42;
}
int run(void) {
    int common=CLONE_VM|SIGCHLD;
    for(mode=0;mode<5;mode++) {
        int ret;
        if(!mode)ret=clone(callback,(void *)0x10000,common,(void *)0x20000);
        else if(mode==1)ret=clone(callback,(void *)0x10000,common|CLONE_PARENT_SETTID,
                                 (void *)0x20000,(pid_t *)0x12345678);
        else ret=clone(callback,(void *)0x10000,common|CLONE_CHILD_SETTID|
                       (mode==3?CLONE_PARENT_SETTID:mode==4?CLONE_PIDFD:0),
                       (void *)0x20000,(pid_t *)0x12345678,(void *)0x23456780,(pid_t *)0x34567890);
        if(ret!=42)return mode+1;
    }
    if(calls!=5)return 6;
    error=0;
    if(clone(callback,0,common,0)!=-1||error!=EINVAL||calls!=5)return 7;
    error=0;
    if(clone(callback,(void *)0x10000,common|CLONE_SETTLS,0)!=-1||error!=EINVAL||calls!=5)return 8;
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="clone-arguments-") as tmp:
    path = Path(tmp)
    workload = ROOT / "sources/distro/distro/clone-arguments/runtime.c"
    for cc in ("gcc", "clang"):
        binary = path / "reference"
        subprocess.run(
            [
                cc,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(workload),
                "-o",
                str(binary),
            ],
            check=True,
        )
        result = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count("::vm-test::pass") == 1
    (path / "bits").mkdir()
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
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    driver = path / "driver.c"
    driver.write_text(DRIVER)
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
                [*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(workload)],
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
            for bad in (False, True):
                actual = path / "clone.c"
                actual.write_text(baseline if bad else source)
                module = path / "clone.wasm"
                subprocess.run(
                    [
                        *flags,
                        "-O2",
                        "-nostdlib",
                        "-ffreestanding",
                        "-Wl,--no-entry,--export=run",
                        str(actual),
                        str(MUSL / "src/internal/syscall_ret.c"),
                        str(driver),
                        "-o",
                        str(module),
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        "node",
                        "--input-type=module",
                        "-e",
                        r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
assert.equal(instance.exports.run(),process.argv[2]==='bad'?3:0);
""",
                        str(module),
                        "bad" if bad else "fixed",
                    ],
                    check=True,
                )
print(
    "real musl public clone positional ABI passed both widths/compilers; old packed branch rejected; native reference and workload analysis passed"
)
