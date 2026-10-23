#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual clone entry in tiny Wasm modules; not Linux slab/Worker acceptance."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1] if len(sys.argv) > 1 else
              root / "sources/linux/arch/wasm/kernel/fork.c").read_text()
record = re.search(r"struct clone_fn \{.*?\n\};", source, re.S).group()
start = source.index("int wasm_call_clone_fn(")
body = source[start:source.index("\n}\n", start) + 3]
prefix = """
#define __user
typedef __UINTPTR_TYPE__ uintptr_t;
""" + record + """
static struct clone_fn metadata;
static volatile int live, released;
static void kfree(void *p) {
    if (p != &metadata || !live) __builtin_trap();
    metadata.fn = metadata.arg = (void *)0;
    live = 0;
    released++;
}
__attribute__((import_module("bridge"), import_name("switch_entry")))
extern void wasm_user_switch_entry(uintptr_t, uintptr_t);
"""
suffix = """
int run(void) {
    if (live) __builtin_trap();
#if __SIZEOF_POINTER__ == 8
    metadata.fn = (void *)(uintptr_t)0x100000100ULL;
    metadata.arg = (void *)(uintptr_t)0x200000020ULL;
#else
    metadata.fn = (void *)(uintptr_t)0x80000100UL;
    metadata.arg = (void *)(uintptr_t)0xffff0020UL;
#endif
    live = 1;
    return wasm_call_clone_fn(&metadata);
}
int owned(void) { return live; }
int releases(void) { return released; }
"""
late = body.replace("\tkfree(clone_fn);\n", "").replace(
    "\treturn 0;", "\tkfree(clone_fn);\n\treturn 0;")
assert late != body
compiler = os.environ.get("CC", "clang")
with tempfile.TemporaryDirectory(prefix="clone-entry-") as tmp:
    path = Path(tmp)
    unit, binary = path / "entry.c", path / "entry.wasm"
    for bits in (32, 64):
        for label, implementation in (("normal", body), ("late-release", late)):
            unit.write_text(prefix + implementation + suffix)
            subprocess.run([compiler, f"--target=wasm{bits}", "-O2", "-nostdlib", "-ffreestanding",
                            "-Wl,--no-entry", "-Wl,--export=run", "-Wl,--export=owned",
                            "-Wl,--export=releases", str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const wide = process.argv[2] === '64';
const fn = wide ? 0x100000100n : (0x80000100|0);
const arg = wide ? 0x200000020n : (0xffff0020|0);
let mode = 'normal', calls = 0, instance;
const fault = new WebAssembly.RuntimeError('continuation restore failed');
({instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {bridge: {
  switch_entry: (actualFn,actualArg) => {
    calls++;
    assert.equal(actualFn,fn,'function word must survive freeing its record');
    assert.equal(actualArg,arg,'argument word must survive freeing its record');
    assert.equal(instance.exports.owned(),0,'handoff must not retain bootstrap allocation');
    if (mode === 'trap') throw fault;
  }
}}));
if (process.argv[3] === 'late-release') {
  assert.throws(() => instance.exports.run(), /handoff must not retain/);
  assert.equal(instance.exports.owned(),1,'old order skips cleanup on a non-local exit');
} else {
  assert.equal(instance.exports.run(),0);
  mode = 'trap';
  assert.throws(() => instance.exports.run(), error => error === fault);
  assert.equal(instance.exports.owned(),0);
  assert.equal(instance.exports.releases(),2);
  mode = 'normal';
  assert.equal(instance.exports.run(),0);
  assert.equal(instance.exports.releases(),3);
  assert.equal(calls,3);
}
""", str(binary), str(bits), label], check=True)
        print(f"wasm{bits}: clone metadata release, raw scalar identity and late-release control passed")
