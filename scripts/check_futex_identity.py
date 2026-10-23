#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact private-key branch in tiny Wasm modules, not scheduler/syscall acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1] if len(sys.argv) > 1 else root / "sources/linux/kernel/futex/core.c").read_text()
start = source.index("\tif (!fshared) {", source.index("int get_futex_key("))
branch = source[start:source.index("\nagain:", start)]
prefix = r"""
#define NULL ((void *)0)
#define IS_ENABLED(x) (x)
typedef __UINTPTR_TYPE__ uintptr_t;
struct mm_struct { int unused; };
union futex_key { struct { struct mm_struct *mm; unsigned long address; } private; };
static int fill(struct mm_struct *mm, unsigned long address, union futex_key *key) {
    int fshared = 0;
"""
suffix = r"""
    __builtin_trap();
}
static int equal(union futex_key a, union futex_key b) {
    return a.private.mm == b.private.mm && a.private.address == b.private.address;
}
int check(void) {
    struct mm_struct *one = (void *)(uintptr_t)0x10000;
    struct mm_struct *two = (void *)(uintptr_t)0x20000;
    union futex_key a, b, c, d;
#if __SIZEOF_POINTER__ == 8
    unsigned long address = 0x100030000UL;
#else
    unsigned long address = 0x80030000UL;
#endif
    if (fill(one,address,&a) || fill(two,address,&b) ||
        fill(one,address,&c) || fill(one,address+65536,&d)) __builtin_trap();
    return (a.private.mm == one) | (equal(a,c) << 1) |
           ((!equal(a,b)) << 2) | ((!equal(a,d)) << 3);
}
"""
cc = os.environ.get("CC", "clang")
with tempfile.TemporaryDirectory(prefix="futex-identity-") as tmp:
    path = Path(tmp)
    unit, binary = path / "key.c", path / "key.wasm"
    old = branch.replace(" || IS_ENABLED(CONFIG_WASM)", "")
    assert old != branch
    for bits in (32, 64):
        for mmu, wasm, implementation, expected in (
            (0, 1, branch, 15), (1, 0, branch, 15), (0, 0, branch, 10), (0, 1, old, 10),
        ):
            unit.write_text(prefix + implementation + suffix)
            subprocess.run([cc, f"--target=wasm{bits}", "-O2", "-Wall", "-Wextra", "-Werror",
                            f"-DCONFIG_MMU={mmu}", f"-DCONFIG_WASM={wasm}",
                            "-nostdlib", "-ffreestanding", "-Wl,--no-entry", "-Wl,--export=check",
                            str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]));
assert.equal(instance.exports.check(), Number(process.argv[2]));
""", str(binary), str(expected)], check=True)
        print(f"wasm{bits}: distinct mm identity, same-mm keys, high offsets, unchanged MMU/NOMMU and old-key control passed")
