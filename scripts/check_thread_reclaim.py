#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact detached-exit body in tiny Wasm; poison freed stacks before exit."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
source = (MUSL / "src/thread/__unmapself.c").read_text()
marker = source.index("\n#else\n")
old = source[:marker] + r'''
#else
void __unmapself(void *base, size_t size) {
    (void)size;
    __libc_free(base);
    __syscall(SYS_exit, 0);
}
#endif
'''
assert source != old
thread = (MUSL / "src/thread/pthread_create.c").read_text()
begin = thread.index("#ifdef __wasm__", thread.index("/* Last, unlink"))
end = thread.index("\n\tself->next->prev", begin)
counter = thread[begin:end]
assert "--libc.threads_minus_1;" in counter
header = r'''
#ifndef MODEL_H
#define MODEL_H
typedef __SIZE_TYPE__ size_t;
typedef __UINTPTR_TYPE__ uintptr_t;
#define DEFAULT_STACK_SIZE 131072
#define SYS_exit 93
void __libc_free(void *);
long __syscall(long,long);
#endif
'''
fixture = r'''
#include "pthread_impl.h"
#if __SIZEOF_POINTER__ == 8
__asm__(".globaltype __stack_pointer, i64\n");
#else
__asm__(".globaltype __stack_pointer, i32\n");
#endif
__attribute__((import_module("model"),import_name("release"))) void release(void *);
__attribute__((import_module("model"),import_name("exit"))) void stop(void *,long,long);
void __libc_free(void *p) {release(p);}
__attribute__((noinline)) long __syscall(long nr,long status) {
    volatile unsigned char scratch[512];
    for (unsigned i=0;i<sizeof scratch;i++) scratch[i]=0x5a;
    stop((void *)scratch,nr,status);
    return 0;
}
static unsigned char dying_stack[2][65536] __attribute__((aligned(16)));
void __unmapself(void *,size_t);
void run(int index) {
    void *base=dying_stack[index], *top=dying_stack[index]+65536;
    __asm__ volatile("local.get %0\nglobal.set __stack_pointer"::"r"(top):"memory");
    __unmapself(base,65536);
    __builtin_trap();
}
uintptr_t heap(int index) {return (uintptr_t)dying_stack[index];}
struct {int threads_minus_1,need_locks;} libc;
void transition(int count) {libc.threads_minus_1=count;libc.need_locks=1;
COUNTER
}
int remaining(void) {return libc.threads_minus_1;}
int locking(void) {return libc.need_locks;}
'''
compilers = os.environ.get("WASM_RECLAIM_COMPILERS", "clang clang-22").split()
assert compilers
with tempfile.TemporaryDirectory(prefix="wasm-thread-reclaim-") as tmp:
    work = Path(tmp)
    abi = work / "abi"
    (abi / "bits").mkdir(parents=True)
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (abi / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (abi / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    (work / "pthread_impl.h").write_text(header)
    for name in ("atomic.h", "syscall.h", "dynlink.h"):
        (work / name).write_text("/* bounded model uses no other private definitions */\n")
    for cc in compilers:
        resource = subprocess.check_output([cc,"-print-resource-dir"],text=True).strip()
        for bits in (32,64):
            real_flags = [cc,f"--target=wasm{bits}","-std=c99","-nostdinc","-D_XOPEN_SOURCE=700","-I",str(abi)]
            for path in ("arch/wasm32","arch/generic","src/include","src/internal","include"):
                real_flags += ["-I",str(MUSL / path)]
            real_flags += ["-isystem",str(Path(resource) / "include")]
            for path in ("src/thread/__unmapself.c","src/thread/pthread_create.c"):
                subprocess.run([*real_flags,"-fsyntax-only",str(MUSL / path)],check=True)
                # Existing generic stack assignment is deliberately overwritten
                # by wasm_tls in pthread_create; keep memory checkers enabled.
                checks = ["-Xanalyzer","-analyzer-disable-checker","-Xanalyzer","deadcode.DeadStores"] if path.endswith("pthread_create.c") else []
                subprocess.run([*real_flags,"--analyze",*checks,"-Xanalyzer","-analyzer-werror",str(MUSL / path),"-o","/dev/null"],check=True)
            workload = str(ROOT / "sources/distro/distro/toolchain-smoke/thread-reclaim.c")
            public_flags = [cc,f"--target=wasm{bits}","-std=c99","-nostdinc","-I",str(abi)]
            for path in ("arch/wasm32","arch/generic","include"):
                public_flags += ["-I",str(MUSL / path)]
            public_flags += ["-isystem",str(Path(resource) / "include")]
            subprocess.run([*public_flags,"-fsyntax-only","-Wall","-Wextra","-Werror",workload],check=True)
            subprocess.run([*public_flags,"--analyze","-Xanalyzer","-analyzer-werror",workload,"-o","/dev/null"],check=True)
            old_counter = "if (!--libc.threads_minus_1) libc.need_locks=-1;"
            for label, actual, count_body, optimization in (("fixed",source,counter,"-O2"), ("old",old,old_counter,"-O2"),
                    ("fixed-Os",source,counter,"-Os"), ("old-Os",old,old_counter,"-Os")):
                unit, helper, binary = work / "exit.c",work / "probe.c",work / "exit.wasm"
                unit.write_text(actual)
                helper.write_text(fixture.replace("COUNTER",count_body))
                flags = [cc,f"--target=wasm{bits}",optimization,"-ffreestanding","-nostdlib","-I",tmp]
                subprocess.run([*flags,"--analyze","-Xanalyzer","-analyzer-werror",str(unit),"-o","/dev/null"],check=True)
                subprocess.run([*flags,"-Wl,--no-entry", "-Wl,--export=__stack_pointer",
                                *["-Wl,--export="+name for name in ("run","heap","transition","remaining","locking")],
                                str(unit),str(helper),"-o",str(binary)],check=True)
                subprocess.run(["node","--input-type=module","-e",r'''
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const module=await WebAssembly.compile(readFileSync(process.argv[1]));
const old=process.argv[2].startsWith('old');let a,base,freed,exited;
const end=Symbol('SYS_exit never returns to user C');
a=(await WebAssembly.instantiate(module,{model:{release(p){
  assert.equal(Number(p),base);freed++;
  const sp=Number(a.__stack_pointer.value);
  assert.equal(sp>base && sp<=base+65536,old,'switch before publishing old stack for reuse');
  new Uint8Array(a.memory.buffer,base,65536).fill(0xa5);
},exit(p,nr,status){
  assert.equal(Number(nr),93);assert.equal(Number(status),0);exited++;
  const sp=Number(p);assert.equal(sp>=base && sp<base+65536,old,'subsequent call frame must not use freed memory');
  throw end;
}}})).exports;
for(let index=0;index<2;index++) {
  base=Number(a.heap(index));freed=exited=0;
  assert.throws(()=>a.run(index),e=>e===end);
  assert.equal(freed,1);assert.equal(exited,1);
  const untouched=new Uint8Array(a.memory.buffer,base,65536).every(v=>v===0xa5);
  assert.equal(untouched,!old,'old code writes an actual C frame after free');
}
a.transition(1);assert.equal(a.remaining(),0);assert.equal(a.locking(),old?-1:1);
a.transition(2);assert.equal(a.remaining(),1);assert.equal(a.locking(),1);
''',str(binary),label],check=True)
            print(f"{cc} wasm{bits}: exact exit stack switch, immediate reuse poison, old failure and lock transition passed")
    native = "#include <assert.h>\nstruct {int threads_minus_1,need_locks;} libc;\nvoid transition(void){\n"+counter+"\n}\nint main(void){libc.threads_minus_1=1;libc.need_locks=1;transition();assert(!libc.threads_minus_1 && libc.need_locks==-1);}\n"
    (work / "native.c").write_text(native)
    for cc in ("gcc","clang"):
        subprocess.run([cc,"-O2","-Wall","-Wextra","-Werror",str(work / "native.c"),"-o",str(work / "native")],check=True)
        subprocess.run([str(work / "native")],check=True)
        subprocess.run([cc,"-O2","-pthread","-Wall","-Wextra","-Werror",workload,"-o",str(work / "thread-reclaim")],check=True)
        result = subprocess.run([str(work / "thread-reclaim")],capture_output=True,text=True,timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count(" pass\n") == 2 and result.stdout.count("::vm-test::pass") == 1
