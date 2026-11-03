#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real heap-layout and SjLj objects across the strict shared-link boundary.

This is a small link/execution check, not complete shared-libc acceptance.
"""

import os
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
recipe = (ROOT / "sources/distro/distro/musl/package.nix").read_text()
link_flags = re.search(r"^\s*LDFLAGS_AUTO=(.+)$", recipe, re.M).group(1)
source = (MUSL / "src/linux/brk.c").read_text()
layout = source[source.index('__attribute__((export_name("__wasm_brk_layout_v1")))') :]
layout = layout[: layout.index("\n}\n") + 3]
longjmp = (
    (MUSL / "src/setjmp/wasm32/wasm_longjmp.c")
    .read_text()
    .replace("#include <stdint.h>", "typedef __UINT32_TYPE__ uint32_t;")
)
fixture = (
    "typedef __UINTPTR_TYPE__ uintptr_t;\nextern void __heap_end, __global_base, __data_end;\n"
    + layout
    + longjmp
)
runner = r"""
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const [file,bits]=process.argv.slice(2),wide=bits==='64';
const word=n=>wide?BigInt(n):n,type=wide?'i64':'i32';
const module=await WebAssembly.compile(readFileSync(file));
const imports=WebAssembly.Module.imports(module);
for(const name of ['__heap_end','__global_base','__data_end'])
 assert(imports.some(item=>item.module==='GOT.mem'&&item.name===name&&item.kind==='global'));
assert(imports.some(item=>item.module==='env'&&item.name==='__c_longjmp'&&item.kind==='tag'));
const table64=wide&&!imports.some(item=>item.name==='__table_base32');
const tag=new WebAssembly.Tag({parameters:[type]});
const memory=new WebAssembly.Memory({initial:word(4),maximum:word(wide?262144:65536),shared:true,address:type});
const env={memory,__c_longjmp:tag,
 __indirect_function_table:new WebAssembly.Table({element:'anyfunc',initial:table64?0n:0,address:table64?'i64':'i32'}),
 __memory_base:new WebAssembly.Global({value:type,mutable:false},word(1024)),
 __table_base:new WebAssembly.Global({value:type,mutable:false},word(0)),
 __table_base32:new WebAssembly.Global({value:'i32',mutable:false},0)};
const got=Object.fromEntries(Object.entries({__heap_end:16384,__global_base:4096,__data_end:8192})
 .map(([name,value])=>[name,new WebAssembly.Global({value:type,mutable:true},word(value))]));
await assert.rejects(()=>WebAssembly.instantiate(module,{env,'GOT.mem':{}}),WebAssembly.LinkError);
const instance=await WebAssembly.instantiate(module,{env,'GOT.mem':got});
instance.exports.__wasm_apply_data_relocs?.();instance.exports.__wasm_call_ctors?.();
const pointer=Number(instance.exports.__wasm_brk_layout_v1()),view=new DataView(memory.buffer);
assert.deepEqual([0,1,2].map(i=>wide?Number(view.getBigUint64(pointer+i*8,true)):view.getUint32(pointer+i*4,true)),[16384,4096,8192]);
try {instance.exports.__wasm_longjmp(word(32768),7);assert.fail('SjLj must throw');}
catch(error){assert(error instanceof WebAssembly.Exception);assert(error.is(tag));
 const payload=Number(error.getArg(tag,0));assert.equal(payload,32768+(wide?16:8));
 assert.equal(view.getInt32(payload+(wide?8:4),true),7);}
"""
with tempfile.TemporaryDirectory(prefix="musl-shared-imports-") as tmp:
    path = Path(tmp)
    (path / "probe.c").write_text(fixture)
    (path / "run.mjs").write_text(runner)
    for compiler in os.environ.get("WASM_SHARED_COMPILERS", "clang clang-22").split():
        version = subprocess.check_output([compiler, "--version"], text=True)
        major = int(re.search(r"clang version (\d+)", version).group(1))
        for bits in (32, 64):
            binary = path / "probe.wasm"
            common = [
                compiler,
                f"--target=wasm{bits}",
                "-O2",
                "-fPIC",
                "-matomics",
                "-mbulk-memory",
                "-mllvm",
                "-wasm-enable-sjlj",
                "-nostdlib",
                "-Wl,--shared",
                "-Wl,--export-all",
                str(path / "probe.c"),
                "-o",
                str(binary),
            ]
            strict = subprocess.run(
                common + ["-Wl,--unresolved-symbols=report-all"],
                capture_output=True,
                text=True,
            )
            if (major >= 22 and not strict.returncode) or (
                strict.returncode
                and not all(
                    name in strict.stderr for name in ("__heap_end", "__c_longjmp")
                )
            ):
                raise RuntimeError(
                    "strict control did not reproduce the heap/tag link boundary"
                )
            maximum = 4294967296 if bits == 32 else 17179869184
            subprocess.run(
                common
                + [
                    link_flags.replace(
                        "${toString platform.maximumMemoryBytes}", str(maximum)
                    )
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["node", str(path / "run.mjs"), str(binary), str(bits)], check=True
            )
            policy = (
                "strict control rejects"
                if strict.returncode
                else "older shared linker permits undefineds"
            )
            print(
                f"{compiler} wasm{bits}: {policy}; explicit heap-layout relocations and imported SjLj identity/payload pass; not full shared-libc acceptance"
            )
