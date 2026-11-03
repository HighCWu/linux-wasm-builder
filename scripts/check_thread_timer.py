#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute musl's real timer worker and TLS reset; modeled delivery, not Linux scheduling."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
timer = (MUSL / "src/time/timer_create.c").read_text()
reset = (MUSL / "src/env/__reset_tls.c").read_text()
recipe = (MUSL / "arch/wasm32/arch.mak").read_text()
assert "obj/src/time/timer_create.o obj/src/time/timer_create.lo" in recipe
thread = (MUSL / "src/thread/pthread_create.c").read_text()


def function(signature):
    start = thread.index(signature)
    end = thread.index("\n}\n", start) + 3
    return thread[start:end]


fixture = (
    timer
    + r"""
static struct pthread state;
struct __libc __libc;
static uintptr_t dtv[1];
static int callbacks, resets_bad, events, error_path, sem_failures;
static _Thread_local volatile int native_value = 41;
__attribute__((export_name("probe_tp"))) uintptr_t probe_tp(void) { return (uintptr_t)&state; }
int sem_init(sem_t *s,int shared,unsigned value) { (void)s;(void)shared;(void)value;return 0; }
int sem_wait(sem_t *s) { (void)s;if(error_path && !sem_failures++){errno=EAGAIN;return -1;}return 0; }
int sem_post(sem_t *s) { (void)s; return 0; }
int pthread_attr_init(pthread_attr_t *a) { (void)a;return 0; }
int pthread_attr_setdetachstate(pthread_attr_t *a,int d) { (void)a;(void)d;return 0; }
int pthread_create(pthread_t *t,const pthread_attr_t *a,void *(*f)(void *),void *p) {
 (void)a;(void)f;(void)p;*t=&state;state.tid=2;state.cancel=0;return 0;
}
int __libc_sigaction(int s,const struct sigaction *a,struct sigaction *b) { (void)s;(void)a;(void)b;return 0; }
void __block_app_sigs(void *s) { (void)s; }
void __restore_sigs(void *s) { (void)s; }
int sigwaitinfo(const sigset_t *set, siginfo_t *si) {
 (void)set;
 si->si_code = events++ < 3 ? SI_TIMER : SI_USER;
 if(si->si_code!=SI_TIMER) state.timer_id=INT_MIN|7;
 return SIGTIMER;
}
static void notify(union sigval value) {
 if(value.sival_int!=37 || native_value!=41 || state.cancel ||
    state.cancelasync || state.canceldisable) resets_bad=1;
 native_value=91;callbacks++;
 state.cancel=state.cancelasync=state.canceldisable=1;
}
__attribute__((export_name("check"))) int check(void) {
 state.dtv=dtv;state.timer_id=7;
 struct sigevent event={.sigev_notify_function=notify,.sigev_value.sival_int=37};
 struct start_args args={.sev=&event};
 start(&args);
 return callbacks!=3 || resets_bad || native_value!=41 || state.cancelbuf ||
        state.cancel || state.cancelasync || state.canceldisable;
}
__attribute__((export_name("error_check"))) int error_check(void) {
 struct sigevent event={.sigev_notify=SIGEV_THREAD,.sigev_notify_function=notify};
 timer_t result;
 error_path=1;errno=0;
 int rc=timer_create((clockid_t)0x40000000,&event,&result);
 return rc!=-1 || errno!=EINVAL || sem_failures<2;
}
"""
    + function("void __do_cleanup_push(")
    + function("void __do_cleanup_pop(")
)
support = r"""
typedef __SIZE_TYPE__ size_t;
static unsigned char heap[16384] __attribute__((aligned(16)));
static size_t used;
void *malloc(size_t n) {
 n=(n+15)&~(size_t)15;if(n>sizeof(heap)-used)__builtin_trap();
 void *p=heap+used;used+=n;return p;
}
void free(void *p) { (void)p; }
void *memcpy(void *to,const void *from,size_t n) {
 unsigned char *d=to;const unsigned char *s=from;for(size_t i=0;i<n;i++)d[i]=s[i];return to;
}
void *memset(void *to,int value,size_t n) {
 unsigned char *d=to;for(size_t i=0;i<n;i++)d[i]=value;return to;
}
"""
runner = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const [file,bits,mode]=process.argv.slice(2),wide=bits==='64',word=n=>wide?BigInt(n):n;
const module=await WebAssembly.compile(readFileSync(file));
assert(WebAssembly.Module.imports(module).every(i=>['env.memory','linux.syscall','linux.get_thread_area'].includes(`${i.module}.${i.name}`)), 'no Emscripten JS exception shims');
const memory=new WebAssembly.Memory({initial:word(8),maximum:word(16),shared:true,address:wide?'i64':'i32'});
let instance,deletes=0;
instance=await WebAssembly.instantiate(module,{env:{memory},linux:{
 get_thread_area(){return instance.exports.probe_tp();},
 syscall(n,id){
  if(Number(n)===135)return word(0);
  if(Number(n)===107){assert.equal(Number(id),0x40000000);return word(-22);}
  assert.equal(Number(n),111);assert.equal(Number(id),7);deletes++;return word(0);
 }
}});
instance.exports.__wasm_init_tls(word(4*65536));
if(mode==='missing-lowering'){
 assert.throws(()=>instance.exports.check(),WebAssembly.RuntimeError);
 assert.equal(deletes,0,'the original cleanup never reaches kernel timer deletion');
}else{
 assert.equal(instance.exports.check(),mode==='missing-native-reset'?1:0);
 assert.equal(deletes,1);
 assert.equal(instance.exports.error_check(),mode==='lost-timer-errno'?1:0,'kernel error survives helper handshake');
}
"""
with tempfile.TemporaryDirectory(prefix="thread-timer-") as tmp:
    path = Path(tmp)
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    (path / "bits/alltypes.h").write_text(
        subprocess.check_output(
            ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
            input=templates,
            text=True,
        )
    )
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    (path / "fixture.c").write_text(fixture)
    (path / "support.c").write_text(support)
    (path / "run.mjs").write_text(runner)
    for cc in os.environ.get("WASM_THREAD_TIMER_COMPILERS", "clang-22").split():
        resource = subprocess.check_output(
            [cc, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            flags = [
                cc,
                f"--target=wasm{bits}",
                "-O2",
                "-ffreestanding",
                "-nostdlib",
                "-nostdinc",
                "-matomics",
                "-mbulk-memory",
                "-D_XOPEN_SOURCE=700",
            ]
            for directory in (
                MUSL / "src/include",
                MUSL / "src/internal",
                path,
                MUSL / "arch/wasm32",
                MUSL / "arch/generic",
                MUSL / "include",
            ):
                flags += ["-I", str(directory)]
            flags += ["-isystem", resource + "/include"]
            public = [cc, f"--target=wasm{bits}", "-O2", "-nostdinc", "-I", tmp]
            for directory in ("arch/wasm32", "arch/generic", "include"):
                public += ["-I", str(MUSL / directory)]
            public += ["-isystem", resource + "/include", "-Wall", "-Wextra", "-Werror"]
            consumer = ROOT / "sources/distro/distro/thread-timer/runtime.c"
            subprocess.run(
                public
                + [
                    "-matomics",
                    "-mbulk-memory",
                    "-mllvm",
                    "-wasm-enable-sjlj",
                    "-c",
                    str(consumer),
                    "-o",
                    str(path / "consumer.o"),
                ],
                check=True,
            )
            for options, source in (
                (public, consumer),
                (flags, MUSL / "src/time/timer_create.c"),
                (flags, MUSL / "src/env/__reset_tls.c"),
            ):
                subprocess.run(
                    options
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
            tag = path / "tag.s"
            tag.write_text(
                f".tagtype __c_longjmp i{bits}\n.globl __c_longjmp\n__c_longjmp:\n"
            )
            subprocess.run(
                [cc, f"--target=wasm{bits}", "-c", str(tag), "-o", str(path / "tag.o")],
                check=True,
            )
            for mode in (
                "normal",
                "missing-lowering",
                "missing-native-reset",
                "lost-timer-errno",
            ):
                changed = (
                    fixture
                    if mode != "lost-timer-errno"
                    else fixture.replace("return __syscall_ret(r);", "return -1;")
                )
                assert mode != "lost-timer-errno" or changed != fixture
                (path / "fixture.c").write_text(changed)
                (path / "reset.c").write_text(
                    reset
                    if mode != "missing-native-reset"
                    else reset.replace(
                        "__wasm_init_tls((void *)__builtin_wasm_tls_base());", ""
                    )
                )
                subprocess.run(
                    flags
                    + (
                        []
                        if mode == "missing-lowering"
                        else ["-mllvm", "-wasm-enable-sjlj"]
                    )
                    + ["-c", str(path / "fixture.c"), "-o", str(path / "timer.o")],
                    check=True,
                )
                subprocess.run(
                    flags
                    + [
                        "-mllvm",
                        "-wasm-enable-sjlj",
                        "-c",
                        str(MUSL / "src/setjmp/wasm32/wasm_longjmp.c"),
                        "-o",
                        str(path / "throw.o"),
                    ],
                    check=True,
                )
                binary = path / "timer.wasm"
                subprocess.run(
                    flags
                    + [
                        str(path / "timer.o"),
                        str(path / "throw.o"),
                        str(path / "tag.o"),
                        str(path / "reset.c"),
                        str(path / "support.c"),
                        str(MUSL / "src/setjmp/wasm32/setjmp.c"),
                        str(MUSL / "src/setjmp/wasm32/longjmp.c"),
                        str(MUSL / "src/thread/pthread_cleanup_push.c"),
                        str(MUSL / "src/internal/syscall_ret.c"),
                        str(MUSL / "src/errno/__errno_location.c"),
                        "-Wl,--no-entry,--import-memory,--shared-memory,--max-memory=1048576,--export=__wasm_init_tls",
                        "-o",
                        str(binary),
                    ],
                    check=True,
                )
                subprocess.run(
                    ["node", str(path / "run.mjs"), str(binary), str(bits), mode],
                    check=True,
                )
            print(
                f"{cc} wasm{bits}: actual timer worker SjLj/TLS, kernel error preservation and three negative controls pass; not Linux timer delivery"
            )
