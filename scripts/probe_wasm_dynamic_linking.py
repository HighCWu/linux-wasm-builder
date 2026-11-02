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

MAIN = r"""
int host_value = 5;
int host_add(int x) { return host_value += x; }
int (*main_function(void))(int) { return host_add; }
"""

LIB_A = r"""
int counter = 7;
volatile int seed = 3;
int inc(int x) { return counter += x; }
int twice(int x) { return x * 2; }
int (*get_function(void))(int) { return inc; }
__attribute__((constructor)) static void init(void) { counter += seed; }
"""
LIB_B = r"""
extern int counter;
extern int inc(int);
extern int twice(int);
extern int host_value;
extern int host_add(int);
extern int optional_fn(int) __attribute__((weak));
int *saved = &counter;
int observed;
__attribute__((constructor)) static void init(void) { observed = *saved; }
int initial_value(void) { return observed; }
int (*get_external_function(void))(int) { return inc; }
int (*get_unaddressed_function(void))(int) { return twice; }
int weak_present(void) { return optional_fn != 0; }
int direct(int x) { return inc(x); }
int from_main(int x) { return host_add(x) + host_value; }
int *main_data_address(void) { return &host_value; }
int (*main_function_address(void))(int) { return host_add; }
int run(int x) { int (*volatile fn)(int) = inc; return fn(x) + *saved; }
"""
RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {basename} from 'node:path';
import {read_wasm_dylink,read_wasm_dynamic_imports,read_wasm_dynamic_signatures} from __BINARY_READER__;
import {plan_dylink_layout} from __LAYOUT_PLANNER__;
import {link_dylink_graph} from __MODULE_LINKER__;
import {ProcessDylink} from __PROCESS_LOADER__;
const [bits, first, second, mainFile, mode] = process.argv.slice(2);
const modules = [first, second].map(p => new WebAssembly.Module(readFileSync(p)));
const layouts=[first,second].map(p=>read_wasm_dynamic_imports(new Uint8Array(readFileSync(p))));
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
const memoryLayout=layouts.flat().find(x=>x.kind==='memory')?.type;
const tableLayout=layouts.flat().find(x=>x.kind==='table');
assert(memoryLayout&&tableLayout);
assert(memoryLayout.shared,'experiment must use shared memory like the platform');
assert.equal(memoryLayout.address==='i64',bits==='64');
const word=(type,x)=>type==='i64'?BigInt(x):Number(x);
const memoryAddress=memoryLayout.address;
const tableAddress=tableLayout.address;
const memory=new WebAssembly.Memory({initial:word(memoryAddress,8),maximum:word(memoryAddress,memoryLayout.maximum),shared:true,address:memoryAddress});
const table=new WebAssembly.Table({element:'anyfunc',initial:word(tableAddress,128),maximum:word(tableAddress,512),address:tableAddress});
const limits={memory:4*65536,table:Number(table.length)-1}; // Main data/stack occupy the first two pages.
const plan=reserve(metadata,131072,8,limits); // Preserve main-module table entries.
assert.throws(()=>reserve(metadata,131072,8,{...limits,memory:131072}),/reservation capacity/);
const [aRegion,bRegion]=plan.items;
assert(aRegion.base+metadata[0].memorySize<=bRegion.base);
assert(aRegion.tableBase+metadata[0].tableSize<=bRegion.tableBase);
const files=new Map([[names[0],new Uint8Array(readFileSync(first))],[names[1],new Uint8Array(readFileSync(second))]]);
const mainBytes=new Uint8Array(readFileSync(mainFile));
const main=new WebAssembly.Instance(new WebAssembly.Module(mainBytes),{env:{memory,__indirect_function_table:table}});
const signatures=read_wasm_dynamic_signatures(mainBytes).exports;
const externalSymbols=new Map();
for(const [name,value] of Object.entries(main.exports)) {
 if(typeof value==='function')externalSymbols.set(name,{value,signature:signatures.get(name),
  ...(name==='host_add'?{address:BigInt(main.exports.main_function())}:{})});
 else if(value instanceof WebAssembly.Global)externalSymbols.set(name,{value,address:BigInt(value.value)});
}
const options={root:names[1],files,memory,table,
 externalSymbols,
 memoryMaximumPages:memoryLayout.maximum,tableMaximumElements:512n,
 stack:main.exports.__stack_pointer,
 memoryArena:{cursor:131072n,limit:BigInt(limits.memory),address:memoryAddress},
 tableArena:{cursor:8n,limit:BigInt(limits.table),address:tableAddress}};
const before=new Uint8Array(memory.buffer).slice();
assert.throws(()=>link_dylink_graph({...options,files:new Map([[names[1],files.get(names[1])]])}),/missing dynamic dependency/);
assert.deepEqual(new Uint8Array(memory.buffer),before,'preflight failure must not modify process memory');
const linked=link_dylink_graph(options);
assert.deepEqual(linked.order,names);
assert.deepEqual(linked.layout.items,plan.items.map(x=>({base:BigInt(x.base),tableBase:BigInt(x.tableBase)})));
const a=linked.instances.get(names[0]),b=linked.instances.get(names[1]);
assert(a.exports.counter instanceof WebAssembly.Global);
const counter=aRegion.base+Number(a.exports.counter.value);
// Use the producer's canonical function pointer, not a duplicate table slot.
const pointer=a.exports.get_function();
const slot=Number(pointer);
assert(slot>=aRegion.tableBase&&slot<aRegion.tableBase+metadata[0].tableSize);
assert.equal(table.get(word(tableAddress,slot)),a.exports.inc);
assert(layouts[1].some(x=>x.module==='GOT.mem'&&x.name==='counter'),'must test imported data GOT');
assert(layouts[1].some(x=>x.module==='GOT.func'&&x.name==='inc'),'must test imported function GOT');
assert.equal(new DataView(memory.buffer).getInt32(counter,true),7,'constructor must not be folded into initial data');
if(mode==='reverse-ctors') {
 for(const name of linked.order.toReversed())linked.instances.get(name).exports.__wasm_call_ctors?.();
} else {
 linked.initialize();
 assert.throws(()=>linked.initialize(),/cannot be retried/);
}
assert.equal(b.exports.initial_value(),10,'dependency initialization and external data relocation precede consumer ctor');
assert.equal(b.exports.get_external_function(),pointer,'function pointer identity across modules');
const extraPointer=b.exports.get_unaddressed_function();
assert(Number(extraPointer)>=plan.tableEnd,'exercise a newly allocated canonical function slot');
assert.equal(table.get(word(tableAddress,extraPointer)),a.exports.twice,'previously unaddressed export gets a callable slot');
assert.equal(table.get(word(tableAddress,extraPointer))(21),42);
assert.equal(b.exports.weak_present(),0,'unresolved weak function retains a null address');
assert.equal(b.exports.main_data_address(),main.exports.host_value.value,'main data addresses must not be relocated again');
assert.equal(b.exports.main_function_address(),main.exports.main_function(),'main canonical function pointer is preserved');
assert.equal(b.exports.from_main(3),16,'main direct/GOT calls share the actual main data');
assert.equal(linked.lookup('counter').address,BigInt(counter));
assert.equal(linked.lookup('inc').address,BigInt(pointer));
assert.equal(linked.lookup('host_value'),undefined,'handle-local lookup must exclude main-only definitions');
assert.equal(new DataView(memory.buffer).getInt32(counter,true),10);
assert.equal(table.get(word(tableAddress,Number(pointer)))(2),12);
assert.equal(b.exports.run(3),30);
assert.equal(new DataView(memory.buffer).getInt32(counter,true),15);
assert.equal(memory.grow(word(memoryAddress,1)),word(memoryAddress,8));
assert.equal(b.exports.run(1),32);
assert.equal(b.exports.direct(4),20,'direct function imports bind to the same dependency state');
// Exercise the process orchestration with a modeled C I/O bridge. The real
// Linux bridge and SDK are accepted only by their separate booted target.
let heap=5*65536;
const live=new Set();
const readCString=p=>{const bytes=new Uint8Array(memory.buffer,Number(p));return new TextDecoder().decode(bytes.subarray(0,bytes.indexOf(0)));};
function storeString(value){const data=new TextEncoder().encode(value+'\0');const p=heap;heap+=data.length;
 new Uint8Array(memory.buffer,p,data.length).set(data);return word(memoryAddress,p);}
const descriptor=120000,originPointer=121000;
const environmentPointer=storeString('/libraries');
const rootPointer=storeString('/libraries/'+names[1]);
const aliasPointer=storeString('/libraries/alias.wasm');
const dependencyPointer=storeString('/libraries/'+names[0]);
const runPointer=storeString('run'),counterPointer=storeString('counter');
const missingPointer=storeString('/missing.wasm'),badPointer=storeString('/bad.wasm');
const controlPointer=storeString('/control');
const control=Symbol('modeled exit/exec');
const virtualFiles=new Map([
 ['/libraries/'+names[0],{bytes:files.get(names[0]),inode:11n}],
 ['/libraries/'+names[1],{bytes:files.get(names[1]),inode:12n}],
 ['/libraries/alias.wasm',{bytes:files.get(names[1]),inode:12n}],
 ['/bad.wasm',{bytes:new Uint8Array([1,2,3]),inode:13n}],
]);
let processLoader,probeReentry=true,nextPin=1;
const pins=new Map();
const allocate=(size,alignment)=>{size=Number(size);alignment=Math.max(8,Number(alignment));
 const p=Math.ceil(heap/alignment)*alignment;heap=p+size;
 if(heap>memory.buffer.byteLength)memory.grow(word(memoryAddress,Math.ceil((heap-memory.buffer.byteLength)/65536)));
 live.add(p);
 if(probeReentry&&processLoader){probeReentry=false;
  assert.equal(processLoader.open(rootPointer,0),word(memoryAddress,0));
  assert.equal(processLoader.open(rootPointer,2),word(memoryAddress,0),'failed recursive call must not unlock outer loading');}
 return word(memoryAddress,p);};
const deallocate=p=>{assert(live.delete(Number(p)),'exactly one owner frees each temporary allocation');};
const bridge={exports:{...main.exports,
 __indirect_function_table:table,
 __wasm_dlopen_io_v1:()=>1,
 __wasm_dlopen_allocate:allocate,
 __wasm_dlopen_deallocate:deallocate,
 __wasm_dlopen_library_path:()=>environmentPointer,
 __wasm_dlopen_origin:()=>word(memoryAddress,originPointer),
 __wasm_dlopen_fd:()=>0,
 __wasm_dlopen_read:path=>{const name=readCString(path);if(name==='/control')throw control;
  const view=new DataView(memory.buffer,descriptor,40);new Uint8Array(memory.buffer,descriptor,40).fill(0);
  const file=virtualFiles.get(name);if(!file){view.setBigUint64(32,2n,true);return word(memoryAddress,descriptor);}
  const pointer=allocate(file.bytes.length,8);new Uint8Array(memory.buffer,Number(pointer),file.bytes.length).set(file.bytes);
  const refreshed=new DataView(memory.buffer,descriptor,40);refreshed.setBigUint64(0,BigInt(pointer),true);
  refreshed.setBigUint64(8,BigInt(file.bytes.length),true);refreshed.setBigUint64(16,1n,true);refreshed.setBigUint64(24,file.inode,true);
  new Uint8Array(memory.buffer,originPointer,name.length+1).set(new TextEncoder().encode(name+'\0'));
  return word(memoryAddress,descriptor);},
 __wasm_dlopen_read_release:()=>{const pointer=new DataView(memory.buffer,descriptor,40).getBigUint64(0,true);
  if(pointer)deallocate(pointer);
  new Uint8Array(memory.buffer,descriptor,40).fill(0);},
}};
processLoader=new ProcessDylink({main:bridge,memory,address:memoryAddress,maximumPages:Number(memoryLayout.maximum),
 tableType:{address:tableAddress,minimum:128n,maximum:512n},signatures,
 isControlFlow:error=>error===control,fatal:error=>{throw error;},
 pinFile:(fd,device,inode)=>{assert.equal(fd,0);assert.equal(device,1n);assert(inode===11n||inode===12n);
  const id=nextPin++;pins.set(id,allocate(1,8));return id;},
 unpinFile:id=>{assert(pins.has(id));deallocate(pins.get(id));pins.delete(id);return 0;}});
const handle=processLoader.open(rootPointer,2);assert(handle!==word(memoryAddress,0));
assert.equal(processLoader.symbol(word(memoryAddress,0),runPointer),word(memoryAddress,0),'local group must not become globally visible');
const runAddress=processLoader.symbol(handle,runPointer);
assert.equal(table.get(word(tableAddress,runAddress))(1),22);
assert.equal(processLoader.open(aliasPointer,2|4|256),handle,'inode alias and NOLOAD reuse');
assert.equal(processLoader.symbol(word(memoryAddress,0),runPointer),runAddress,'GLOBAL promotion preserves canonical pointer');
const dependency=processLoader.open(dependencyPointer,2);
const dependencyCounter=Number(processLoader.symbol(dependency,counterPointer));
assert.equal(new DataView(memory.buffer).getInt32(dependencyCounter,true),11,'opening an existing dependency must not rerun constructors or zero data');
const retained=live.size;
assert.equal(processLoader.open(missingPointer,2),word(memoryAddress,0));
assert.equal(processLoader.open(badPointer,2),word(memoryAddress,0));
assert.equal(live.size,retained,'ordinary failures release C buffers and path allocations');
assert.equal(processLoader.open(rootPointer,2),handle,'ordinary failures preserve live object group');
assert.equal(processLoader.valid(handle),1);assert.equal(processLoader.valid(word(memoryAddress,0)),0);
assert.throws(()=>processLoader.open(controlPointer,2),error=>error===control,'exit/exec is never converted into recoverable dlerror');
assert.equal(live.size,retained+1,'after exit/exec the old libc must not be called to free old-context paths');
console.log(`Process loader model wasm${bits}: aliases, scopes, reuse, read cleanup, reentry guard and control transfer pass; not Linux bridge acceptance`);
console.log(`PIC probe wasm${bits}: runtime linker dependencies, relocations, GOT, weak/null, canonical slots, main symbols, handle lookup, ctor, direct/indirect calls and growth pass (table ${tableAddress}); not Linux/ELF acceptance`);
"""

with tempfile.TemporaryDirectory(prefix="wasm-dylink-probe-") as tmp:
    directory = Path(tmp)
    (directory / "a.c").write_text(LIB_A)
    (directory / "b.c").write_text(LIB_B)
    (directory / "main.c").write_text(MAIN)
    runtime = Path(__file__).resolve().parents[1] / "sources/distro/packages/kernel/src"
    runner = RUNNER.replace(
        "__BINARY_READER__", json.dumps((runtime / "wasm_binary.ts").as_uri())
    ).replace("__LAYOUT_PLANNER__", json.dumps((runtime / "dylink.ts").as_uri()))
    runner = runner.replace(
        "__MODULE_LINKER__", json.dumps((runtime / "dylink_linker.ts").as_uri())
    )
    runner = runner.replace(
        "__PROCESS_LOADER__", json.dumps((runtime / "dylink_process.ts").as_uri())
    )
    (directory / "probe.mjs").write_text(runner)
    for bits in (32, 64):
        for name in ("main", "a", "b"):
            subprocess.run(
                [
                    args.clang,
                    f"--target=wasm{bits}",
                    "-nostdlib",
                    "-O2",
                    *([] if name == "main" else ["-fPIC", "-shared"]),
                    "-matomics",
                    "-mbulk-memory",
                    "-Wl,--shared-memory",
                    "-Wl,--no-entry",
                    "-Wl,--import-memory",
                    "-Wl,--import-table",
                    *(
                        ["-Wl,--table-base=3", "-Wl,--export=__stack_pointer"]
                        if name == "main"
                        else []
                    ),
                    "-Wl,--export-all",
                    "-Wl,--export=__wasm_call_ctors",
                    *([] if name == "main" else [f"-Wl,-soname,{name}{bits}.wasm"]),
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
                str(directory / f"main{bits}.wasm"),
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
                str(directory / f"main{bits}.wasm"),
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
