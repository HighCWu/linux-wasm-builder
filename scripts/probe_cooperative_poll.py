#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real Clang loop instrumentation/TLS batching; no Linux signal claim."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "sources/distro/distro/cooperative-poll/execution.c"
program = r"""
static _Thread_local volatile unsigned finished;
__attribute__((export_name("stop"),no_sanitize("coverage")))
void stop(void) { finished=1; }
__attribute__((export_name("reset"),no_sanitize("coverage")))
void reset(void) { finished=0; }
__attribute__((export_name("compute")))
unsigned compute(unsigned limit) {
 unsigned count=0;
 while(!finished&&count<limit)count++;
 return count;
}
"""
runner = r"""
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const [file,bits]=process.argv.slice(2),wide=bits==='64',word=n=>wide?BigInt(n):n;
const module=await WebAssembly.compile(readFileSync(file));
assert.deepEqual(WebAssembly.Module.imports(module).filter(i=>i.kind==='function'),
 [{module:'linux_user_poll_v1',name:'checkpoint',kind:'function'}]);
const memory=new WebAssembly.Memory({initial:word(8),maximum:word(16),shared:true,address:wide?'i64':'i32'});
const threads=[];
for(let index=0;index<2;index++){
 const state={instance:undefined,polls:0,throws:false,refuses:false};
 const instance=await WebAssembly.instantiate(module,{env:{memory},linux_user_poll_v1:{checkpoint(){
  state.polls++;
  if(state.throws){state.throws=false;throw sentinel;}
  if(state.refuses)return -95;
  if(state.polls===3)state.instance.exports.stop();
  return 0;
 }}});
 state.instance=instance;threads.push(state);
 assert.equal(instance.exports.__wasm_user_poll_abi(),1);
 const prefix=new Uint8Array(memory.buffer,0,64).slice();
 instance.exports.__sanitizer_cov_trace_pc();
 assert.equal(state.polls,0,'pre-TLS hook must not enter the host');
 assert.deepEqual(new Uint8Array(memory.buffer,0,64),prefix,'pre-TLS memory is unchanged');
 instance.exports.__wasm_init_tls(word((4+index)*65536));
}
const counts=[];
for(const state of threads){
 const count=state.instance.exports.compute(65536);
 assert(count>4096&&count<65536,'compiler checkpoints interrupt pure computation without syscalls');
 assert.equal(state.polls,3,'host entry is batched');counts.push(count);
}
assert.equal(counts[0],counts[1],'each thread instance owns its own native TLS budget');
const sentinel=Symbol('nonlocal signal control'),state=threads[0];
state.instance.exports.reset();state.polls=0;state.throws=true;
assert.throws(()=>state.instance.exports.compute(65536),error=>error===sentinel);
state.polls=0;
assert(state.instance.exports.compute(65536)<65536,'budget recovers after a nonlocal callback');
assert.equal(state.polls,3);
state.instance.exports.reset();state.refuses=true;
assert.throws(()=>state.instance.exports.compute(65536),WebAssembly.RuntimeError,'unsupported checkpoint fails visibly');
"""
with tempfile.TemporaryDirectory(prefix="cooperative-poll-") as tmp:
    path = Path(tmp)
    (path / "program.c").write_text(program)
    (path / "run.mjs").write_text(runner)
    for cc in os.environ.get("WASM_POLL_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            common = [
                cc,
                f"--target=wasm{bits}",
                "-O2",
                "-matomics",
                "-mbulk-memory",
                "-nostdlib",
                "-Wl,--no-entry,--import-memory,--shared-memory,--max-memory=1048576",
                "-Wl,--export=__wasm_init_tls,--export=__tls_base,--export=__tls_size,--export=__tls_align",
                "-Wl,--export=__sanitizer_cov_trace_pc",
            ]
            for mode in ("instrumented", "plain"):
                binary = path / "program.wasm"
                flags = (
                    ["-fsanitize-coverage=trace-pc,no-prune,edge"]
                    if mode == "instrumented"
                    else []
                )
                subprocess.run(
                    common
                    + flags
                    + [str(EXECUTION), str(path / "program.c"), "-o", str(binary)],
                    check=True,
                )
                run = subprocess.run(
                    ["node", str(path / "run.mjs"), str(binary), str(bits)],
                    capture_output=True,
                    text=True,
                )
                if mode == "instrumented" and run.returncode:
                    raise RuntimeError(run.stderr)
                if mode == "plain" and (
                    not run.returncode
                    or "compiler checkpoints interrupt pure computation"
                    not in run.stderr
                ):
                    raise RuntimeError(
                        "uninstrumented control did not fail at the compute-loop assertion"
                    )
            print(
                f"{cc} wasm{bits}: automatic pure-loop polling, TLS/pre-TLS, batching and nonlocal recovery pass; plain-loop control fails; no Linux signal acceptance"
            )
