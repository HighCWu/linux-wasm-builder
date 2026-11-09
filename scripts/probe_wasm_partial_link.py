#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Probe partial-linking C objects into an executable dynamic Wasm module."""

from pathlib import Path
import argparse
import shutil
import subprocess
import tempfile


MAIN_C = r"""
extern int local_helper(int value);
extern int external_provider(int value);

int entry(int value)
{
    return external_provider(local_helper(value));
}
"""

HELPER_C = r"""
int local_helper(int value)
{
    return value + 1;
}
"""

NODE_RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const bits = Number(process.argv[3]);
const address64 = bits === 64;
const module = new WebAssembly.Module(readFileSync(process.argv[2]));
const imports = WebAssembly.Module.imports(module);
const importNames = imports.map(entry=>`${entry.module}.${entry.name}:${entry.kind}`).sort();
const expectedImports = [
  'env.memory:memory',
  'env.__memory_base:global',
  'env.__table_base:global',
  'env.external_provider:function',
];
if(imports.some(entry=>entry.module==='env'&&entry.name==='__table_base32')){
  assert.equal(address64,true,'32-bit table base is only expected for the wasm64 profile');
  expectedImports.push('env.__table_base32:global');
}
expectedImports.sort();
assert.deepEqual(importNames, expectedImports,
  'partial link resolves local_helper but preserves external_provider as the only function import');
assert.deepEqual(WebAssembly.Module.exports(module).filter(entry=>entry.name==='entry'),
  [{name:'entry',kind:'function'}]);
const zero = address64?0n:0;
const env = {
  external_provider(value) { return value + 39; },
  memory: address64
    ? new WebAssembly.Memory({initial:2n,maximum:16n,address:'i64'})
    : new WebAssembly.Memory({initial:2,maximum:16}),
  __memory_base: new WebAssembly.Global({value:address64?'i64':'i32'},zero),
  __table_base: new WebAssembly.Global({value:address64?'i64':'i32'},zero),
  ...(address64?{__table_base32:new WebAssembly.Global({value:'i32'},0)}:{}),
};
const instance = new WebAssembly.Instance(module, {
  env,
});
assert.equal(instance.exports.entry(2), 42);
console.log(`Wasm${bits} partial link reference (not patched SDK/Linux acceptance): local helper resolved, external provider imported, entry returns 42 pass`);
"""

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--clang", default="clang", help="Clang C driver")
parser.add_argument("--node", default="node", help="Node.js Wasm engine")
args = parser.parse_args()


def resolve(program: str, label: str) -> str:
    path = shutil.which(program)
    if path is None:
        raise SystemExit(f"error: {label} executable not found: {program}")
    return path


clang = resolve(args.clang, "Clang")
node = resolve(args.node, "Node.js")

with tempfile.TemporaryDirectory(prefix="wasm-partial-link-probe-") as temporary:
    directory = Path(temporary)
    main_source = directory / "main.c"
    helper_source = directory / "helper.c"
    main_source.write_text(MAIN_C)
    helper_source.write_text(HELPER_C)
    runner = directory / "validate.mjs"
    runner.write_text(NODE_RUNNER)

    direct_failure = None
    for bits in (32, 64):
        main_object = directory / f"main{bits}.o"
        helper_object = directory / f"helper{bits}.o"
        merged_object = directory / f"partial{bits}.o"
        module = directory / f"partial{bits}.so"
        for source, output in (
            (main_source, main_object),
            (helper_source, helper_object),
        ):
            subprocess.run(
                [
                    clang,
                    f"--target=wasm{bits}-unknown-unknown",
                    "-nostdlib",
                    "-O2",
                    "-fPIC",
                    "-c",
                    str(source),
                    "-o",
                    str(output),
                ],
                check=True,
                timeout=30,
            )

        direct_command = [
            clang,
            f"--target=wasm{bits}-unknown-unknown",
            "-r",
            "-nostdlib",
            str(main_object),
            str(helper_object),
            "-o",
            str(merged_object),
        ]
        direct = subprocess.run(
            direct_command, check=False, text=True, capture_output=True, timeout=30
        )
        if direct.returncode != 0:
            fallback_command = [
                clang,
                f"--target=wasm{bits}-unknown-unknown",
                "-nostdlib",
                "-Wl,-r",
                str(main_object),
                str(helper_object),
                "-o",
                str(merged_object),
            ]
            fallback = subprocess.run(
                fallback_command,
                check=False,
                text=True,
                capture_output=True,
                timeout=30,
            )
            if fallback.returncode != 0:
                raise SystemExit(
                    f"error: both clang -r and explicit -Wl,-r failed for wasm{bits}\n"
                    f"clang -r:\n{direct.stdout}{direct.stderr}\n"
                    f"-Wl,-r:\n{fallback.stdout}{fallback.stderr}"
                )
            direct_failure = (
                direct_failure or direct.stderr.strip() or direct.stdout.strip()
            )
            print(
                f"Wasm{bits} partial link used explicit -Wl,-r: underlying LLD reference only; "
                "this does not verify Clang driver's -r forwarding",
                flush=True,
            )

        subprocess.run(
            [
                clang,
                f"--target=wasm{bits}-unknown-unknown",
                "-nostdlib",
                "-O2",
                "-fPIC",
                "-shared",
                "-Wl,--no-entry,--unresolved-symbols=import-dynamic,--export=entry",
                str(merged_object),
                "-o",
                str(module),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run(
            [node, str(runner), str(module), str(bits)],
            check=True,
            timeout=30,
        )

    if direct_failure:
        print(f"Clang driver -r fallback reason: {direct_failure}")
