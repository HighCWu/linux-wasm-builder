#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute actual TP reset code and libc-free entry artifacts; not Linux exec acceptance."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = Path(os.environ.get("WASM_EXEC_STATE_SOURCE_ROOT", ROOT / "sources/linux"))
CONSUMER = ROOT / "sources/distro/distro/exec-thread-state"
processor = (LINUX / "arch/wasm/include/asm/processor.h").read_text()
flush = processor[processor.index("static inline void flush_thread(void)") :]
flush = flush[: flush.index("\n}\n") + 3]
generic = (LINUX / "fs/exec.c").read_text()
loader = (LINUX / "arch/wasm/kernel/binfmt_wasm.c").read_text()
assert generic.index("int begin_new_exec(") < generic.index("\tflush_thread();")
start = loader.index("static int load_wasm_binary(struct linux_binprm *bprm)\n{")
load = loader[start:]
assert (
    load.index("wasm_user_compile_end(")
    < load.index("ret = copy_args(bprm);")
    < load.index("ret = begin_new_exec(bprm);")
    < load.index("wasm_user_instantiate(true);")
)
model = r"""
struct thread_info { unsigned long flags, tp_value; int phase; };
static struct thread_info threads[2], *active;
#define current_thread_info() active
"""
checks = r"""
__attribute__((export_name("check"))) int check(void) {
 unsigned long high=(unsigned long)0x100010000ULL | 0x90010000UL;
 threads[0]=(struct thread_info){71,high,1};
 threads[1]=(struct thread_info){73,high-16,0};
 active=&threads[0];flush_thread();
 if(threads[0].tp_value || threads[0].flags!=71 || threads[0].phase!=1)return 1;
 if(threads[1].tp_value!=high-16 || threads[1].flags!=73)return 2;
 active=&threads[1];flush_thread();flush_thread();
 return threads[1].tp_value || threads[1].flags!=73 || threads[1].phase!=0;
}
"""
runner = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [file,bits,mode]=process.argv.slice(2),wide=bits==='64',word=n=>wide?BigInt(n):n;
const module=await WebAssembly.compile(readFileSync(file));
if(mode!=='entry'){
 const instance=await WebAssembly.instantiate(module);
 assert.equal(instance.exports.check()===0,mode==='normal');
}else{
 const {user_function_imports_supported}=await import(pathToFileURL(process.argv[5]).href);
 assert(user_function_imports_supported(readFileSync(file),wide?'i64':'i32',true),'actual Clang entry must pass the exec ABI gate');
 assert.deepEqual(WebAssembly.Module.imports(module).map(i=>`${i.module}.${i.name}:${i.kind}`).sort(),
  ['env.memory:memory','linux.get_thread_area:function','linux.syscall:function']);
 for(const tp of [0,0x90010000]){
  let observed=0,status=-1;
  const exit=Symbol('exit');
  const memory=new WebAssembly.Memory({initial:word(2),maximum:word(wide?262144:65536),shared:true,address:wide?'i64':'i32'});
  const instance=await WebAssembly.instantiate(module,{env:{memory},linux:{
   get_thread_area(){observed++;return word(tp);},
   syscall(n,s,...args){assert.equal(Number(n),94);assert.equal(observed,1);assert(args.every(v=>v===word(0)));status=Number(s);throw exit;}
  }});
  assert.throws(()=>instance.exports._start(),e=>e===exit);
  assert.equal(status,tp?31:0,'old inherited TP must fail before any libc startup');
 }
}
"""
with tempfile.TemporaryDirectory(prefix="exec-thread-state-") as tmp:
    path = Path(tmp)
    (path / "run.mjs").write_text(runner)
    musl = ROOT / "sources/musl"
    (path / "bits").mkdir()
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        musl / "include/alltypes.h.in"
    ).read_text()
    (path / "bits/alltypes.h").write_text(
        subprocess.check_output(
            ["sed", "-f", str(musl / "tools/mkalltypes.sed")],
            input=templates,
            text=True,
        )
    )
    for cc in os.environ.get("WASM_EXEC_STATE_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output(
            [cc, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            common = [cc, f"--target=wasm{bits}", "-O2", "-Wall", "-Wextra", "-Werror"]
            headers = ["-nostdinc", "-I", tmp]
            for directory in ("arch/wasm32", "arch/generic", "include"):
                headers += ["-I", str(musl / directory)]
            headers += ["-isystem", resource + "/include"]
            subprocess.run(
                common
                + headers
                + [
                    "-matomics",
                    "-mbulk-memory",
                    "-mllvm",
                    "-wasm-enable-sjlj",
                    "-c",
                    str(CONSUMER / "runtime.c"),
                    "-o",
                    str(path / "runtime.o"),
                ],
                check=True,
            )
            subprocess.run(
                common
                + headers
                + [
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    str(CONSUMER / "runtime.c"),
                    "-o",
                    "/dev/null",
                ],
                check=True,
            )
            binary = path / "probe.wasm"
            imports_consumer = ROOT / "sources/distro/distro/exec-imports/runtime.c"
            for action in (
                [
                    "-matomics",
                    "-mbulk-memory",
                    "-mllvm",
                    "-wasm-enable-sjlj",
                    "-c",
                    str(imports_consumer),
                    "-o",
                    str(path / "imports.o"),
                ],
                [
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    str(imports_consumer),
                    "-o",
                    "/dev/null",
                ],
            ):
                subprocess.run(common + headers + action, check=True)
            for mode in ("normal", "missing-reset"):
                source = path / "probe.c"
                body = (
                    flush
                    if mode == "normal"
                    else flush.replace("current_thread_info()->tp_value = 0;", "")
                )
                assert mode == "normal" or body != flush
                source.write_text(model + body + checks)
                subprocess.run(
                    common
                    + ["-nostdlib", str(source), "-Wl,--no-entry", "-o", str(binary)],
                    check=True,
                )
                subprocess.run(
                    ["node", str(path / "run.mjs"), str(binary), str(bits), mode],
                    check=True,
                )
                if mode == "normal":
                    subprocess.run(
                        common
                        + [
                            "--analyze",
                            "-Xanalyzer",
                            "-analyzer-werror",
                            str(source),
                            "-o",
                            "/dev/null",
                        ],
                        check=True,
                    )
            maximum = 17179869184 if bits == 64 else 4294967296
            subprocess.run(
                common
                + [
                    "-matomics",
                    "-mbulk-memory",
                    "-nostdlib",
                    str(CONSUMER / "entry.c"),
                    f"-Wl,--no-entry,--export=_start,--import-memory,--shared-memory,--export-table,--export=__stack_pointer,--max-memory={maximum}",
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            subprocess.run(
                ["node", str(path / "run.mjs"), str(binary), str(bits), "entry",
                 str(ROOT / "sources/distro/packages/kernel/src/user-functions.ts")],
                check=True,
            )
            print(
                f"{cc} wasm{bits}: actual reset/isolation, missing-reset control, libc-free entry and inherited-TP refusal pass; not Linux exec acceptance"
            )
