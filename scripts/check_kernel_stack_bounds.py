#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute actual Wasm kernel stack macros without allocating high-address memory."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
processor = Path(os.environ.get("WASM_PROCESSOR_SOURCE", ROOT / "sources/linux/arch/wasm/include/asm/processor.h")).read_text()
thread = Path(os.environ.get("WASM_THREAD_INFO_SOURCE", ROOT / "sources/linux/arch/wasm/include/asm/thread_info.h")).read_text()
bounds = re.search(r"^#define on_thread_stack\(\) \\\n[^\n]+", processor, re.M).group(0)
sizes = "\n".join(re.findall(r"^#define THREAD_(?:SIZE_ORDER|SIZE|SHIFT) .+$", thread, re.M))
old_bounds = "#define on_thread_stack() \\\n\t((unsigned long)(current->stack - get_stack_pointer()) < THREAD_SIZE)"
old_sizes = sizes.replace("PAGE_SHIFT + THREAD_SIZE_ORDER", "PAGE_SHIFT << THREAD_SIZE_ORDER")
assert old_bounds != bounds and old_sizes != sizes
prefix = r'''
#define PAGE_SHIFT 16
#define PAGE_SIZE (1UL << PAGE_SHIFT)
struct task { void *stack; };
static struct task task;
static void *sp;
#define current (&task)
static inline void *get_stack_pointer(void) { return sp; }
'''
suffix = r'''
int check(unsigned long base,unsigned long pointer) {
    task.stack=(void *)base; sp=(void *)pointer;
    return on_thread_stack();
}
unsigned int shift(void) { return THREAD_SHIFT; }
unsigned long size(void) { return THREAD_SIZE; }
'''
compilers = os.environ.get("WASM_STACK_COMPILERS", "clang").split()
assert compilers, "at least one Wasm compiler must execute the stack model"
with tempfile.TemporaryDirectory(prefix="wasm-kstack-bounds-") as tmp:
    unit, binary = Path(tmp) / "stack.c", Path(tmp) / "stack.wasm"
    for cc in compilers:
        for bits in (32, 64):
            for variant in ("fixed", "old-bounds", "old-shift"):
                chosen_sizes = old_sizes if variant == "old-shift" else sizes
                chosen_bounds = old_bounds if variant == "old-bounds" else bounds
                invariant = "" if variant == "old-shift" else '\n_Static_assert((1UL << THREAD_SHIFT) == THREAD_SIZE,"stack shift/size invariant");\n'
                unit.write_text(prefix + chosen_sizes + "\n" + chosen_bounds + invariant + suffix)
                flags = [cc, f"--target=wasm{bits}", "-ffreestanding", "-Wall", "-Wextra", "-Werror"]
                subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", str(unit), "-o", "/dev/null"], check=True)
                subprocess.run([*flags, "-O2", "-nostdlib", "-Wl,--no-entry", "-Wl,--export=check",
                                "-Wl,--export=shift", "-Wl,--export=size", str(unit), "-o", str(binary)], check=True)
                subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance:{exports:api}}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
const wide=process.argv[2]==='64', mode=process.argv[3];
const p=n=>wide ? BigInt(n) : Number(n);
const size=BigInt(api.size());
assert.equal(size,131072n);
if (mode==='old-shift') {
  assert.equal(api.shift(),32);
  assert.notEqual(1n<<BigInt(api.shift()),size,'old shift does not describe allocated stack');
  process.exit(0);
}
assert.equal(api.shift(),17);
const bases=wide ? [0x200000n,0x80040000n,0x100020000n] : [0x200000n,0x80040000n,0xfffc0000n];
for (const base of bases) {
  assert.equal(api.check(p(base),p(base)),1);
  for (const offset of [1n,size/2n,size-1n])
    assert.equal(api.check(p(base),p(base+offset)),mode==='old-bounds'?0:1,'interior stack pointer');
  assert.equal(api.check(p(base),p(base-1n)),mode==='old-bounds'?1:0,'address immediately below allocation');
  for (const pointer of [0n,base-size-1n,base+size,base+size+1n])
    assert.equal(api.check(p(base),p(pointer)),0,'outside allocation');
}
''', str(binary), str(bits), variant], check=True)
            print(f"{cc} wasm{bits}: real stack interval/shift, high addresses and both old controls passed")
