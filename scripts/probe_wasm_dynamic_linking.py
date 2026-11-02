#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded toolchain/engine experiment, not a Linux loader or ELF support claim."""

from pathlib import Path
import argparse
import json
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--clang", default="clang")
parser.add_argument("--node", default="node")
args = parser.parse_args()

LIB_A = r"""
int counter = 7;
volatile int seed = 3;
int inc(int x) { return counter += x; }
int (*get_function(void))(int) { return inc; }
__attribute__((constructor)) static void init(void) { counter += seed; }
"""
LIB_B = r"""
extern int counter;
extern int inc(int);
int *saved = &counter;
int observed;
__attribute__((constructor)) static void init(void) { observed = *saved; }
int initial_value(void) { return observed; }
int (*get_external_function(void))(int) { return inc; }
int run(int x) { int (*volatile fn)(int) = inc; return fn(x) + *saved; }
"""
RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {basename} from 'node:path';
import {read_wasm_dylink} from __BINARY_READER__;
import {plan_dylink_layout} from __LAYOUT_PLANNER__;
const [bits, first, second, mode] = process.argv.slice(2);
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
// Exercise the runtime's parser with actual LLD output, before instantiation.
// Dependency resolution and symbol binding below remain a bounded probe.
function dylink(module) {
 const result=read_wasm_dylink(module);
 assert(result,'missing dylink.0');
 assert.deepEqual(result.unknownSubsections,[],'probe cannot honor unknown extensions');
 if(result.target!==undefined)assert.equal(result.target,`wasm${bits}`);
 return result;
}
const metadata=modules.map(dylink);
const names=[first,second].map(path=>basename(path));
assert.deepEqual(metadata[0].needed,[]);
assert.deepEqual(metadata[1].needed,[names[0]],'linker must emit the actual shared dependency');
function order(root, available){
 const result=[],active=new Set(),done=new Set();
 function visit(name){assert(available.has(name),`missing dependency ${name}`);
  assert(!active.has(name),'cyclic dependencies are outside this probe');
  if(done.has(name))return;
  active.add(name);for(const dependency of available.get(name).needed)visit(dependency);
  active.delete(name);done.add(name);result.push(name);
 }
 visit(root);return result;
}
const available=new Map(names.map((name,i)=>[name,metadata[i]]));
assert.throws(()=>order(names[1],new Map([[names[1],metadata[1]]])),/missing dependency/);
assert.deepEqual(order(names[1],available),names);
// Use an isolated reservation plan, committing it only after every layout fits.
function reserve(items, memoryEnd, tableEnd, limits){
 const plan=plan_dylink_layout(items,
  {cursor:BigInt(memoryEnd),limit:BigInt(limits.memory),address:memoryAddress},
  {cursor:BigInt(tableEnd),limit:BigInt(limits.table),address:tableAddress});
 // This tiny corpus deliberately reserves only small host-addressable regions.
 return {items:plan.items.map(x=>({base:Number(x.base),tableBase:Number(x.tableBase)})),
  memoryEnd:Number(plan.memoryEnd),tableEnd:Number(plan.tableEnd)};
}
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
const limits={memory:4*65536,table:Number(table.length)-1}; // Reserve upper memory for the C stack.
const plan=reserve(metadata,65536,3,limits); // 0 null, 1/2 signal sentinels.
assert.throws(()=>reserve(metadata,65536,3,{...limits,memory:65536}),/reservation capacity/);
const [aRegion,bRegion]=plan.items;
assert(aRegion.base+metadata[0].memorySize<=bRegion.base);
assert(aRegion.tableBase+metadata[0].tableSize<=bRegion.tableBase);
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
const aImports=createGlobals(layouts[0],aRegion.base,aRegion.tableBase);
const a=new WebAssembly.Instance(modules[0],aImports);
assert(a.exports.counter instanceof WebAssembly.Global);
const counter=aRegion.base+Number(a.exports.counter.value);
const dataGOT=sharedGlobals.get('GOT.mem.counter');
if(dataGOT)dataGOT.value=word(typeof dataGOT.value==='bigint'?'i64':'i32',counter);
// Use the producer's canonical function pointer, not a duplicate table slot.
a.exports.__wasm_apply_data_relocs?.();
const pointer=a.exports.get_function();
const slot=Number(pointer);
assert(slot>=aRegion.tableBase&&slot<aRegion.tableBase+metadata[0].tableSize);
assert.equal(table.get(word(tableAddress,slot)),a.exports.inc);
const functionGOT=sharedGlobals.get('GOT.func.inc');
if(functionGOT)functionGOT.value=word(typeof functionGOT.value==='bigint'?'i64':'i32',slot);
const bImports=createGlobals(layouts[1],bRegion.base,bRegion.tableBase);
const externalData=sharedGlobals.get('GOT.mem.counter');
assert(externalData,'must test real imported data GOT');
externalData.value=word(typeof externalData.value==='bigint'?'i64':'i32',counter);
const externalFunction=sharedGlobals.get('GOT.func.inc');
assert(externalFunction,'must test real imported function GOT');
externalFunction.value=word(typeof externalFunction.value==='bigint'?'i64':'i32',slot);
if(bImports.env&&layouts[1].some(x=>x.kind===0&&x.field==='inc'))bImports.env.inc=a.exports.inc;
const b=new WebAssembly.Instance(modules[1],bImports);
b.exports.__wasm_apply_data_relocs?.();
const instances=new Map([[names[0],a],[names[1],b]]);
assert.equal(new DataView(memory.buffer).getInt32(counter,true),7,'constructor must not be folded into initial data');
const initialization=order(names[1],available);
if(mode==='reverse-ctors')initialization.reverse(); // Negative control must fail the C observation.
for(const name of initialization)instances.get(name).exports.__wasm_call_ctors?.();
assert.equal(b.exports.initial_value(),10,'dependency initialization and external data relocation precede consumer ctor');
assert.equal(b.exports.get_external_function(),pointer,'function pointer identity across modules');
assert.equal(new DataView(memory.buffer).getInt32(counter,true),10);
assert.equal(table.get(word(tableAddress,Number(pointer)))(2),12);
assert.equal(b.exports.run(3),30);
assert.equal(new DataView(memory.buffer).getInt32(counter,true),15);
assert.equal(memory.grow(word(memoryAddress,1)),word(memoryAddress,8));
assert.equal(b.exports.run(1),32);
const missing=createGlobals(layouts[1],bRegion.base,bRegion.tableBase);
delete missing['GOT.mem'].counter;
assert.throws(()=>new WebAssembly.Instance(modules[1],missing),WebAssembly.LinkError);
console.log(`PIC probe wasm${bits}: linker dependency order, metadata reservations, data relocations, shared memory/table, GOT, ctor, cross-module calls and growth pass (table ${tableAddress}); not Linux/ELF acceptance`);
"""

with tempfile.TemporaryDirectory(prefix="wasm-dylink-probe-") as tmp:
    directory = Path(tmp)
    (directory / "a.c").write_text(LIB_A)
    (directory / "b.c").write_text(LIB_B)
    runtime = Path(__file__).resolve().parents[1] / "sources/distro/packages/kernel/src"
    runner = RUNNER.replace(
        "__BINARY_READER__", json.dumps((runtime / "wasm_binary.ts").as_uri())
    ).replace("__LAYOUT_PLANNER__", json.dumps((runtime / "dylink.ts").as_uri()))
    (directory / "probe.mjs").write_text(runner)
    for bits in (32, 64):
        for name in ("a", "b"):
            subprocess.run(
                [
                    args.clang,
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
                    "-Wl,--export=__wasm_call_ctors",
                    f"-Wl,-soname,{name}{bits}.wasm",
                    f"-Wl,--max-memory={4294967296 if bits == 32 else 17179869184}",
                    str(directory / f"{name}.c"),
                    *([str(directory / f"a{bits}.wasm")] if name == "b" else []),
                    "-o",
                    str(directory / f"{name}{bits}.wasm"),
                ],
                check=True,
            )
        subprocess.run(
            [
                args.node,
                str(directory / "probe.mjs"),
                str(bits),
                str(directory / f"a{bits}.wasm"),
                str(directory / f"b{bits}.wasm"),
            ],
            check=True,
        )
        negative = subprocess.run(
            [
                args.node,
                str(directory / "probe.mjs"),
                str(bits),
                str(directory / f"a{bits}.wasm"),
                str(directory / f"b{bits}.wasm"),
                "reverse-ctors",
            ],
            capture_output=True,
            text=True,
        )
        if negative.returncode == 0 or (
            "dependency initialization and external data relocation precede consumer ctor"
            not in negative.stderr
        ):
            raise RuntimeError(
                "reversed constructor order did not fail the C observation: "
                + negative.stderr[:1200]
            )
        print(
            f"PIC probe wasm{bits}: reversed constructor order rejected by real C observation",
            flush=True,
        )
