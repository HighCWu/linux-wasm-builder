#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual remote request-admission prefix; not mailbox/scheduler or target ptrace acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1] if len(sys.argv) > 1 else root / "sources/linux/arch/wasm/kernel/remote_vm.c").read_text()
function = source.index("int wasm_access_remote_vm(")
start = source.index("\tif (len <= 0", function)
prefix = source[start:source.index("\n\trequest =", start)]
shim = r"""
#define PAGE_SIZE 65536UL
#define min_t(t,a,b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define __user
#if __SIZEOF_POINTER__ == 8
#define TASK_SIZE (1UL << 34)
#else
#define TASK_SIZE 0xffffffffUL
#endif
static int access_ok(const void *p, unsigned long size) {
    unsigned long addr = (unsigned long)p;
    return size <= TASK_SIZE && addr <= TASK_SIZE - size;
}
int bounded(unsigned long addr, int len) {
"""
suffix = "\nreturn len;\n}\n"
old = prefix.replace("\tif (!access_ok", "\tlen = min_t(unsigned long, len, PAGE_SIZE - (addr % PAGE_SIZE));\n\tif (!access_ok")
assert old != prefix
cc = os.environ.get("CC", "clang")
with tempfile.TemporaryDirectory(prefix="remote-vm-range-") as tmp:
    path = Path(tmp)
    unit, binary = path / "range.c", path / "range.wasm"
    for bits in (32, 64):
        for label, implementation in (("normal", prefix), ("page-cut", old)):
            unit.write_text(shim + implementation + suffix)
            subprocess.run([cc, f"--target=wasm{bits}", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-nostdlib", "-ffreestanding", "-Wl,--no-entry", "-Wl,--export=bounded",
                            str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const wide = process.argv[2] === '64';
const word = wide ? 8 : 4;
const p = n => wide ? BigInt(n) : Number(n)|0;
const limit = wide ? 1n<<34n : 0xffffffffn;
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]));
const bounded = (addr,len) => instance.exports.bounded(p(addr),len);
if (process.argv[3] === 'page-cut') {
  assert.equal(bounded(65535,word),1,'old page cut loses the rest of a valid machine word');
} else {
  assert.equal(bounded(65535,word),word);
  assert.equal(bounded(65533,word),word);
  assert.equal(bounded(65535,65536),65536,'cap payload without forcing page alignment');
}
assert.equal(bounded(65536,0x7fffffff),65536);
assert.equal(bounded(limit-2n,word),2,'retain valid prefix at TASK_SIZE');
assert.equal(bounded(limit,word),0);
if (wide) assert.equal(bounded(limit+1n,word),0);
assert.equal(bounded(-1,word),0);
assert.equal(bounded(65535,0),0);
assert.equal(bounded(65535,-1),0);
assert.equal(bounded(wide ? 0x100000100n : 0x80000100,word),word);
""", str(binary), str(bits), label], check=True)
        print(f"wasm{bits}: full cross-page word, bounded payload, high offsets, TASK_SIZE prefix and old page-cut control passed")
