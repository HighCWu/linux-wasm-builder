#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual Wasm syscall dispatcher with nested imports, not target ptrace acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("WASM_SYSCALL_SOURCE", ROOT / "sources/linux/arch/wasm/kernel/syscall.c")).read_text()
header = Path(os.environ.get("WASM_SIGCONTEXT_SOURCE", ROOT / "sources/linux/arch/wasm/include/uapi/asm/sigcontext.h")).read_text()
begin = source.index('__attribute__((export_name("syscall")))')
body = source[begin:source.index("\n}\n", begin) + 3]
snapshot = """else if (nr >= 0) {
			struct pt_regs entered = *regs;
			long result;"""
assert snapshot in body
old = body.replace("\t\t\tstruct pt_regs entered = *regs;\n", "").replace("\t\t\t*regs = entered;\n", "")
irq_begin = source.index('__attribute__((export_name("callback_irq_save_v1")))')
irq_end = source.index("\n}\n", source.index("wasm_callback_irq_restore_v1(", irq_begin)) + 3
irq_body = source[irq_begin:irq_end]
prefix = header + r'''
__attribute__((optnone)) void *memcpy(void *destination, const void *source, __SIZE_TYPE__ length) {
    unsigned char *to = destination;
    const unsigned char *from = source;
    for (__SIZE_TYPE__ i=0;i<length;i++) to[i]=from[i];
    return destination;
}
#define false 0
#define true 1
#define bool _Bool
#define noinstr __attribute__((no_instrument_function))
#define ENOSYS 38
#define __NR_sigaltstack 99
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define current ((void *)1)
static struct pt_regs registers;
static int depth, mode, sp_error, restart_pending, irq, user_phase, enters, stack_reads, quiescent;
static struct pt_regs *current_pt_regs(void) { return &registers; }
static void local_irq_disable(void) { irq=0; }
static void local_irq_enable(void) { if(user_phase) __builtin_trap(); irq=1; }
static unsigned long arch_local_save_flags(void) { return irq; }
static void restore_irq(unsigned long flags) { irq=flags; }
#define local_irq_restore(flags) do { \
    _Static_assert(__builtin_types_compatible_p(__typeof__(flags),unsigned long),"native IRQ flag width"); \
    restore_irq(flags); \
} while (0)
static void rcu_note_context_switch(int preempt) {
    if (preempt || user_phase || irq) __builtin_trap();
    quiescent++;
}
static void instrumentation_begin(void) { if(user_phase) __builtin_trap(); }
static void instrumentation_end(void) { if(user_phase) __builtin_trap(); }
static void enter_from_user_mode(struct pt_regs *regs) {
    (void)regs;
    if(!user_phase || irq) __builtin_trap();
    user_phase=0;
    enters++;
}
static int wasm_user_signal_v1_stack_pointer(unsigned long *sp) {
    if(user_phase || !irq) __builtin_trap();
    stack_reads++;
#if __SIZEOF_LONG__ == 8
    *sp = 0x100000100UL + depth * 65536UL;
#else
    *sp = 0x80000100UL + depth * 65536UL;
#endif
    return sp_error;
}
static long syscall_enter_from_user_mode_work(struct pt_regs *regs, long nr) {
    if(user_phase || !irq) __builtin_trap();
    depth++;
    irq=1;
    if (nr == 0) regs->syscall_args[5] += 9; /* model ptrace edit */
    if (mode == 3) { regs->syscall_return = -13; return -1; }
    return mode == 1 && nr == 0 ? 2 : nr;
}
static void wasm_timer_check(void) {}
static void wasm_service_remote_request(void *task) { (void)task; }
__attribute__((import_module("model"), import_name("nested"))) extern void nested(void);
__attribute__((import_module("model"), import_name("exit")))
extern void observe(long,long,long,long,long,long,long,long,long,int,int,int);
static void syscall_exit_to_user_mode(struct pt_regs *r) {
    if(user_phase || !irq) __builtin_trap();
    observe(r->syscall_nr,r->user_sp,r->syscall_args[0],r->syscall_args[1],r->syscall_args[2],
            r->syscall_args[3],r->syscall_args[4],r->syscall_args[5],r->syscall_return,r->user_mode,depth,irq);
    if (r->syscall_return == -512) r->restart_syscall_nr = r->syscall_nr;
    depth--;
    irq=0;
    user_phase=1;
}
static long outer(const struct pt_regs *r) {
    (void)r; user_phase=1; nested(); user_phase=0;
    if (mode == 2 && restart_pending) { restart_pending = 0; return -512; }
    return 101;
}
static long inner(const struct pt_regs *r) { return (long)r->syscall_args[0]; }
static long redirected(const struct pt_regs *r) {
    (void)r; user_phase=1; nested(); user_phase=0; return 202;
}
static long (*syscall_table[])(const struct pt_regs *) = {outer,inner,redirected};
void configure(int m, int e) {
    mode=m; sp_error=e; restart_pending=1; depth=0; irq=0; user_phase=1;
    enters=stack_reads=quiescent=0;
}
int stats(int field) {
    switch(field) {
    case 0:return enters; case 1:return stack_reads;
    case 2:return quiescent; case 3:return user_phase;
    default:__builtin_trap();
    }
}
'''
with tempfile.TemporaryDirectory(prefix="syscall-reentry-") as tmp:
    unit, binary = Path(tmp) / "dispatch.c", Path(tmp) / "dispatch.wasm"
    for bits in (32, 64):
        for implementation, fixed in ((body, True), (old, False)):
            unit.write_text(prefix + implementation + irq_body)
            subprocess.run([os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}", "-O2",
                            "-nostdlib", "-ffreestanding", "-Wl,--no-entry", "-Wl,--export=configure", "-Wl,--export=stats", "-Wl,--export=__stack_pointer",
                            str(unit), "-o", str(binary)], check=True)
            subprocess.run([os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}", "--analyze",
                            "-ffreestanding", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null",
                            str(unit)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const {call_kernel_entry} = await import(pathToFileURL(process.argv[4]));
const wide = process.argv[2] === '64', fixed = process.argv[3] === 'True';
const p = n => wide ? BigInt(n) : Number(n)|0;
const base = wide ? 0x100000100n : (0x80000100|0);
let api, events;
({instance:{exports:api}} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {model: {
  nested() {
    for (const value of [17,-14]) {
      assert.equal(call_kernel_entry(api,wide ? 'i64' : 'i32',() =>
        api.syscall(p(1),p(value),p(20),p(30),p(40),p(50),p(60))), p(value));
    }
  },
  exit(...state) { events.push(state); },
}}));
for (const mode of [0,1,2]) {
  api.configure(mode,0); events=[];
  const result = call_kernel_entry(api,wide ? 'i64' : 'i32',() =>
    api.syscall(p(0),p(10),p(11),p(12),p(13),p(14),p(15)));
  assert.equal(result,p(mode === 1 ? 202 : mode === 2 && !fixed ? -14 : 101));
  assert.equal(api.stats(0),events.length,'every exit, including restart, has a fresh entry');
  assert.equal(api.stats(2),events.length,'RCU reporting follows each entry');
  assert.equal(api.stats(1),events.length-(mode === 2 ? 1 : 0),
    'restart preserves the original stack/ptrace arguments, without importing again');
  assert.equal(api.stats(3),1,'final return remains in user phase');
  const outer = events.filter(e => e[10] === 1);
  assert.equal(outer.length,mode === 2 ? 2 : 1);
  for (let index=0;index<outer.length;index++) {
    const [nr,sp,...rest] = outer[index];
    assert.equal(rest[9],1,'live outer kernel callback resumes with its enabled IRQ state');
    if (fixed) {
      assert.equal(nr,p(mode === 1 ? 2 : 0));
      assert.equal(sp,base);
      assert.deepEqual(rest.slice(0,6),[10,11,12,13,14,24+index*9].map(p));
      assert.equal(rest[7],0,'outer return processing remains in kernel mode');
    } else {
      assert.equal(nr,p(1),'old dispatcher exposes inner number');
      assert.equal(sp,p(BigInt.asUintN(wide ? 64 : 32,BigInt(base))+65536n));
      assert.deepEqual(rest.slice(0,6),[-14,20,30,40,50,60].map(p));
    }
  }
}
for (const [number,error,expected] of [[98,0,-38],[99,-14,-14],[-2,0,-38],[-1,0,-38]]) {
  api.configure(0,error); events=[];
  assert.equal(call_kernel_entry(api,wide ? 'i64' : 'i32',() =>
    api.syscall(p(number),p(0),p(0),p(0),p(0),p(0),p(0))),p(expected));
  assert.equal(events.length,1,'direct error paths remain bounded');
}
api.configure(3,0); events=[];
assert.equal(call_kernel_entry(api,wide ? 'i64' : 'i32',() =>
  api.syscall(p(0),p(10),p(11),p(12),p(13),p(14),p(15))),p(-13),
  'tracer result must survive skip');
assert.equal(events.length,1,'skipped syscall must not invoke handler or nested imports');
assert.equal(events[0][0],p(-1));
''', str(binary), str(bits), str(fixed), str(ROOT / "sources/distro/packages/kernel/src/signal-stack.ts")], check=True)
        print(f"wasm{bits}: nested frame, ptrace edits, signed results, restart target and old-clobber control passed")
        controls = {
            "early-stack": body.replace("\tfor (;;) {", "\tsp_error = wasm_user_signal_v1_stack_pointer(&sp);\n\tfor (;;) {", 1),
            "early-rcu": body.replace("\t\tenter_from_user_mode(regs);", "\t\trcu_note_context_switch(false);\n\t\tenter_from_user_mode(regs);", 1),
            "missing-restart-entry": body.replace("\t\tenter_from_user_mode(regs);", "\t\tif (first_entry) enter_from_user_mode(regs);", 1),
        }
        for name, broken in controls.items():
            assert broken != body
            unit.write_text(prefix + broken + irq_body)
            subprocess.run([os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}", "-O2",
                            "-nostdlib", "-ffreestanding", "-Wl,--no-entry", "-Wl,--export=configure",
                            str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const wide=process.argv[2]==='64', p=n=>wide?BigInt(n):n;
let e;
({instance:{exports:e}}=await WebAssembly.instantiate(readFileSync(process.argv[1]),{model:{
  nested(){ e.syscall(p(1),p(17),p(0),p(0),p(0),p(0),p(0)); },
  exit(){},
}}));
e.configure(process.argv[3]==='missing-restart-entry'?2:0,0);
assert.throws(()=>e.syscall(p(0),p(0),p(0),p(0),p(0),p(0),p(0)),
  WebAssembly.RuntimeError,process.argv[3]+' must not pass context admission');
''', str(binary), str(bits), name], check=True)
        print(f"wasm{bits}: early stack/RCU and missing restart entry controls rejected")
