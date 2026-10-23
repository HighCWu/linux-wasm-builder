#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual cancellation/restorer bodies in tiny Wasm; not Linux scheduling proof."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"


def function(source, signature):
    start = source.index(signature)
    begin = source.index("{", start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


cancel = (MUSL / "src/thread/pthread_cancel.c").read_text()
restore = (MUSL / "src/signal/wasm32/restore.c").read_text()
recipe = (MUSL / "arch/wasm32/arch.mak").read_text()
assert "obj/src/thread/pthread_cancel.o obj/src/thread/pthread_cancel.lo" in recipe
bodies = function(cancel, "long __cancel()\n{")
bodies += function(cancel, "static __attribute__((noinline)) long wasm_cancellable_syscall(")
bodies += function(cancel, "long __syscall_cp_c(syscall_arg_t nr,")
bodies += function(cancel, "static void _sigaddset(")
bodies += function(cancel, "static void cancel_handler(")
bodies += function(restore, "hidden void __restore(uintptr_t fn, int sig)")
bodies += function(restore, "hidden void __restore_rt(uintptr_t fn, int sig)")
old = bodies.replace("longjmp(self->wasm_interrupted_cancelpoint, 1);", "(void)0;")
assert old != bodies
unbracketed = bodies.replace("self->wasm_cancelpoint = 0;", "self->wasm_cancelpoint = point;")
assert unbracketed != bodies
prefix = r'''
typedef __UINTPTR_TYPE__ uintptr_t;
typedef long syscall_arg_t;
typedef struct { unsigned long __bits[16]; } sigset_t;
typedef struct { int unused; } siginfo_t;
typedef struct { void *ss_sp; int ss_flags; __SIZE_TYPE__ ss_size; } stack_t;
typedef struct { stack_t uc_stack; sigset_t uc_sigmask; } ucontext_t;
struct pthread { int cancel, canceldisable, cancelasync;
    void *volatile wasm_cancelpoint, *volatile wasm_interrupted_cancelpoint; };
typedef struct pthread *pthread_t;
typedef unsigned long long jmp_buf[6];
int setjmp(jmp_buf) __attribute__((returns_twice));
_Noreturn void longjmp(jmp_buf,int);
static struct pthread state;
static int mode, completed, exited, inside_syscall, abi_value=1;
#define hidden
#define PTHREAD_CANCEL_ENABLE 0
#define PTHREAD_CANCEL_DISABLE 1
#define PTHREAD_CANCELED ((void *)-1)
#define ECANCELED 125
#define ENOSYS 38
#define SYS_close 57
#define SIGCANCEL 33
#define SIG_SETMASK 2
#define __pthread_self() (&state)
#define a_barrier() __asm__ volatile("" ::: "memory")
static void pthread_exit(void *p) {(void)p;exited++;__builtin_trap();}
static int pthread_sigmask(int how,const sigset_t *s,void *o) {(void)how;(void)s;(void)o;return 0;}
static int __wasm_signal_cancel_abi(void) {return abi_value;}
static int __wasm_copy_siginfo(siginfo_t *p) {(void)p;return 0;}
static int __wasm_copy_signal_frame(stack_t *s,sigset_t *p) {(void)s;(void)p;return 0;}
static int __wasm_finish_signal_frame(const stack_t *s,const sigset_t *p) {(void)s;(void)p;return 0;}
static long __syscall(long,long,long,long,long,long,long);
void __restore_rt(uintptr_t,int);
void __restore(uintptr_t,int);
'''
suffix = r'''
void *malloc(__SIZE_TYPE__ size) {
    static unsigned long long storage[4096];static __SIZE_TYPE__ used;
    size=(size+15)&-(__SIZE_TYPE__)16;
    if(size>sizeof storage-used)__builtin_trap();
    void *p=(unsigned char *)storage+used;used+=size;return p;
}
void free(void *p) {(void)p;}
void *memset(void *p,int v,__SIZE_TYPE__ n) {
    unsigned char *b=p;for (__SIZE_TYPE__ i=0;i<n;i++)b[i]=v;return p;
}
static void nested(int sig) {
    (void)sig;
    if (mode==5) __syscall_cp_c(63,0,0,0,0,0,0);
    else {state.cancel=1;__restore_rt((uintptr_t)cancel_handler,SIGCANCEL);}
    completed=1;
}
static void nested_info(int sig,siginfo_t *info,void *ctx) {(void)info;(void)ctx;nested(sig);}
static long __syscall(long nr,long a,long b,long c,long d,long e,long f) {
    (void)nr;(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;
    inside_syscall++;
    if (inside_syscall==1 && mode==4) __restore((uintptr_t)nested,10);
    else if (inside_syscall==1 && mode==6) __restore_rt((uintptr_t)nested_info,10);
    else if (inside_syscall==1 && mode==5) __restore((uintptr_t)nested,10);
    else {state.cancel=1;__restore_rt((uintptr_t)cancel_handler,SIGCANCEL);}
    inside_syscall--;
    return 7;
}
int run(int scenario) {
    state=(struct pthread){0};completed=exited=inside_syscall=0;mode=scenario;abi_value=1;
    if (mode==2) state.canceldisable=PTHREAD_CANCEL_DISABLE;
    if (mode==8) state.canceldisable=2;
    if (mode==7) abi_value=0;
    long result=mode==0 ? __syscall(63,0,0,0,0,0,0) :
        __syscall_cp_c(mode==3 ? SYS_close : 63,0,0,0,0,0,0);
    return (int)result;
}
int finished(void) {return completed;}
int canceled(void) {return exited;}
int interrupted(void) {return inside_syscall;}
'''
compilers = os.environ.get("WASM_CANCEL_COMPILERS", "clang-22").split()
assert compilers
with tempfile.TemporaryDirectory(prefix="wasm-cancel-") as tmp:
    work = Path(tmp)
    (work / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates, text=True, capture_output=True, check=True)
    (work / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (work / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    for cc in compilers:
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-std=c99", "-nostdinc", "-I", tmp]
            for path in ("arch/wasm32", "arch/generic", "src/include", "src/internal", "include"):
                flags += ["-I", str(MUSL / path)]
            flags += ["-isystem", str(Path(resource) / "include")]
            for path in ("src/thread/pthread_cancel.c", "src/signal/wasm32/restore.c"):
                subprocess.run([*flags, "-fsyntax-only", str(MUSL / path)], check=True)
                subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", str(MUSL / path), "-o", "/dev/null"], check=True)
            workload = str(ROOT / "sources/distro/distro/toolchain-smoke/deferred-cancel.c")
            subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", workload], check=True)
            subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", workload, "-o", "/dev/null"], check=True)
            trampoline = work / "restorer.wasm"
            subprocess.run([*flags, "-O2", "-ffreestanding", "-nostdlib", "-Wl,--no-entry", "-Wl,--allow-undefined",
                            str(MUSL / "src/signal/wasm32/restore.c"), "-o", str(trampoline)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const module=await WebAssembly.compile(readFileSync(process.argv[1]));
assert(WebAssembly.Module.exports(module).some(x=>x.name==='__wasm_signal_handler_v2' && x.kind==='function'));
''', str(trampoline)], check=True)
            helpers = []
            tag_source = work / "tag.s"
            tag_source.write_text(f".tagtype __c_longjmp i{bits}\n.globl __c_longjmp\n__c_longjmp:\n")
            tag_object = work / "tag.o"
            subprocess.run([cc, f"--target=wasm{bits}", "-c", str(tag_source), "-o", str(tag_object)], check=True)
            helpers.append(str(tag_object))
            for name in ("setjmp", "wasm_longjmp"):
                obj = work / (name + ".o")
                sjlj = ["-mexception-handling", "-mllvm", "-wasm-enable-eh", "-mllvm", "-wasm-enable-sjlj"] if name == "wasm_longjmp" else []
                subprocess.run([*flags, *sjlj, "-O2", "-ffreestanding", "-c",
                                str(MUSL / ("src/setjmp/wasm32/" + name + ".c")), "-o", str(obj)], check=True)
                helpers.append(str(obj))
            for label, body in (("fixed", bodies), ("old", old), ("unbracketed", unbracketed)):
                source, binary = work / "model.c", work / "model.wasm"
                source.write_text(prefix + body + suffix)
                subprocess.run([*flags, "-mexception-handling", "-mllvm", "-wasm-enable-eh", "-mllvm", "-wasm-enable-sjlj", "-ffreestanding", "-nostdlib", "-O2", "-Wl,--no-entry", "-Wl,--import-undefined",
                                *["-Wl,--export=" + name for name in ("run", "finished", "canceled", "interrupted")],
                                str(source), *helpers, "-o", str(binary)], check=True)
                subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const module=await WebAssembly.compile(readFileSync(process.argv[1]));
assert.deepEqual(WebAssembly.Module.imports(module),[], 'native Wasm SjLj, never emscripten JS shims');
const label=process.argv[2];
const fresh=async()=> (await WebAssembly.instantiate(module)).exports;
for(const scenario of [0,2,3,7]) {
  const a=await fresh();assert.equal(a.run(scenario),scenario===7?-38:7);assert.equal(a.canceled(),0);
}
let a=await fresh();
if(label==='old') {
  assert.throws(()=>a.run(1),WebAssembly.RuntimeError);
  assert.equal(a.interrupted(),0,'old cancellation reaches only the post-syscall check, too late for a restarted blocking call');
} else {
  assert.throws(()=>a.run(1),WebAssembly.RuntimeError);assert.equal(a.interrupted(),1,'cancel before restart');
}
for(const scenario of [4,6]) {
  a=await fresh();assert.throws(()=>a.run(scenario),WebAssembly.RuntimeError);
  assert.equal(a.finished(),label==='unbracketed'?0:1,'ordinary handler is outside the interrupted cancellation point');
}
a=await fresh();assert.throws(()=>a.run(5),WebAssembly.RuntimeError);assert.equal(a.finished(),0);
if(label!=='old') {a=await fresh();assert.equal(a.run(8),-125);assert.equal(a.canceled(),0);}
''', str(binary), label, str(bits)], check=True)
            print(f"{cc} wasm{bits}: actual cancellation/restorer bodies, close/disabled/raw/nested cases and negative controls passed")
