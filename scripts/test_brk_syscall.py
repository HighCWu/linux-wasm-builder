#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute actual kernel/libc brk bodies in separate tiny Wasm memories.

Locks, limits and capacity are modeled; this is not Linux boot acceptance.
"""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
LINUX = Path(os.environ.get("WASM_BRK_KERNEL_SOURCE_ROOT", ROOT / "sources/linux"))
KERNEL = r"""
#include <stdint.h>
#include <limits.h>
typedef unsigned long long u64;
#define ENOMEM 12
#define EFAULT 14
#define ENOSPC 28
#define RLIM_INFINITY ULONG_MAX
#define RLIMIT_AS 0
#define RLIMIT_DATA 1
#define PAGE_SIZE 65536UL
#ifdef __wasm64__
#define TASK_SIZE (1UL << 34)
#else
#define TASK_SIZE UINT32_MAX
#endif
struct mm_struct {
 unsigned long start_brk,start_data,end_data,brk;
 int arg_lock;
};
struct task_struct { struct mm_struct *mm; };
static struct mm_struct map;
static struct task_struct task={&map};
#define current (&task)
static unsigned long as_limit=ULONG_MAX,data_limit=ULONG_MAX;
#define rlimit(which) ((which)==RLIMIT_AS?as_limit:data_limit)
static int depth;
static void spin_lock(int *lock) {
 if(*lock||depth)__builtin_trap();*lock=1;depth++;
}
static void spin_unlock(int *lock) {
 if(!*lock||depth!=1)__builtin_trap();*lock=0;depth--;
}
__attribute__((export_name("configure")))
void configure(unsigned long as,unsigned long data) { as_limit=as;data_limit=data; }
__attribute__((export_name("recorded_break")))
unsigned long recorded_break(void) { return map.brk; }
__attribute__((export_name("lock_depth")))
int lock_depth(void) { return depth; }
__attribute__((import_module("user_brk_v1"),import_name("layout")))
int wasm_user_brk_v1_layout(u64 *fields);
__attribute__((import_module("user_brk_v1"),import_name("update")))
unsigned long wasm_user_brk_v1_update(unsigned long requested);
#define SYSCALL_DEFINE1(name,type,arg) \
 __attribute__((export_name("kernel_brk"))) long kernel_brk(type arg)
"""
RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [kernelFile,userFile,bits,helper]=process.argv.slice(2);
const {user_brk_layout,user_brk_update}=await import(pathToFileURL(helper));
const wide=bits==='64',kind=wide?'i64':'i32';
const word=n=>wide?BigInt(n):Number(n);
const unsigned=n=>wide?BigInt.asUintN(64,n):BigInt(n>>>0);
const kernelModule=await WebAssembly.compile(readFileSync(kernelFile));
const userModule=await WebAssembly.compile(readFileSync(userFile));
let kernel,user,unsupported=false,invalid=false,reenter=false,nested=0;
kernel=(await WebAssembly.instantiate(kernelModule,{user_brk_v1:{
 layout(to){assert.equal(kernel.exports.lock_depth(),0);
  if(unsupported)return -38;
  if(invalid)return -14;
  return user_brk_layout(user.exports,user.exports.memory,kind,kernel.exports.memory,to);},
 update(requested){assert.equal(kernel.exports.lock_depth(),0);
  const result=user_brk_update(user.exports,kind,requested);
  if(reenter&&requested!==word(0)){
   reenter=false;nested=unsigned(requested)+64n;
   assert.equal(unsigned(kernel.exports.kernel_brk(word(nested))),nested);}
  return result;}
}})).exports;
// The imports above use one object shape for readability with real instances.
kernel={exports:kernel};
user=await WebAssembly.instantiate(userModule,{linux:{syscall(n,a){
 assert.equal(n,word(214),'normal libc uses the standard brk syscall number');
 return kernel.exports.kernel_brk(a);
}}});
user=user instanceof WebAssembly.Instance?user:user.instance;
const u=user.exports,k=kernel.exports;
u.model_configure(word(1),word(8));k.configure(word(-1),word(-1));
const initial=unsigned(u.sbrk(word(0)));
assert(initial>0n&&initial<=65536n);
assert.equal(unsigned(k.kernel_brk(word(0))),initial);
const layoutPointer=unsigned(u.__wasm_brk_layout_v1());
const slot=wide?8:4;
const layout=new DataView(u.memory.buffer,Number(layoutPointer),3*slot);
const minimum=wide?layout.getBigUint64(0,true):BigInt(layout.getUint32(0,true));
assert.equal(minimum,initial);
unsupported=true;assert.equal(k.kernel_brk(word(0)),word(-38));unsupported=false;
invalid=true;assert.equal(k.kernel_brk(word(0)),word(-14));invalid=false;
assert.equal(unsigned(k.recorded_break()),initial);
assert.equal(k.lock_depth(),0);
u.model_set_errno(7);
k.configure(word(initial),word(-1));
assert.equal(unsigned(k.kernel_brk(word(initial+1n))),initial,'AS rounds to real Wasm pages');
assert.equal(u.last_error(),7,'refused raw brk does not modify libc errno');
assert.equal(unsigned(u.sbrk(word(0))),initial);
assert.equal(u.sbrk(word(1)),word(-1));assert.equal(u.last_error(),12);
assert.equal(u.lock_state(),0,'API and callback locks are distinct and released');
k.configure(word(-1),word(0));u.model_set_errno(7);
assert.equal(unsigned(k.kernel_brk(word(initial+1n))),initial,'DATA includes static data and heap growth');
assert.equal(u.last_error(),7);
assert.equal(u.brk(word(initial+1n)),-1);assert.equal(u.last_error(),12);
assert.equal(unsigned(k.kernel_brk(word(initial-1n))),initial,'monotonic allocator refuses shrink');
assert.equal(u.sbrk(word(-1)),word(-1));assert.equal(u.lock_state(),0);
k.configure(word(-1),word(-1));
assert.equal(unsigned(u.sbrk(word(65536))),initial);
const grown=initial+65536n;
assert.equal(unsigned(u.sbrk(word(0))),grown);
assert.equal(unsigned(k.recorded_break()),grown);
assert.equal(u.grow_count(),word(1));
u.model_configure(word(2),word(wide?262144:65536));
assert.equal(unsigned(k.kernel_brk(word(-1))),grown,'reserved errno-shaped pointers are not a heap break');
assert.equal(u.grow_count(),word(0),'range rejection precedes even modeled full-capacity growth');
assert.equal(unsigned(u.__wasm_brk_layout_v1()),layoutPointer,'layout remains immutable after growth');
assert.equal(wide?layout.getBigUint64(0,true):BigInt(layout.getUint32(0,true)),minimum);
u.model_configure(word(2),word(2));u.model_set_errno(7);
assert.equal(unsigned(k.kernel_brk(word(grown+65536n))),grown,'actual allocator failure returns old break');
assert.equal(u.last_error(),7,'failed memory.grow callback preserves errno');
u.model_configure(word(2),word(8));reenter=true;
const first=grown+16n;
assert.equal(unsigned(k.kernel_brk(word(first))),first);
assert.equal(unsigned(k.recorded_break()),nested,'late older frame cannot lower published break');
assert.equal(unsigned(k.kernel_brk(word(0))),nested);
assert.equal(u.lock_state(),0);assert.equal(k.lock_depth(),0);
console.log(`brk wasm${bits}: real syscall-routed libc, separate memories, AS/DATA, raw errno, failure recovery and reentrant publication pass; not Linux boot acceptance`);
"""

with tempfile.TemporaryDirectory(prefix="wasm-brk-syscall-") as tmp:
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
    (path / "model.h").write_text(
        "#include <stddef.h>\nsize_t brk_model_size(int);\nsize_t brk_model_grow(int,size_t);\n"
    )
    real = (LINUX / "arch/wasm/kernel/syscall.c").read_text()
    real = real.split("/* WASM_BRK_SYSCALL_BEGIN */", 1)[1].split(
        "/* WASM_BRK_SYSCALL_END */", 1
    )[0]
    check = (LINUX / "include/linux/mm.h").read_text()
    check = check[check.index("static inline int check_data_rlimit(") :]
    check = check[: check.index("\n}\n") + 3]
    (path / "kernel.c").write_text(KERNEL + check + real)
    (path / "run.mjs").write_text(RUNNER)
    includes = [
        path,
        MUSL / "arch/wasm32",
        MUSL / "arch/generic",
        MUSL / "src/include",
        MUSL / "src/internal",
        MUSL / "include",
    ]
    for cc in os.environ.get("WASM_BRK_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            kernel = path / "kernel.wasm"
            user = path / "user.wasm"
            subprocess.run(
                [
                    cc,
                    f"--target=wasm{bits}",
                    "-O2",
                    "-nostdlib",
                    "-ffreestanding",
                    "-Wl,--no-entry",
                    "-Wl,--export-memory",
                    str(path / "kernel.c"),
                    "-o",
                    str(kernel),
                ],
                check=True,
            )
            flags = [
                cc,
                f"--target=wasm{bits}",
                "-nostdinc",
                *[arg for directory in includes for arg in ["-I", str(directory)]],
                "-include",
                str(path / "model.h"),
                "-D__builtin_wasm_memory_size=brk_model_size",
                "-D__builtin_wasm_memory_grow=brk_model_grow",
                "-DWASM_BRK_SYSCALL=1",
            ]
            subprocess.run(
                [
                    *flags,
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    str(MUSL / "src/linux/brk.c"),
                    "-o",
                    "/dev/null",
                ],
                check=True,
            )
            exports = [
                "brk",
                "sbrk",
                "model_configure",
                "model_set_errno",
                "last_error",
                "lock_state",
                "grow_count",
            ]
            subprocess.run(
                [
                    *flags,
                    "-O2",
                    "-nostdlib",
                    "-ffreestanding",
                    "-Wl,--no-entry",
                    "-Wl,-z,stack-size=8192",
                    "-Wl,--export-memory",
                    *["-Wl,--export=" + name for name in exports],
                    str(MUSL / "src/linux/brk.c"),
                    str(ROOT / "scripts/fixtures/brk_model.c"),
                    "-o",
                    str(user),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "node",
                    str(path / "run.mjs"),
                    str(kernel),
                    str(user),
                    str(bits),
                    str(ROOT / "sources/distro/packages/kernel/src/user-brk.ts"),
                ],
                check=True,
            )
