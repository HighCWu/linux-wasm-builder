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
int unaddressed_main(int n) { return n + 40; }
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
const [bits, first, second, mainFile, cycleAFile, cycleBFile, mode] = process.argv.slice(2);
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
const environmentPointer=storeString('/shadow:/libraries');
const searchedPointer=storeString(names[1]),blockedPointer=storeString('blocked.wasm');
const rootPointer=storeString('/libraries/'+names[1]);
const aliasPointer=storeString('/libraries/alias.wasm');
const dependencyPointer=storeString('/libraries/'+names[0]);
const runPointer=storeString('run'),counterPointer=storeString('counter');
const missingPointer=storeString('/missing.wasm'),badPointer=storeString('/bad.wasm');
const controlPointer=storeString('/control');
const control=Symbol('modeled exit/exec');
// A genuine Wasm start callback enters main dlsym while the new module's active
// element segment already occupies its assigned table region.
const str=value=>[value.length,...new TextEncoder().encode(value)];
const sec=(id,payload)=>[id,payload.length,...payload];
const baseName=tableAddress==='i32'?'__table_base32':'__table_base';
const startModule=new Uint8Array([0,97,115,109,1,0,0,0,
 ...sec(0,[...str('dylink.0'),...sec(1,[0,0,1,0])]),
 ...sec(1,[2,0x60,0,0,0x60,0,1,0x7f]),
 ...sec(2,[3,...str('env'),...str('during_start'),0,0,
  ...str('env'),...str('__indirect_function_table'),1,0x70,tableAddress==='i64'?4:0,0,
  ...str('env'),...str(baseName),3,tableAddress==='i64'?0x7e:0x7f,0]),
 ...sec(3,[3,1,1,0]),
 ...sec(7,[2,...str('answer'),0,1,...str('entry'),0,2]),
 ...sec(8,[3]),
 ...sec(9,[1,0,0x23,0,0x0b,1,1]),
 ...sec(10,[3,5,0,0x41,0xe3,0,0x0b,
  ...(tableAddress==='i64'?[5,0,0x23,0,0xa7,0x0b]:[4,0,0x23,0,0x0b]),
  4,0,0x10,0,0x0b]),
]);
const unaddressedPointer=storeString('unaddressed_main');
let fromStart;
const virtualFiles=new Map([
 ['/libraries/'+names[0],{bytes:files.get(names[0]),inode:11n}],
 ['/libraries/'+names[1],{bytes:files.get(names[1]),inode:12n}],
 ['/libraries/alias.wasm',{bytes:files.get(names[1]),inode:12n}],
 ['/bad.wasm',{bytes:new Uint8Array([1,2,3]),inode:13n}],
 ['/shadow/'+names[1],{bytes:new Uint8Array([1,2,3]),inode:13n}],
 ['/libraries/blocked.wasm',{bytes:files.get(names[1]),inode:12n}],
 ['/libraries/noexec.wasm',{bytes:files.get(names[1]),inode:12n}],
 ['/libraries/nomemory.wasm',{bytes:files.get(names[1]),inode:12n}],
 ['/libraries/denied.wasm',{bytes:files.get(names[1]),inode:12n}],
 ['/libraries/'+basename(cycleAFile),{bytes:new Uint8Array(readFileSync(cycleAFile)),inode:21n}],
 ['/libraries/'+basename(cycleBFile),{bytes:new Uint8Array(readFileSync(cycleBFile)),inode:22n}],
 ['/libraries/start.wasm',{bytes:startModule,inode:31n}],
]);
assert.deepEqual(dylink(new WebAssembly.Module(readFileSync(cycleAFile))).needed,[basename(cycleBFile)]);
assert.deepEqual(dylink(new WebAssembly.Module(readFileSync(cycleBFile))).needed,[basename(cycleAFile)]);
let processLoader,probeReentry=true,nextPin=1,currentFd=-1;
const attempted=[];
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
 during_start:()=>{fromStart=processLoader.symbol(word(memoryAddress,0),unaddressedPointer);
  assert.notEqual(fromStart,word(memoryAddress,0),'dlsym in start resolves a new main pointer');},
 __indirect_function_table:table,
 __wasm_dlopen_io_v1:()=>1,
 __wasm_dlopen_allocate:allocate,
 __wasm_dlopen_deallocate:deallocate,
 __wasm_dlopen_library_path:()=>environmentPointer,
 __wasm_dlopen_origin:()=>word(memoryAddress,originPointer),
 __wasm_dlopen_fd:()=>currentFd,
 __wasm_dlopen_read:path=>{const name=readCString(path);if(name==='/control')throw control;
  attempted.push(name);currentFd=-1;
  const view=new DataView(memory.buffer,descriptor,40);new Uint8Array(memory.buffer,descriptor,40).fill(0);
  if(name==='/shadow/blocked.wasm'){view.setBigUint64(32,24n,true);return word(memoryAddress,descriptor);}
  if(name==='/shadow/noexec.wasm'||name==='/shadow/nomemory.wasm'){
   currentFd=0;view.setBigUint64(32,name.includes('noexec')?13n:12n,true);return word(memoryAddress,descriptor);}
  if(name==='/shadow/denied.wasm'){view.setBigUint64(32,13n,true);return word(memoryAddress,descriptor);}
  const file=virtualFiles.get(name);if(!file){view.setBigUint64(32,2n,true);return word(memoryAddress,descriptor);}
  currentFd=0;
  const pointer=allocate(file.bytes.length,8);new Uint8Array(memory.buffer,Number(pointer),file.bytes.length).set(file.bytes);
  const refreshed=new DataView(memory.buffer,descriptor,40);refreshed.setBigUint64(0,BigInt(pointer),true);
  refreshed.setBigUint64(8,BigInt(file.bytes.length),true);refreshed.setBigUint64(16,1n,true);refreshed.setBigUint64(24,file.inode,true);
  new Uint8Array(memory.buffer,originPointer,name.length+1).set(new TextEncoder().encode(name+'\0'));
  return word(memoryAddress,descriptor);},
 __wasm_dlopen_read_release:()=>{const pointer=new DataView(memory.buffer,descriptor,40).getBigUint64(0,true);
  if(pointer)deallocate(pointer);
  new Uint8Array(memory.buffer,descriptor,40).fill(0);currentFd=-1;},
}};
processLoader=new ProcessDylink({main:bridge,memory,address:memoryAddress,maximumPages:Number(memoryLayout.maximum),
 tableType:{address:tableAddress,minimum:128n,maximum:512n},signatures:new Map([...signatures,['during_start','[[],[]]']]),
 isControlFlow:error=>error===control,fatal:error=>{throw error;},
 pinFile:(fd,device,inode)=>{assert.equal(fd,0);assert.equal(device,1n);assert([11n,12n,21n,22n,31n].includes(inode));
  const id=nextPin++;pins.set(id,allocate(1,8));return id;},
 unpinFile:id=>{assert(pins.has(id));deallocate(pins.get(id));pins.delete(id);return 0;}});
const beforeSearch=live.size;
assert.equal(processLoader.open(searchedPointer,2),word(memoryAddress,0),'opened malformed file must stop search');
assert.deepEqual(attempted,['/shadow/'+names[1]],'do not substitute a later same-name library');
assert.equal(live.size,beforeSearch,'shadow failure releases temporary buffers');
attempted.length=0;
assert.equal(processLoader.open(blockedPointer,2),word(memoryAddress,0),'EMFILE must stop search');
assert.deepEqual(attempted,['/shadow/blocked.wasm']);
assert.equal(live.size,beforeSearch,'hard open error releases temporary paths');
for(const name of ['noexec.wasm','nomemory.wasm']){
 attempted.length=0;
 assert.equal(processLoader.open(storeString(name),2),word(memoryAddress,0),'opened-file error must stop search');
 assert.deepEqual(attempted,['/shadow/'+name]);
 assert.equal(live.size,beforeSearch,'opened-file error releases temporary paths');}
virtualFiles.delete('/shadow/'+names[1]);attempted.length=0;
const handle=processLoader.open(searchedPointer,2);assert(handle!==word(memoryAddress,0));
assert(attempted.includes('/shadow/'+names[1])&&attempted.includes('/libraries/'+names[1]),'ENOENT permits next directory and successful recovery');
assert.equal(processLoader.open(rootPointer,2),handle);
attempted.length=0;
assert.equal(processLoader.open(storeString('denied.wasm'),2),handle,'EACCES while opening permits next directory');
assert.deepEqual(attempted,['/shadow/denied.wasm','/libraries/denied.wasm']);
assert.equal(processLoader.symbol(word(memoryAddress,0),runPointer),word(memoryAddress,0),'local group must not become globally visible');
const runAddress=processLoader.symbol(handle,runPointer);
assert.equal(table.get(word(tableAddress,runAddress))(1),22);
assert.equal(processLoader.open(aliasPointer,2|4|256),handle,'inode alias and NOLOAD reuse');
assert.equal(processLoader.symbol(word(memoryAddress,0),runPointer),runAddress,'GLOBAL promotion preserves canonical pointer');
const dependency=processLoader.open(dependencyPointer,2);
const dependencyCounter=Number(processLoader.symbol(dependency,counterPointer));
assert.equal(new DataView(memory.buffer).getInt32(dependencyCounter,true),11,'opening an existing dependency must not rerun constructors or zero data');
const cycle=processLoader.open(storeString(basename(cycleAFile)),2);
assert.notEqual(cycle,word(memoryAddress,0),'load real mutual NEEDED graph');
const address=name=>Number(processLoader.symbol(cycle,storeString(name)));
const data=name=>new DataView(memory.buffer).getInt32(address(name),true);
const pointerAt=name=>memoryAddress==='i64'?new DataView(memory.buffer).getBigUint64(address(name),true):BigInt(new DataView(memory.buffer).getUint32(address(name),true));
assert.equal(data('cycle_a_value'),11);assert.equal(data('cycle_b_value'),8);
assert.equal(data('cycle_a_count'),1);assert.equal(data('cycle_b_count'),1);
assert.equal(data('cycle_b_vector_observed'),220,'v128 forward call works during peer constructor');
const vectorCheck=processLoader.symbol(cycle,storeString('cycle_vector_check'));
assert.equal(table.get(word(tableAddress,vectorCheck))(),220,'v128 arguments stay within Wasm across libraries');
console.log(`Process loader SIMD model wasm${bits}: v128 forward constructor and cross-module calls pass; not Linux bridge acceptance`);
assert.equal(data('cycle_a_observed'),8);assert.equal(data('cycle_b_observed'),3);
assert.equal(pointerAt('cycle_a_saved'),BigInt(address('cycle_b_value')));
assert.equal(pointerAt('cycle_b_saved'),BigInt(address('cycle_a_value')));
const aStep=processLoader.symbol(cycle,storeString('cycle_a_step'));
const bStep=processLoader.symbol(cycle,storeString('cycle_b_step'));
assert.equal(pointerAt('cycle_a_function'),BigInt(bStep));assert.equal(pointerAt('cycle_b_function'),BigInt(aStep));
assert.equal(table.get(word(tableAddress,aStep))(2),13);assert.equal(table.get(word(tableAddress,bStep))(2),10);
const cyclePeer=processLoader.open(storeString(basename(cycleBFile)),2|4);
assert.notEqual(cyclePeer,word(memoryAddress,0));
assert.equal(processLoader.symbol(cyclePeer,storeString('cycle_a_value')),word(memoryAddress,address('cycle_a_value')));
assert.equal(data('cycle_a_count'),1);assert.equal(data('cycle_b_count'),1);
console.log(`Process loader cyclic model wasm${bits}: mutual NEEDED, relocated peer constructors, canonical pointers and reused instances pass; not Linux bridge acceptance`);
const starting=processLoader.open(storeString('start.wasm'),2);
assert.notEqual(starting,word(memoryAddress,0),'load module with reentrant start lookup');
const entry=processLoader.symbol(starting,storeString('entry'));
const moduleSlot=table.get(word(tableAddress,entry))();
assert.equal(table.get(word(tableAddress,moduleSlot))(),99,'main dlsym must not overwrite new module element');
assert.equal(table.get(word(tableAddress,fromStart))(2),42,'new main pointer remains callable');
assert.notEqual(BigInt(fromStart),BigInt(moduleSlot),'publication and main pointer slots are disjoint');
assert.equal(processLoader.symbol(word(memoryAddress,0),unaddressedPointer),fromStart,'later lookup preserves canonical identity');
console.log(`Process loader start model wasm${bits}: reentrant main dlsym preserves module elements and canonical pointers pass; not Linux bridge acceptance`);
const retained=live.size;
assert.equal(processLoader.open(missingPointer,2),word(memoryAddress,0));
assert.equal(processLoader.open(badPointer,2),word(memoryAddress,0));
assert.equal(live.size,retained,'ordinary failures release C buffers and path allocations');
assert.equal(processLoader.open(rootPointer,2),handle,'ordinary failures preserve live object group');
assert.equal(processLoader.valid(handle),1);assert.equal(processLoader.valid(word(memoryAddress,0)),0);
assert.throws(()=>processLoader.open(controlPointer,2),error=>error===control,'exit/exec is never converted into recoverable dlerror');
assert.equal(live.size,retained+1,'after exit/exec the old libc must not be called to free old-context paths');
console.log(`Process loader model wasm${bits}: ordered search, hard/opened-file rejection, aliases, scopes, reuse, read cleanup, reentry guard and control transfer pass; not Linux bridge acceptance`);
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
        sources = (
            Path(__file__).resolve().parents[1] / "sources/distro/distro/dynamic-loader"
        )
        (directory / "bootstrap").mkdir(exist_ok=True)
        for name, output, dependency in (
            ("a", directory / "bootstrap" / f"cycle-a{bits}.wasm", None),
            (
                "b",
                directory / f"cycle-b{bits}.wasm",
                directory / "bootstrap" / f"cycle-a{bits}.wasm",
            ),
            ("a", directory / f"cycle-a{bits}.wasm", directory / f"cycle-b{bits}.wasm"),
        ):
            subprocess.run(
                [
                    args.clang,
                    f"--target=wasm{bits}",
                    "-nostdlib",
                    "-O2",
                    "-fPIC",
                    "-shared",
                    "-msimd128",
                    "-matomics",
                    "-mbulk-memory",
                    "-Wl,--shared-memory,--no-entry,--import-memory,--import-table",
                    "-Wl,--unresolved-symbols=import-dynamic,--export-all,--export=__wasm_call_ctors",
                    f"-Wl,--max-memory={4294967296 if bits == 32 else 17179869184}",
                    f"-Wl,-soname,cycle-{name}{bits}.wasm",
                    str(sources / f"cycle-{name}.c"),
                    *([str(dependency)] if dependency else []),
                    "-o",
                    str(output),
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
                str(directory / f"cycle-a{bits}.wasm"),
                str(directory / f"cycle-b{bits}.wasm"),
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
                str(directory / f"cycle-a{bits}.wasm"),
                str(directory / f"cycle-b{bits}.wasm"),
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
