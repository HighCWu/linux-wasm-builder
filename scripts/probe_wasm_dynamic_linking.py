#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded toolchain/engine experiment, not a Linux loader or ELF support claim."""

from pathlib import Path
import subprocess
import tempfile

LIB_A = r"""
int counter = 7;
int inc(int x) { return counter += x; }
int (*get_function(void))(int) { return inc; }
__attribute__((constructor)) static void init(void) { counter += 3; }
"""
LIB_B = r"""
extern int counter;
extern int inc(int);
int run(int x) { int (*volatile fn)(int) = inc; return fn(x) + counter; }
"""
RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const [bits, first, second] = process.argv.slice(2);
const modules = [first, second].map(p => new WebAssembly.Module(readFileSync(p)));
function imports(bytes) {
 let p=8;
 function u(){let v=0,s=0,b;do{b=bytes[p++];v+=(b&127)*2**s;s+=7;}while(b&128);return v;}
 function name(){let n=u();let s=new TextDecoder().decode(bytes.subarray(p,p+n));p+=n;return s;}
 let result=[];
 while(p<bytes.length){let id=bytes[p++], n=u(), end=p+n;
  if(id!==2){p=end;continue;}
  let count=u();
  for(let i=0;i<count;i++){
   let module=name(), field=name(), kind=bytes[p++];
   let item={module,field,kind};
   if(kind===0)u();
   else if(kind===1||kind===2){
    if(kind===1)assert.equal(bytes[p++],0x70);
    item.flags=u();item.minimum=u();if(item.flags&1)item.maximum=u();
   }else if(kind===3){item.type=bytes[p++]===0x7e?'i64':'i32';item.mutable=!!bytes[p++];}
   else throw new Error('unexpected experiment import kind');
   result.push(item);
  }
  assert.equal(p,end);
 }
 return result;
}
const layouts=[first,second].map(p=>imports(readFileSync(p)));
for(const m of modules)assert.equal(WebAssembly.Module.customSections(m,'dylink.0').length,1);
const memoryLayout=layouts.flat().find(x=>x.kind===2);
const tableLayout=layouts.flat().find(x=>x.kind===1);
assert(memoryLayout&&tableLayout);
assert(memoryLayout.flags&2,'experiment must use shared memory like the platform');
assert.equal(!!(memoryLayout.flags&4),bits==='64');
const word=(type,x)=>type==='i64'?BigInt(x):x;
const memoryAddress=memoryLayout.flags&4?'i64':'i32';
const tableAddress=tableLayout.flags&4?'i64':'i32';
const memory=new WebAssembly.Memory({initial:word(memoryAddress,8),maximum:word(memoryAddress,memoryLayout.maximum),shared:true,address:memoryAddress});
const table=new WebAssembly.Table({element:'anyfunc',initial:word(tableAddress,128),maximum:word(tableAddress,512),address:tableAddress});
const sharedGlobals=new Map();
function createGlobals(layout, base, tableBase){
 let map={};
 for(const i of layout){
  let group=map[i.module]??={};
  if(i.kind===2)group[i.field]=memory;
  else if(i.kind===1)group[i.field]=table;
  else if(i.kind===3){
   const key=i.module+'.'+i.field;
   let value=0;
   if(i.field==='__memory_base')value=base;
   if(i.field==='__table_base'||i.field==='__table_base32')value=tableBase;
   if(i.field==='__stack_pointer')value=8*65536-16;
   let g=i.module.startsWith('GOT.')||i.field==='__stack_pointer'?sharedGlobals.get(key):undefined;
   if(!g){g=new WebAssembly.Global({value:i.type,mutable:i.mutable},word(i.type,value));
    if(i.module.startsWith('GOT.')||i.field==='__stack_pointer')sharedGlobals.set(key,g);}
   group[i.field]=g;
  }
 }
 return map;
}
const aImports=createGlobals(layouts[0],16384,1);
const a=new WebAssembly.Instance(modules[0],aImports);
assert(a.exports.counter instanceof WebAssembly.Global);
const counter=16384+Number(a.exports.counter.value);
const dataGOT=sharedGlobals.get('GOT.mem.counter');
if(dataGOT)dataGOT.value=word(typeof dataGOT.value==='bigint'?'i64':'i32',counter);
const slot=64;
table.set(word(tableAddress,slot),a.exports.inc);
const functionGOT=sharedGlobals.get('GOT.func.inc');
if(functionGOT)functionGOT.value=word(typeof functionGOT.value==='bigint'?'i64':'i32',slot);
a.exports.__wasm_apply_data_relocs?.();
a.exports.__wasm_call_ctors();
assert.equal(new DataView(memory.buffer).getInt32(counter,true),10);
const pointer=a.exports.get_function();
if(typeof table.get(word(tableAddress,Number(pointer)))!=='function')
 throw new Error(JSON.stringify({bits,pointer:String(pointer),tableAddress,slots:[0,1,2,3,64].map(x=>[x,typeof table.get(word(tableAddress,x))]),imports:layouts[0]}));
assert.equal(table.get(word(tableAddress,Number(pointer)))(2),12);
const bImports=createGlobals(layouts[1],32768,16);
const externalData=sharedGlobals.get('GOT.mem.counter');
assert(externalData,'must test real imported data GOT');
externalData.value=word(typeof externalData.value==='bigint'?'i64':'i32',counter);
const externalFunction=sharedGlobals.get('GOT.func.inc');
assert(externalFunction,'must test real imported function GOT');
externalFunction.value=word(typeof externalFunction.value==='bigint'?'i64':'i32',slot);
if(bImports.env&&layouts[1].some(x=>x.kind===0&&x.field==='inc'))bImports.env.inc=a.exports.inc;
const b=new WebAssembly.Instance(modules[1],bImports);
b.exports.__wasm_apply_data_relocs?.();
b.exports.__wasm_call_ctors?.();
assert.equal(b.exports.run(3),30);
assert.equal(new DataView(memory.buffer).getInt32(counter,true),15);
assert.equal(memory.grow(word(memoryAddress,1)),word(memoryAddress,8));
assert.equal(b.exports.run(1),32);
const missing=createGlobals(layouts[1],49152,32);
delete missing['GOT.mem'].counter;
assert.throws(()=>new WebAssembly.Instance(modules[1],missing),WebAssembly.LinkError);
console.log(`PIC probe wasm${bits}: real shared memory/table, data/function GOT, ctor, cross-module calls and growth pass (table ${tableAddress}); not Linux/ELF acceptance`);
"""

with tempfile.TemporaryDirectory(prefix="wasm-dylink-probe-") as tmp:
    directory = Path(tmp)
    (directory / "a.c").write_text(LIB_A)
    (directory / "b.c").write_text(LIB_B)
    (directory / "probe.mjs").write_text(RUNNER)
    for bits in (32, 64):
        for name in ("a", "b"):
            subprocess.run(
                [
                    "clang",
                    f"--target=wasm{bits}",
                    "-nostdlib",
                    "-O2",
                    "-fPIC",
                    "-shared",
                    "-matomics",
                    "-mbulk-memory",
                    "-Wl,--shared-memory",
                    "-Wl,--no-entry",
                    "-Wl,--export-all",
                    f"-Wl,--max-memory={4294967296 if bits == 32 else 17179869184}",
                    str(directory / f"{name}.c"),
                    "-o",
                    str(directory / f"{name}{bits}.wasm"),
                ],
                check=True,
            )
        subprocess.run(
            [
                "node",
                str(directory / "probe.mjs"),
                str(bits),
                str(directory / f"a{bits}.wasm"),
                str(directory / f"b{bits}.wasm"),
            ],
            check=True,
        )
