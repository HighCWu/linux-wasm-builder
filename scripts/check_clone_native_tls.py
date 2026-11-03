#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual musl clone + C11 start bodies; modeled syscall transport, not Linux acceptance."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
thread = (MUSL / "src/thread/pthread_create.c").read_text()


def body(marker):
    source = thread[thread.index(marker) :]
    ending = "\n};\n" if marker.startswith("struct ") else "\n}\n"
    return source[: source.index(ending) + len(ending)]


fixture = (
    r"""
#define _GNU_SOURCE
#include "pthread_impl.h"
#include <sched.h>
hidden void __wasm_init_tls(void *);
static _Thread_local volatile unsigned value = 41;
__attribute__((import_module("probe"),import_name("exit"),noreturn))
void probe_exit(long);
_Noreturn void __pthread_exit(void *result) { probe_exit((long)result); }
"""
    + body("struct start_args {")
    + body("static int start_c11(")
    + r"""
static int application(void *arg) {
 if(value!=41) __builtin_trap();
 value=42;
 return (int)(long)arg;
}
__attribute__((export_name("launch"))) long launch(void *stack,void *native_tls) {
 struct start_args args={.start_func=(void *(*)(void *))application,
                         .start_arg=(void *)37,.wasm_tls=native_tls};
 return __clone(start_c11,stack,CLONE_VM|CLONE_THREAD, &args);
}
__attribute__((export_name("read_tls"))) unsigned read_tls(void) { return value; }
"""
)
runner = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const [file,bits,negative]=process.argv.slice(2),wide=bits==='64',word=n=>wide?BigInt(n):n;
const module=await WebAssembly.compile(readFileSync(file));
const memory=new WebAssembly.Memory({initial:word(8),maximum:word(16),shared:true,address:wide?'i64':'i32'});
let parent,child,exited=false,newborn=false;
const exit=Symbol('exit');
const imports={env:{memory},probe:{exit(status){assert.equal(Number(status),37);exited=true;throw exit;}},
 linux:{syscall(n,a,b,c){
  n=Number(n);
  if(n===178){ // Actual clone entry's first kernel return, before pthread start.
   newborn=true;
   assert.equal(child.exports.__tls_base.value,parent.exports.__tls_base.value);
   return word(2);
  }
  assert.equal(n,220);
  assert.equal(Number(c),0x10100);
  const table=child.exports.__indirect_function_table;
  let index;
  try { table.get(0n); index=BigInt(a); }
  catch(error){if(!(error instanceof TypeError))throw error; index=Number(a);}
  try {table.get(index)(b);assert.fail('child must exit');}
  catch(error){if(error!==exit)throw error;}
  return word(2);
 }}};
parent=await WebAssembly.instantiate(module,imports);
child=await WebAssembly.instantiate(module,imports);
parent.exports.__wasm_init_tls(word(4*65536));
assert.equal(parent.exports.read_tls(),41);
assert.equal(Number(parent.exports.launch(word(7*65536),word(5*65536))),2);
assert(exited&&newborn);
assert.equal(parent.exports.read_tls(),41,'pthread start must isolate native TLS before application');
assert.equal(child.exports.read_tls(),42);
assert.notEqual(child.exports.__tls_base.value,parent.exports.__tls_base.value);
assert.equal(negative,'normal');
"""
with tempfile.TemporaryDirectory(prefix="clone-native-tls-") as tmp:
    path = Path(tmp)
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.check_output(
        ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates, text=True
    )
    (path / "bits/alltypes.h").write_text(generated)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    (path / "run.mjs").write_text(runner)
    for cc in os.environ.get("WASM_CLONE_TLS_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            flags = [
                cc,
                f"--target=wasm{bits}",
                "-O2",
                "-matomics",
                "-mbulk-memory",
                "-nostdlib",
                "-I",
                tmp,
            ]
            for include in (
                "src/include",
                "arch/wasm32",
                "arch/generic",
                "src/internal",
                "include",
            ):
                flags += ["-I", str(MUSL / include)]
            for mode in ("normal", "missing-init"):
                source = (
                    fixture
                    if mode == "normal"
                    else fixture.replace(
                        "__wasm_init_tls(args->wasm_tls);",
                        "/* negative: no initialization */",
                    )
                )
                (path / "fixture.c").write_text(source)
                binary = path / "clone.wasm"
                subprocess.run(
                    flags
                    + [
                        str(MUSL / "src/thread/wasm32/clone.c"),
                        str(path / "fixture.c"),
                        "-Wl,--no-entry,--import-memory,--shared-memory,--max-memory=1048576,--export-table",
                        "-Wl,--export=__wasm_init_tls,--export=__tls_base",
                        "-o",
                        str(binary),
                    ],
                    check=True,
                )
                result = subprocess.run(
                    ["node", str(path / "run.mjs"), str(binary), str(bits), mode],
                    capture_output=True,
                    text=True,
                )
                if mode == "normal" and result.returncode:
                    raise RuntimeError(result.stderr)
                if mode != "normal" and (
                    not result.returncode
                    or "pthread start must isolate native TLS" not in result.stderr
                ):
                    raise RuntimeError(
                        "missing-init control failed for an unexpected reason: "
                        + result.stderr
                    )
                if mode == "normal":
                    for source_file in (
                        MUSL / "src/thread/wasm32/clone.c",
                        path / "fixture.c",
                    ):
                        subprocess.run(
                            flags
                            + [
                                "--analyze",
                                "-Xanalyzer",
                                "-analyzer-werror",
                                str(source_file),
                                "-o",
                                "/dev/null",
                            ],
                            check=True,
                        )
            print(
                f"{cc} wasm{bits}: actual clone/C11 start isolates native TLS; pre-start inherited window confirmed; missing-init control rejected; no Linux acceptance"
            )
