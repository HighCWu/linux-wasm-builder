#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute the actual phase helper/hooks and IRQ bridge, not a Linux boot."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ARCH = Path(os.environ.get("WASM_CONTEXT_ARCH", ROOT / "sources/linux/arch/wasm"))


def without_includes(text):
    return "\n".join(line for line in text.splitlines() if not line.startswith("#include"))


context = without_includes((ARCH / "kernel/user_context.c").read_text())
hooks = without_includes((ARCH / "include/asm/entry-common.h").read_text())
irq = (ARCH / "kernel/irq.c").read_text()
start = irq.index("static void run_irq(")
irq = irq[start:irq.index("\n}\n", start) + 3]
process = (ARCH / "kernel/process.c").read_text()
assert "wasm_set_user_context(true);\n\twasm_user_call();\n\twasm_set_user_context(false);" in process
assert "task_thread_info(dst)->in_user_context = false;" in process
prefix = r'''
#define true 1
#define false 0
#define NULL ((void *)0)
#define EINVAL 22
#define bool _Bool
#define __always_inline inline __attribute__((always_inline))
#define BUG_ON(bad) do { if (bad) __builtin_trap(); } while (0)
typedef unsigned int irq_hw_number_t;
struct pt_regs { int user_mode; };
struct thread_info { bool in_user_context; };
static struct thread_info info;
static struct pt_regs regs;
static struct pt_regs *irq_regs;
static int irq_enabled=1, ticks, user_ticks, entries, exits;
#define current_thread_info() (&info)
#define current_pt_regs() (&regs)
#define user_mode(r) ((r)->user_mode)
#define local_irq_save(flags) do { flags=irq_enabled; irq_enabled=0; } while (0)
#define local_irq_restore(flags) do { irq_enabled=(flags); } while (0)
#define raw_local_irq_save local_irq_save
#define raw_local_irq_restore local_irq_restore
'''
generic = r'''
/* Strict stand-ins reject unmatched transitions; actual Linux generic helpers
 * are not linked by this small architecture model. */
static void enter_from_user_mode(struct pt_regs *r) {
    BUG_ON(irq_enabled || !info.in_user_context);
    arch_enter_from_user_mode(r); entries++;
}
static void exit_to_user_mode(void) {
    BUG_ON(irq_enabled || info.in_user_context);
    arch_exit_to_user_mode(); exits++;
}
static struct pt_regs *set_irq_regs(struct pt_regs *r) {
    struct pt_regs *old=irq_regs; irq_regs=r; return old;
}
static void irq_enter(void) { BUG_ON(irq_enabled || info.in_user_context); }
static void irq_exit(void) { BUG_ON(irq_enabled || info.in_user_context); }
static void generic_handle_domain_irq(void *domain, irq_hw_number_t hwirq) {
    BUG_ON(domain || hwirq!=2 || info.in_user_context || !irq_regs);
    ticks++; user_ticks+=user_mode(irq_regs);
}
'''
suffix = r'''
__attribute__((export_name("interrupt"))) void interrupt(void) { run_irq(2); }
__attribute__((export_name("mask"))) void mask(int enabled) { irq_enabled=enabled; }
__attribute__((export_name("stats"))) int stats(int field) {
    switch(field) {
    case 0:return ticks; case 1:return user_ticks; case 2:return entries;
    case 3:return exits; case 4:return irq_enabled; case 5:return !!irq_regs;
    default:__builtin_trap();
    }
}
'''
with tempfile.TemporaryDirectory(prefix="wasm-user-context-") as tmp:
    unit, binary = Path(tmp) / "context.c", Path(tmp) / "context.wasm"
    unit.write_text(prefix + hooks + generic + context + irq + suffix)
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            subprocess.run([cc, f"--target=wasm{bits}", "-Os", "-nostdlib", "-ffreestanding",
                            "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                            "-Wl,--no-entry", str(unit), "-o", str(binary)], check=True)
            subprocess.run([cc, f"--target=wasm{bits}", "--analyze", "-ffreestanding",
                            "-Xanalyzer", "-analyzer-output=text", str(unit)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const {call_kernel_entry,call_user_callback} = await import(pathToFileURL(process.argv[3]));
const {instance:{exports:e}} = await WebAssembly.instantiate(readFileSync(process.argv[1]));
const address = process.argv[2] === '64' ? 'i64' : 'i32';
assert.equal(e.user_context_v1(2),0);
e.interrupt();
assert.equal(e.stats(1),0,'kernel IRQ is not a user tick');
assert.equal(e.user_context_v1(1),0,'first user entry performs only a phase change');
e.interrupt();
assert.equal(e.user_context_v1(2),1,'IRQ restores interrupted user phase');
assert.equal(e.stats(1),1);
assert.equal(e.stats(5),0,'IRQ register lifetime ends before returning');
const jump=new WebAssembly.Exception(new WebAssembly.Tag({parameters:[]}),[]);
for (const failure of [undefined,jump]) {
  const invoke=()=>call_kernel_entry(e,address,()=>{
    e.user_context_v1(0); // stand-in syscall generic entry
    return call_user_callback(e,address,()=>{
      assert.equal(e.user_context_v1(2),1);
      call_kernel_entry(e,address,()=>{
        assert.equal(e.user_context_v1(2),0,'leaf access runs in kernel context');
        e.interrupt();
      },true);
      assert.equal(e.user_context_v1(2),1);
      if(failure) throw failure;
      return 17;
    });
  });
  if(failure) assert.throws(invoke,error=>error===failure);
  else assert.equal(invoke(),17);
  assert.equal(e.user_context_v1(2),1,'live outer user caller restored');
}
assert.equal(e.stats(4),1,'transition helpers preserve IRQ state');
assert.equal(e.stats(3),e.stats(2)+1,'exactly one active user phase');
e.user_context_v1(0);
assert.equal(e.stats(3),e.stats(2),'all generic transitions balanced');
for(const enabled of [0,1]) {
  e.mask(enabled);
  e.user_context_v1(1);
  assert.equal(e.stats(4),enabled);
  e.user_context_v1(0);
  assert.equal(e.stats(4),enabled);
}
assert.equal(e.user_context_v1(3),-22,'invalid internal mode leaves state intact');
assert.equal(e.user_context_v1(2),0);
''', str(binary), str(bits), str(ROOT / "sources/distro/packages/kernel/src/signal-stack.ts")], check=True)
            unpaired = irq.replace("\tif (user_mode(&regs))\n\t\tenter_from_user_mode(&regs);", "")
            unpaired = unpaired.replace("\tif (user_mode(&regs))\n\t\texit_to_user_mode();", "")
            assert unpaired != irq
            unit.write_text(prefix + hooks + generic + context + unpaired + suffix)
            subprocess.run([cc, f"--target=wasm{bits}", "-Os", "-nostdlib", "-ffreestanding",
                            "-Wl,--no-entry", str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance:{exports:e}}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
e.interrupt();
e.user_context_v1(1);
assert.throws(()=>e.interrupt(),WebAssembly.RuntimeError,'unpaired IRQ entry must be detected');
''', str(binary)], check=True)
            unit.write_text(prefix + hooks + generic + context + irq + suffix)
            print(f"{cc} wasm{bits}: actual phase/IRQ bodies and nested JS restoration passed")
