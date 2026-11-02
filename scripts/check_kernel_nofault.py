#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute the actual Wasm kernel nofault macros in small linear memories."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("header", type=Path)
parser.add_argument("--clang", default="clang-18")
parser.add_argument("--node", default="node")
args = parser.parse_args()
header = args.header.read_text()
body = header.split("/* WASM_KERNEL_NOFAULT_BEGIN */", 1)[1].split(
    "/* WASM_KERNEL_NOFAULT_END */", 1
)[0]

# The GPL implementation is read from the selected kernel, not copied into this
# MIT harness. Its temporary executable is an architecture test, never an SDK.
SHIM = r"""
typedef unsigned int u32;
static u32 get32(const void *p) { u32 value; __builtin_memcpy(&value,p,4); return value; }
static void put32(u32 value, void *p) { __builtin_memcpy(p,&value,4); }
#define get_unaligned(p) get32(p)
#define put_unaligned(value,p) put32(value,p)
"""
ENTRY = r"""
int read32(unsigned long address) {
 u32 value=0x13579;
 __get_kernel_nofault(&value,(const void *)address,u32,fault);
 return (int)value;
fault: return -14;
}
int write32(unsigned long address, u32 value) {
 __put_kernel_nofault((void *)address,&value,u32,fault);
 return 0;
fault: return -14;
}
int range(unsigned long address,unsigned long size) {
 return wasm_kernel_nofault_range((const void *)address,size);
}
int read_once(unsigned long address) {
 u32 value; unsigned calls=0;
 __get_kernel_nofault(&value,(++calls,(void *)address),u32,fault);
 return calls==1 && value==42;
fault:return -14;
}
int write_once(unsigned long address) {
 u32 value=43; unsigned calls=0;
 __put_kernel_nofault((++calls,(void *)address),&value,u32,fault);
 return calls==1;
fault:return -14;
}
"""
RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
for(const width of [32,64]) {
 const word=n=>width===64?BigInt(n):n;
 const memory=new WebAssembly.Memory({initial:word(1),maximum:word(4),shared:true,address:width===64?'i64':'i32'});
 const {instance}=await WebAssembly.instantiate(readFileSync(`${process.argv[2]}/${width}.wasm`),{env:{memory}});
 const e=instance.exports;
 new DataView(memory.buffer).setUint32(1025,42,true);
 assert.equal(e.read32(word(1025)),42); assert.equal(e.read_once(word(1025)),1);
 assert.equal(e.write_once(word(1025)),1); assert.equal(e.read32(word(1025)),43);
 assert.equal(e.write32(word(65532),99),0); assert.equal(e.read32(word(65532)),99);
 const before=new Uint8Array(memory.buffer).slice();
 for(const address of [65536,0,65533,-1]) {
  assert.equal(e.read32(word(address)),-14,'bad reads return EFAULT, never a Wasm trap');
  assert.equal(e.write32(word(address),77),-14,'bad writes return EFAULT');
 }
 assert.deepEqual(new Uint8Array(memory.buffer),before,'failed stores preserve memory');
 assert.equal(e.range(word(65535),word(1)),1);
 assert.equal(e.range(word(65535),word(2)),0);
 assert.equal(e.range(word(-4),word(8)),0,'wrapped intervals reject');
 assert.equal(e.range(word(1024),word(0)),0);
 memory.grow(word(1));
 assert.equal(e.write32(word(65536),123),0,'newly committed capacity is visible');
 assert.equal(e.read32(word(65536)),123);
 const limits=(await WebAssembly.instantiate(readFileSync(`${process.argv[2]}/bounds${width}.wasm`),{env:{memory}})).instance.exports;
 limits.pages(width===64?1n<<48n:65536);
 assert.equal(limits.range(word(-1),word(1)),1,'full address-space last byte must not wrap its capacity');
 assert.equal(limits.range(word(-1),word(2)),0,'full address-space wrap rejects');
 console.log(`kernel nofault wasm${width}: actual macros, unaligned access, boundaries, overflow, no store side effects and growth pass; not a Linux boot`);
}
"""
with tempfile.TemporaryDirectory(prefix="wasm-kernel-nofault-") as temporary:
    path = Path(temporary)
    source = path / "check.c"
    source.write_text(SHIM + body + ENTRY)
    for width in (32, 64):
        flags = [
            args.clang,
            f"--target=wasm{width}",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-matomics",
            "-mbulk-memory",
            "-nostdlib",
            "-Wl,--no-entry,--import-memory,--export-all,--max-memory=262144,--shared-memory",
            "-Wl,-z,stack-size=0",
        ]
        subprocess.run(
            [*flags, str(source), "-o", str(path / f"{width}.wasm")],
            check=True,
        )
        # Arithmetic-only capacity model: no huge host allocation or reads.
        bounds = path / "bounds.c"
        bounds.write_text(
            "static unsigned long capacity;\n#define __builtin_wasm_memory_size(index) capacity\n"
            + body
            + "\nvoid pages(unsigned long n){capacity=n;}\n"
            + "int range(unsigned long a,unsigned long n){return wasm_kernel_nofault_range((void*)a,n);}\n"
        )
        subprocess.run(
            [*flags, str(bounds), "-o", str(path / f"bounds{width}.wasm")], check=True
        )
    runner = path / "check.mjs"
    runner.write_text(RUNNER)
    subprocess.run([args.node, str(runner), str(path)], check=True)
print(json.dumps({"kernelHeader": str(args.header), "widths": [32, 64]}))
