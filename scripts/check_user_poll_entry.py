#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual private kernel checkpoint body, modeled entry/IRQ work; not signal acceptance."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = Path(os.environ.get("WASM_POLL_KERNEL_SOURCE_ROOT", ROOT / "sources/linux"))
text = (LINUX / "arch/wasm/kernel/syscall.c").read_text()
body = text[text.index('__attribute__((export_name("user_poll_v1")))') :]
body = body[: body.index("\n}\n") + 3]
model = r"""
#include "arch/wasm/include/uapi/asm/sigcontext.h"
#define noinstr
#define EAGAIN 11
#define false 0
static struct pt_regs registers;
static struct { int in_user_context; } thread;
static int irq, instrument, entered, left, work, timers, remote;
static int stack_error, stale_restart, syscall_events, order;
#define current ((void *)0)
#define current_pt_regs() (&registers)
#define current_thread_info() (&thread)
#define REQUIRE(test) do { if(!(test)) __builtin_trap(); } while(0)
static void raw_local_irq_disable(void) { irq=0; }
static void enter_from_user_mode(struct pt_regs *regs) {
 REQUIRE(!irq&&thread.in_user_context&&regs==&registers);
 thread.in_user_context=0;entered++;
}
static void instrumentation_begin(void) { REQUIRE(!instrument&&!thread.in_user_context);instrument=1; }
static void instrumentation_end(void) { REQUIRE(instrument&&!irq);instrument=0; }
static int wasm_user_signal_v1_stack_pointer(unsigned long *sp) {
 REQUIRE(instrument&&!irq);*sp=196608;return stack_error;
}
static void rcu_note_context_switch(int preempt) {
 REQUIRE(instrument&&!irq&&!preempt&&registers.user_sp==196608);order=1;
}
static void local_irq_enable(void) { REQUIRE(order==1);irq=1; }
static void local_irq_disable(void) { REQUIRE(irq&&order==3);irq=0; }
static void wasm_timer_check(void) { REQUIRE(irq&&order==1);timers++;order=2; }
static void wasm_service_remote_request(void *task) { REQUIRE(!task&&irq&&order==2);remote++;order=3; }
static void irqentry_exit_to_user_mode_prepare(struct pt_regs *regs) {
 REQUIRE(!irq&&instrument&&!thread.in_user_context&&order==3);
 work++;
 stale_restart=regs->syscall_nr!=-1||regs->restart_syscall_nr!=-1||regs->syscall_return!=0;
 /* Model a handler's nested syscall touching the task's shared pt_regs. */
 regs->syscall_nr=172;regs->syscall_return=999;regs->user_sp=327680;
}
static void syscall_exit_to_user_mode_work(struct pt_regs *regs) {
 syscall_events++;irqentry_exit_to_user_mode_prepare(regs);
}
static void exit_to_user_mode(void) {
 REQUIRE(!irq&&!instrument&&!thread.in_user_context);
 thread.in_user_context=1;left++;
}
"""
checks = r"""
__attribute__((export_name("check"))) int check(void) {
 struct pt_regs original;
 for(int scenario=0;scenario<3;scenario++) {
  registers.syscall_nr=64;registers.restart_syscall_nr=219;
  registers.syscall_return=-512;registers.user_mode=1;registers.user_sp=131072;
  for(int i=0;i<6;i++)registers.syscall_args[i]=71+i;
  original=registers;
  irq=1;instrument=entered=left=work=timers=remote=order=stale_restart=syscall_events=0;
  thread.in_user_context=scenario!=2;stack_error=scenario==1?-14:0;
  int result=wasm_user_poll_v1();
  if(result!=(scenario==2?-11:stack_error))return 1;
  if(registers.syscall_nr!=original.syscall_nr||registers.syscall_return!=original.syscall_return||
     registers.restart_syscall_nr!=original.restart_syscall_nr||registers.user_sp!=original.user_sp||
     registers.user_mode!=original.user_mode)return 2;
  for(int i=0;i<6;i++)if(registers.syscall_args[i]!=original.syscall_args[i])return 2;
  if(stale_restart)return 3;
  if(syscall_events)return 4;
  if(scenario==2) {if(entered||left||work||timers||remote||!irq||thread.in_user_context)return 5;}
  else if(entered!=1||left!=1||irq||!thread.in_user_context||instrument||
          work!=(scenario==0)||timers!=work||remote!=work)return 6;
 }
 return 0;
}
"""
runner = r"""
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[2]));
assert.equal(instance.exports.check(),Number(process.argv[3]));
"""
controls = {
    "normal": (body, 0),
    "stale-return": (
        body.replace("regs->syscall_return = 0;", "/* stale restart result */"),
        3,
    ),
    "syscall-work": (
        body.replace(
            "irqentry_exit_to_user_mode_prepare(regs);",
            "syscall_exit_to_user_mode_work(regs);",
        ),
        4,
    ),
}
assert all(source != body for name, (source, _) in controls.items() if name != "normal")
with tempfile.TemporaryDirectory(prefix="user-poll-entry-") as tmp:
    path = Path(tmp)
    (path / "run.mjs").write_text(runner)
    for cc in os.environ.get("WASM_POLL_ENTRY_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            flags = [
                cc,
                f"--target=wasm{bits}",
                "-O2",
                "-mbulk-memory",
                "-nostdlib",
                "-I",
                str(LINUX),
            ]
            for name, (source, expected) in controls.items():
                (path / "entry.c").write_text(model + source + checks)
                binary = path / "entry.wasm"
                subprocess.run(
                    flags
                    + [str(path / "entry.c"), "-Wl,--no-entry", "-o", str(binary)],
                    check=True,
                )
                subprocess.run(
                    ["node", str(path / "run.mjs"), str(binary), str(expected)],
                    check=True,
                )
                if name == "normal":
                    subprocess.run(
                        flags
                        + [
                            "--analyze",
                            "-Xanalyzer",
                            "-analyzer-werror",
                            str(path / "entry.c"),
                            "-o",
                            "/dev/null",
                        ],
                        check=True,
                    )
            print(
                f"{cc} wasm{bits}: actual checkpoint preserves regs and entry/IRQ order; bad stack/kernel phase refuse; stale restart and syscall-work controls rejected; modeled Linux work only"
            )
