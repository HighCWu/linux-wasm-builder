#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact futex repair body and old-path trap control in tiny Wasm, not Linux runtime acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "sources/linux/kernel/futex/core.c").read_text()
begin = source.index("int fault_in_user_writeable(")
body = source[begin:source.index("\n}\n", begin) + 3]
old = body.replace("\tif (IS_ENABLED(CONFIG_WASM))\n\t\treturn -EFAULT;\n", "")
assert old != body
prefix = r'''
typedef unsigned int u32;
#define __user
#define NULL ((void *)0)
#define EFAULT 14
#define FAULT_FLAG_WRITE 1
#define IS_ENABLED(x) (x)
struct mm_struct { int unused; };
static struct mm_struct mm;
static struct { struct mm_struct *mm; } task = {&mm};
#define current (&task)
static int locks, unlocks, repairs, result;
static void mmap_read_lock(struct mm_struct *p) { if (p != &mm) __builtin_trap(); locks++; }
static void mmap_read_unlock(struct mm_struct *p) { if (p != &mm) __builtin_trap(); unlocks++; }
static int fixup_user_fault(struct mm_struct *p, unsigned long address, int flags, void *unused) {
    if (p != &mm || address != 0x100000UL || flags != FAULT_FLAG_WRITE || unused) __builtin_trap();
    repairs++;
#if CONFIG_MMU
    return result;
#else
    __builtin_trap(); /* Actual generic NOMMU stub calls BUG(). */
#endif
}
'''
suffix = r'''
int run(int value) {
    locks = unlocks = repairs = 0;
    result = value;
    return fault_in_user_writeable((u32 *)0x100000UL);
}
int lock_count(void) { return locks; }
int unlock_count(void) { return unlocks; }
int repair_count(void) { return repairs; }
'''
with tempfile.TemporaryDirectory(prefix="futex-fault-") as tmp:
    musl = ROOT / "sources/musl"
    include = Path(tmp) / "include"
    (include / "bits").mkdir(parents=True)
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (include / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
    (include / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    workload = ROOT / "sources/distro/distro/toolchain-smoke/user-access.c"
    unit, binary = Path(tmp) / "fault.c", Path(tmp) / "fault.wasm"
    for bits in (32, 64):
        frontend = [os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}", "-nostdinc",
                    "-I", str(include), "-I", str(musl / "arch/wasm32"),
                    "-I", str(musl / "arch/generic"), "-I", str(musl / "include")]
        subprocess.run([*frontend, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(workload)], check=True)
        subprocess.run([*frontend, "--analyze", "-Xanalyzer", "-analyzer-werror", str(workload),
                        "-o", "/dev/null"], check=True)
        for wasm, mmu, implementation, trap in ((1, 0, body, False), (1, 0, old, True),
                                               (0, 1, body, False), (0, 0, body, True)):
            unit.write_text(prefix + implementation + suffix)
            subprocess.run([os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}", "-O2",
                            f"-DCONFIG_WASM={wasm}", f"-DCONFIG_MMU={mmu}", "-nostdlib", "-ffreestanding",
                            "-Wl,--no-entry", *["-Wl,--export=" + name for name in
                            ("run", "lock_count", "unlock_count", "repair_count")], str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance:{exports:e}} = await WebAssembly.instantiate(readFileSync(process.argv[1]));
const trap = process.argv[2] === 'True', wasm = process.argv[3] === '1';
for (const input of [-14,0,1]) {
  if (trap) assert.throws(() => e.run(input), WebAssembly.RuntimeError);
  else assert.equal(e.run(input), wasm ? -14 : Math.min(input,0));
  assert.equal(e.lock_count(), wasm && !trap ? 0 : 1);
  assert.equal(e.unlock_count(), trap || wasm ? 0 : 1);
  assert.equal(e.repair_count(), wasm && !trap ? 0 : 1);
}
''', str(binary), str(trap), str(wasm)], check=True)
        print(f"wasm{bits}: EFAULT without page repair, old NOMMU trap, unchanged MMU lock/result path passed")
