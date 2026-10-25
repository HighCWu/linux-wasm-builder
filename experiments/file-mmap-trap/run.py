#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual copy-body/bridge cleanup regression, not full-kernel target acceptance."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--expect-leak", action="store_true", help="bypass the abort hook as a negative control")
parser.add_argument("--old-kernel", action="store_true", help="hide the cleanup export and require normal refusal")
args = parser.parse_args()
if args.old_kernel and args.expect_leak:
    parser.error("old-kernel refusal and cleanup bypass are separate controls")
root = Path(__file__).resolve().parents[2]
directory = Path(__file__).resolve().parent
source = Path(os.environ.get("WASM_MMAP_COPY_SOURCE",
                            root / "sources/linux/arch/wasm/kernel/mmap_file.c")).read_text()
source = re.sub(r"^#include[^\n]*\n", "", source, flags=re.M)
if args.old_kernel:
    marker = '__attribute__((export_name("abort_file_mmap_v1")))'
    assert source.count(marker) == 1
    source = source.replace(marker, "")
shim = (directory / "shim.c").read_text()
marker = "/* The runner inserts the actual GPL kernel function body here, unchanged. */"
assert shim.count(marker) == 1
compiler = os.environ.get("CC", "clang")
failed = False
with tempfile.TemporaryDirectory(prefix="file-mmap-trap-") as tmp:
    unit, binary = Path(tmp) / "kernel.c", Path(tmp) / "kernel.wasm"
    unit.write_text(shim.replace(marker, source))
    for bits in (32, 64):
        subprocess.run([compiler, f"--target=wasm{bits}", "-O2", "-nostdlib", "-ffreestanding",
                        "-DCONFIG_WASM_MMAP_COPY_TEST=1", "-Wl,--no-entry", "-Wl,--export-memory",
                        "-Wl,--export=__stack_pointer", "-Wl,--export=run", "-Wl,--export=resource",
                        "-Wl,--export=exit_cleanup",
                        str(unit), "-o", str(binary)], check=True)
        result = subprocess.run(["node", "--input-type=module", "-e", """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const root = pathToFileURL(process.argv[2] + '/');
const {FileMmapCopy} = await import(new URL('sources/distro/packages/kernel/src/file-mmap-copy.ts',root));
const {call_kernel_entry} = await import(new URL('sources/distro/packages/kernel/src/signal-stack.ts',root));
const wide = process.argv[3] === '64', width = wide ? 'i64' : 'i32';
const word = n => wide ? BigInt(n) : n;
const value = wide ? 0x7e : 0x7f;
const name = text => [text.length,...new TextEncoder().encode(text)];
const section = (id,bytes) => [id,bytes.length,...bytes];
const initializer = trap => {
  const body = trap ? [0,0,0x0b] : [0,0x20,0,0x0b];
  return new WebAssembly.Instance(new WebAssembly.Module(new Uint8Array([
    0,97,115,109,1,0,0,0,
    ...section(1,[1,0x60,2,value,value,1,value]),
    ...section(3,[1,0]),
    ...section(7,[1,...name('__wasm_mmap_init_v1'),0,0]),
    ...section(10,[1,body.length,...body])
  ]))).exports;
};
let bridge, selected = initializer(false);
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {bridge: {
  map: (...args) => bridge.map(selected,...args,() => {
    if (process.argv[4] !== 'true') instance.exports.abort_file_mmap_v1();
  })
}});
bridge = new FileMmapCopy(instance.exports.memory,width,() => instance.exports);
const call = () => call_kernel_entry(instance.exports,width,() => instance.exports.run());
const state = () => [0,1,2,3,4].map(i => Number(instance.exports.resource(i)));
if (process.argv[5] === 'true') {
  assert.equal(instance.exports.abort_file_mmap_v1,undefined);
  selected = {__wasm_mmap_init_v1: () => assert.fail('unsupported kernel must not invoke user allocator')};
  assert.equal(bridge.capabilities(selected),0);
  assert.equal(call(),word(-95));
  assert.deepEqual(state(),[0,0,0,0,0],'normal refusal must release actual C callback resources');
  console.log(`wasm${process.argv[3]} missing cleanup export: normal EOPNOTSUPP, no user allocator and all C resources zero`);
  process.exit(0);
}
assert.equal(call(),word(65536));
assert.deepEqual(state(),[0,0,0,0,0],'normal return must clean actual C resources');
selected = {__wasm_mmap_init_v1: () => word(-12)};
assert.equal(call(),word(-12));
assert.deepEqual(state(),[0,0,0,0,0],'ordinary errno must also clean actual C resources');
selected = initializer(true);
const stack = instance.exports.__stack_pointer.value;
assert.throws(call,WebAssembly.RuntimeError);
assert.equal(instance.exports.__stack_pointer.value,stack,'kernel stack restoration alone is insufficient');
assert.equal(bridge.copy(instance.exports.memory,word(0),word(0)),-1,'JS lease must be revoked');
const resources = state();
console.log(`wasm${process.argv[3]} after user trap: requests=${resources[0]} staging=${resources[1]} allocations=${resources[2]} reserved=${resources[3]} pins=${resources[4]}`);
assert.deepEqual(resources,process.argv[4] === 'true' ? [1,1,2,131072,1] : [0,0,0,0,0],
  'revoking a JS lease is not sufficient: actual C cleanup must also run');
instance.exports.exit_cleanup();
instance.exports.exit_cleanup();
assert.deepEqual(state(),[0,0,0,0,0],'exit hook must drain once without double release');
selected = initializer(false);
assert.equal(call(),word(65536));
assert.deepEqual(state(),[0,0,0,0,0],'later allocation must recover');
""", str(binary), str(root), str(bits), str(args.expect_leak).lower(), str(args.old_kernel).lower()])
        failed |= result.returncode != 0
if failed:
    sys.exit("file mmap cleanup requirement failed (both pointer widths were checked)")
