#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real mutable-global/TLS owner prototype; no Linux or libc coverage claim."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/cooperative-poll/execution.c"
runner = r"""
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const [file,bits]=process.argv.slice(2),wide=bits==='64',type=wide?'i64':'i32',word=n=>wide?BigInt(n):n;
const module=await WebAssembly.compile(readFileSync(file));
assert.deepEqual(WebAssembly.Module.imports(module).map(i=>`${i.module}.${i.name}:${i.kind}`).sort(),
 ['env.memory:memory','linux_user_poll_v2.checkpoint:function','linux_user_poll_v2.thread_pointer:global']);
const memory=new WebAssembly.Memory({initial:word(8),maximum:word(16),shared:true,address:type});
const create=async(id)=>{
 const state={calls:0,tp:new WebAssembly.Global({value:type,mutable:true},word(id))};
 state.instance=await WebAssembly.instantiate(module,{env:{memory},linux_user_poll_v2:{thread_pointer:state.tp,checkpoint(){state.calls++;return 0;}}});
 assert.equal(state.instance.exports.__wasm_user_poll_abi(),2);
 return state;
};
const parent=await create(0),child=await create(2);
const run=(state,n)=>{for(let i=0;i<n;i++)state.instance.exports.__sanitizer_cov_trace_pc();};
const size=Number(parent.instance.exports.__tls_size.value);assert(size>4&&size<=64);
parent.instance.exports.__wasm_init_tls(word(4*65536));
const bytes=()=>new Uint8Array(memory.buffer,4*65536,size).slice();
let saved=bytes();run(parent,10000);assert.deepEqual(bytes(),saved,'no TP: no TLS mutation');assert.equal(parent.calls,0);
parent.tp.value=word(1);run(parent,1);saved=bytes();
child.instance.exports.__tls_base.value=parent.instance.exports.__tls_base.value;
run(child,10000);assert.deepEqual(bytes(),saved,'inherited parent TLS must remain untouched');assert.equal(child.calls,0);
child.instance.exports.__wasm_init_tls(word(5*65536));run(child,4096);assert.equal(child.calls,1);
run(parent,4095);assert.equal(parent.calls,1,'child startup did not spend parent budget');
parent.tp.value=word(0);saved=bytes();run(parent,8192);assert.deepEqual(bytes(),saved);
parent.tp.value=word(1);run(parent,4096);assert.equal(parent.calls,2,'ready state resumes independently');
for(const descriptor of [{value:type,mutable:false},{value:wide?'i32':'i64',mutable:true}]){
 const wrong=new WebAssembly.Global(descriptor,descriptor.value==='i64'?0n:0);
 await assert.rejects(()=>WebAssembly.instantiate(module,{env:{memory},linux_user_poll_v2:{thread_pointer:wrong,checkpoint:()=>0}}),WebAssembly.LinkError);
}
"""
with tempfile.TemporaryDirectory(prefix="cooperative-poll-owner-") as tmp:
    path = Path(tmp)
    (path / "run.mjs").write_text(runner)
    for compiler in os.environ.get("WASM_POLL_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            flags = [
                compiler,
                f"--target=wasm{bits}",
                "-O2",
                "-matomics",
                "-mbulk-memory",
                "-DWASM_POLL_THREAD_GLOBAL=1",
            ]
            # Clang18's inline-asm import-name storage does not survive direct
            # object emission. Keep its textual assembly input alive in a second
            # invocation. The project's released Clang22 already owns the names.
            assembly, obj, binary = (
                path / "owner.s",
                path / "owner.o",
                path / "owner.wasm",
            )
            if "clang version 18." in subprocess.check_output(
                [compiler, "--version"], text=True
            ):
                subprocess.run(
                    flags + ["-S", str(SOURCE), "-o", str(assembly)], check=True
                )
                subprocess.run(
                    [
                        compiler,
                        f"--target=wasm{bits}",
                        "-matomics",
                        "-mbulk-memory",
                        "-c",
                        str(assembly),
                        "-o",
                        str(obj),
                    ],
                    check=True,
                )
            else:
                subprocess.run(flags + ["-c", str(SOURCE), "-o", str(obj)], check=True)
            subprocess.run(
                [
                    compiler,
                    f"--target=wasm{bits}",
                    "-nostdlib",
                    str(obj),
                    "-Wl,--no-entry,--import-memory,--shared-memory,--max-memory=1048576",
                    "-Wl,--export=__wasm_init_tls,--export=__tls_base,--export=__tls_size,--export=__sanitizer_cov_trace_pc",
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            subprocess.run(
                ["node", str(path / "run.mjs"), str(binary), str(bits)], check=True
            )
            subprocess.run(
                flags
                + [
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    str(SOURCE),
                    "-o",
                    "/dev/null",
                ],
                check=True,
            )
            print(
                f"{compiler} wasm{bits}: actual global/TLS owner gate, inherited-parent refusal, independent budgets and import-type refusal pass; not Linux acceptance"
            )
