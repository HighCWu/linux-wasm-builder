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
    return "\n".join(line for line in text.splitlines() if not line.startswith("#include")) + "\n"


context = without_includes((ARCH / "kernel/user_context.c").read_text())
hooks = without_includes((ARCH / "include/asm/entry-common.h").read_text())
ptrace = without_includes((ARCH / "include/uapi/asm/ptrace.h").read_text())
sigcontext = without_includes((ARCH / "include/uapi/asm/sigcontext.h").read_text())
irq = (ARCH / "kernel/irq.c").read_text()
start = irq.rfind("\n", 0, irq.index("run_irq(")) + 1
irq = irq[start:irq.index("\n}\n", start) + 3]
process = (ARCH / "kernel/process.c").read_text()
assert "wasm_run_user();" in process
assert "wasm_set_user_context(true);\n\twasm_user_call();\n\twasm_set_user_context(false);" in context
assert "task_thread_info(dst)->in_user_context = false;" in process
assert "wasm_check_user_context_abi();" in (ARCH / "kernel/setup.c").read_text()
assert "failed = wasm_run_user_signal(" in (ARCH / "kernel/signal.c").read_text()
abi_decl = "int wasm_import(user_context_v1, abi)(void);"
assert abi_decl in (ARCH / "include/asm/wasm_imports.h").read_text()
prefix = r'''
#define true 1
#define false 0
#define NULL ((void *)0)
#define EINVAL 22
#define bool _Bool
#define noinstr __attribute__((no_instrument_function,noinline))
#define __init
#define panic(...) __builtin_trap()
#define wasm_import(ns,name) __attribute__((import_module(#ns),import_name(#name))) wasm_##ns##_##name
/* Kernel inline definitions permit unused architecture-only helpers. */
#define inline inline __attribute__((unused))
#define __always_inline inline __attribute__((always_inline))
#define BUG_ON(bad) do { if (bad) __builtin_trap(); } while (0)
#define BUG() __builtin_trap()
#define barrier_data(ptr) __asm__ __volatile__("" : : "r"(ptr) : "memory")
typedef unsigned int irq_hw_number_t;
typedef unsigned int u32;
typedef unsigned long uintptr_t;
struct thread_info { bool in_user_context; };
static struct thread_info info;
static struct pt_regs regs;
static struct pt_regs *irq_regs;
static int irq_enabled=1, ticks, user_ticks, entries, exits;
static unsigned long arch_local_save_flags(void) { return irq_enabled; }
#define current_thread_info() (&info)
#define current_pt_regs() (&regs)
#define local_irq_save(flags) do { flags=irq_enabled; irq_enabled=0; } while (0)
#define local_irq_restore(flags) do { irq_enabled=(flags); } while (0)
#define raw_local_irq_save local_irq_save
#define raw_local_irq_restore local_irq_restore
'''
prefix = sigcontext + prefix
prefix += abi_decl + "\n"
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
static void instrumentation_begin(void) { BUG_ON(info.in_user_context); }
static void instrumentation_end(void) { BUG_ON(info.in_user_context); }
__attribute__((optnone)) void *memset(void *to, int value, __SIZE_TYPE__ count) {
    BUG_ON(info.in_user_context);
    unsigned char *bytes=to;
    for (__SIZE_TYPE__ i=0;i<count;i++) bytes[i]=value;
    return to;
}
static void wasm_user_call(void) { BUG_ON(!info.in_user_context); }
static int wasm_user_signal_v1_call_handler(uintptr_t trampoline, uintptr_t fn, u32 sig,
        unsigned long sp, unsigned long base, unsigned long size, u32 flags) {
    BUG_ON(!info.in_user_context || trampoline!=1 || fn!=2 || sig!=10 ||
           sp!=4096 || base!=2048 || size!=2048 || flags!=3);
    return 17;
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
    unit.write_text(prefix + ptrace + hooks + generic + context + irq + suffix)
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            subprocess.run([cc, f"--target=wasm{bits}", "-Os", "-nostdlib", "-ffreestanding",
                            "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                            "-Wl,--no-entry", "-Wl,--export=wasm_run_user", "-Wl,--export=wasm_run_user_signal",
                            "-Wl,--export=wasm_check_user_context_abi", str(unit), "-o", str(binary)], check=True)
            subprocess.run([cc, f"--target=wasm{bits}", "--analyze", "-ffreestanding",
                            "-Xanalyzer", "-analyzer-output=text", str(unit)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const {call_kernel_entry,call_user_callback} = await import(pathToFileURL(process.argv[3]));
const {instance:{exports:e}} = await WebAssembly.instantiate(readFileSync(process.argv[1]));
const address = process.argv[2] === '64' ? 'i64' : 'i32';
const p=n=>address==='i64'?BigInt(n):n;
assert.equal(e.user_context_v1(2),0);
e.wasm_check_user_context_abi(); // default configuration has no mandatory import
e.wasm_run_user();
assert.equal(e.user_context_v1(2),0);
assert.equal(e.wasm_run_user_signal(p(1),p(2),10,p(4096),p(2048),p(2048),3),17);
assert.equal(e.user_context_v1(2),0,'signal returns to its live kernel caller');
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
            unit.write_text(prefix + ptrace + hooks + generic + context + unpaired + suffix)
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
            unit.write_text(prefix + ptrace + hooks + generic + context + irq + suffix)
            subprocess.run([cc, f"--target=wasm{bits}", "-DCONFIG_CONTEXT_TRACKING_USER=1",
                            "-Os", "-nostdlib", "-ffreestanding", "-Wl,--no-entry",
                            "-Wl,--export=wasm_check_user_context_abi", str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const {user_context_imports,user_module_imports_supported}=await import(pathToFileURL(process.argv[2]));
const module=new WebAssembly.Module(readFileSync(process.argv[1]));
assert.equal(user_module_imports_supported(module),false,'host ABI is not an application import');
assert.throws(()=>new WebAssembly.Instance(module,{}),TypeError);
assert.throws(()=>new WebAssembly.Instance(module,{user_context_v1:{}}),WebAssembly.LinkError);
for(const version of [0,1,2]) {
  const {exports:e}=new WebAssembly.Instance(module,{user_context_v1:{abi:()=>version}});
  if(version===1) e.wasm_check_user_context_abi();
  else assert.throws(()=>e.wasm_check_user_context_abi(),WebAssembly.RuntimeError);
}
new WebAssembly.Instance(module,{user_context_v1:user_context_imports()}).exports.wasm_check_user_context_abi();
''', str(binary), str(ROOT / "sources/distro/packages/kernel/src/wasm.ts")], check=True)
            unit.write_text(prefix + ptrace + hooks + generic + context + irq + suffix)
            early_clear = irq.replace("\tlocal_irq_save(flags);", "\tmemset(&regs, 0, sizeof(regs));\n\tregs.user_mode = was_user;\n\tlocal_irq_save(flags);", 1)
            assert early_clear != irq
            unit.write_text(prefix + ptrace + hooks + generic + context + early_clear + suffix)
            subprocess.run([cc, f"--target=wasm{bits}", "-Os", "-nostdlib", "-ffreestanding",
                            "-Wl,--no-entry", str(unit), "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance:{exports:e}}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
e.user_context_v1(1);
assert.throws(()=>e.interrupt(),WebAssembly.RuntimeError,'early memset before RCU/context entry must be detected');
''', str(binary)], check=True)
            unit.write_text(prefix + ptrace + hooks + generic + context + irq + suffix)
            broken_ptrace = ptrace.replace("((regs)->user_mode)", "(regs->user_mode)")
            assert broken_ptrace != ptrace
            unit.write_text(prefix + broken_ptrace + hooks + generic + context + irq + suffix)
            refused = subprocess.run([cc, f"--target=wasm{bits}", "-ffreestanding", "-fsyntax-only",
                                      str(unit)], capture_output=True, text=True)
            assert refused.returncode != 0 and "member reference type" in refused.stderr, refused.stderr
            unit.write_text(prefix + ptrace + hooks + generic + context + irq + suffix)
            print(f"{cc} wasm{bits}: actual phase/IRQ bodies and nested JS restoration passed")
