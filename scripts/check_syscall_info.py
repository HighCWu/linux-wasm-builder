#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual generic syscall-info helpers and Wasm accessors, not target ptrace acceptance."""
import os
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
KERNEL = Path(os.environ.get("WASM_SYSCALL_INFO_ROOT", ROOT / "sources/linux"))


def read(path):
    local = KERNEL / path
    if local.is_file():
        return local.read_text()
    if "WASM_SYSCALL_INFO_ROOT" in os.environ:
        raise FileNotFoundError("missing exact pinned syscall-info model input: " + path)
    return subprocess.run(["git", "-C", str(KERNEL), "show", "HEAD:" + path],
                          capture_output=True, text=True, check=True).stdout


def no_includes(text):
    return "\n".join(line for line in text.splitlines() if not line.startswith("#include")) + "\n"


ptrace = read("kernel/ptrace.c")
assert "ptrace_get_syscall_info(struct task_struct *child" in ptrace, \
    "expected exact generic kernel/ptrace.c, not the architecture ptrace adapter"
start = ptrace.index("#ifdef CONFIG_HAVE_ARCH_SYSCALL_INFO")
end = ptrace.index("#endif /* CONFIG_HAVE_ARCH_SYSCALL_INFO */", start)
helpers = ptrace[start:end] + "\n#endif\n"
assert "task_user_regset_view" not in helpers
assert "default y if HAVE_ARCH_TRACEHOOK" in read("arch/Kconfig")
assert "select HAVE_ARCH_SYSCALL_INFO" in read("arch/wasm/Kconfig")
assert "select HAVE_ARCH_TRACEHOOK" not in read("arch/wasm/Kconfig")
assert "obj-$(CONFIG_HAVE_ARCH_SYSCALL_INFO) += syscall.o" in read("lib/Makefile")
assert read("fs/proc/base.c").count("#ifdef CONFIG_HAVE_ARCH_SYSCALL_INFO") == 3
for tracehook, capable in ((False, False), (True, True), (False, True)):
    definitions = (["-DCONFIG_HAVE_ARCH_TRACEHOOK=1"] if tracehook else [])
    definitions += ["-DCONFIG_HAVE_ARCH_SYSCALL_INFO=1"] if capable else []
    for path in ("kernel/ptrace.c", "fs/proc/base.c"):
        processed = subprocess.run(["gcc", "-E", "-P", "-nostdinc", "-x", "c", *definitions, "-"],
                                   input=no_includes(read(path)), capture_output=True, text=True, check=True).stdout
        marker = "ptrace_get_syscall_info" if path == "kernel/ptrace.c" else "proc_pid_syscall"
        assert bool(re.search(r"static\s+int\s+" + marker + r"\s*\(", processed)) == capable, (path, tracehook, capable)
        if path == "kernel/ptrace.c":
            assert bool(re.search(r"static\s+int\s+ptrace_regset\s*\(", processed)) == tracehook

prefix = r'''
typedef unsigned char __u8;
typedef unsigned short __u16;
typedef unsigned int __u32;
typedef int __s32;
typedef unsigned long long __u64;
typedef long long __s64;
typedef _Bool bool;
#define false 0
#define __user
#define NULL ((void *)0)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define IS_ERR_VALUE(v) ((unsigned long)(v) >= (unsigned long)-4095)
#define offsetof(t,m) __builtin_offsetof(t,m)
#define offsetofend(t,m) (offsetof(t,m)+sizeof(((t *)0)->m))
#define min(a,b) ((a)<(b)?(a):(b))
#define EFAULT 14
#define EINVAL 22
#define ERANGE 34
#define SIGTRAP 5
__attribute__((optnone)) void *memcpy(void *to,const void *from,__SIZE_TYPE__ n) {
    unsigned char *d=to; const unsigned char *s=from;
    for (__SIZE_TYPE__ i=0;i<n;i++) d[i]=s[i];
    return to;
}
__attribute__((optnone)) void *memset(void *to,int value,__SIZE_TYPE__ n) {
    unsigned char *d=to;
    for (__SIZE_TYPE__ i=0;i<n;i++) d[i]=value;
    return to;
}
'''
task = r'''
struct siginfo { int si_code; };
struct task_struct { struct pt_regs regs; struct siginfo *last_siginfo; unsigned long ptrace_message; };
#define task_pt_regs(t) (&(t)->regs)
#define instruction_pointer(r) (-1)
#define user_stack_pointer(r) ((r)->user_sp)
static int copy_fault;
static unsigned long copy_to_user(void *to,const void *from,unsigned long n) {
    if (copy_fault) return n;
    memcpy(to,from,n); return 0;
}
#define copy_from_user copy_to_user
'''
driver = r'''
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
int run(void) {
    _Static_assert(sizeof(struct ptrace_syscall_info)==88,"full standard syscall-info layout");
    struct siginfo stop={.si_code=SIGTRAP|0x80};
    struct task_struct child={.last_siginfo=&stop,.ptrace_message=PTRACE_EVENTMSG_SYSCALL_ENTRY};
    struct ptrace_syscall_info info={0};
    child.regs.syscall_nr=178;
    child.regs.user_sp=0x80000100UL;
    for (int i=0;i<6;i++) child.regs.syscall_args[i]=0x80000000UL+i;
    CHECK(ptrace_get_syscall_info(&child,sizeof info,&info)==80);
    CHECK(info.op==PTRACE_SYSCALL_INFO_ENTRY && info.entry.nr==178 && info.arch==0);
    CHECK(info.stack_pointer==0x80000100UL && info.instruction_pointer==(__u64)-1);
    for (int i=0;i<6;i++) CHECK(info.entry.args[i]==0x80000000UL+i);
    info.entry.nr=173;
    for (int i=0;i<6;i++) info.entry.args[i]=100+i;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==0 && child.regs.syscall_nr==173);
    for (int i=0;i<6;i++) CHECK(child.regs.syscall_args[i]==100UL+i);
    info.entry.nr=(__u64)-1; info.entry.args[0]=999;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==0 && child.regs.syscall_nr==-1);
    CHECK(child.regs.syscall_args[0]==100);
    info.entry.nr=1ULL<<32;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==-ERANGE);
    info.entry.nr=178; info.entry.args[0]=1ULL<<32;
#if __SIZEOF_LONG__ == 4
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==-ERANGE);
#else
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==0);
    CHECK(child.regs.syscall_args[0]==1ULL<<32);
#endif
    info.flags=1;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==-EINVAL);
    info.flags=0; info.reserved=1;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==-EINVAL);
    info.reserved=0;
    CHECK(ptrace_set_syscall_info(&child,sizeof info-1,&info)==-EINVAL);
    copy_fault=1;
    CHECK(ptrace_get_syscall_info(&child,sizeof info,&info)==-EFAULT);
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==-EFAULT);
    copy_fault=0;
    child.ptrace_message=PTRACE_EVENTMSG_SYSCALL_EXIT; child.regs.syscall_return=-38;
    CHECK(ptrace_get_syscall_info(&child,sizeof info,&info)==33);
    CHECK(info.op==PTRACE_SYSCALL_INFO_EXIT && info.exit.rval==-38 && info.exit.is_error==1);
    info.exit.rval=42; info.exit.is_error=0;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==0 && child.regs.syscall_return==42);
    info.exit.rval=-13; info.exit.is_error=1;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==0 && child.regs.syscall_return==-13);
    info.op=PTRACE_SYSCALL_INFO_ENTRY;
    CHECK(ptrace_set_syscall_info(&child,sizeof info,&info)==-EINVAL);
    stop.si_code=0;
    CHECK(ptrace_get_syscall_info(&child,sizeof info,&info)==24 && info.op==PTRACE_SYSCALL_INFO_NONE);
    return 0;
}
'''
unit = prefix + no_includes(read("include/uapi/linux/ptrace.h")) + no_includes(read("arch/wasm/include/uapi/asm/sigcontext.h"))
unit += task + no_includes(read("arch/wasm/include/asm/syscall.h"))
unit += "\n#define CONFIG_HAVE_ARCH_SYSCALL_INFO 1\n" + helpers + driver
with tempfile.TemporaryDirectory(prefix="wasm-syscall-info-") as tmp:
    source, binary = Path(tmp) / "info.c", Path(tmp) / "info.wasm"
    source.write_text(unit)
    for cc in os.environ.get("WASM_INFO_COMPILERS", "clang").split():
        for bits in (32, 64):
            flags=[cc, f"--target=wasm{bits}", "-ffreestanding"]
            subprocess.run([*flags,"--analyze","-Xanalyzer","-analyzer-werror",str(source),"-o","/dev/null"],check=True)
            subprocess.run([*flags,"-O2","-nostdlib","-Wl,--no-entry","-Wl,--export=run",str(source),"-o",str(binary)],check=True)
            subprocess.run(["node","--input-type=module","-e",r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
assert.equal(instance.exports.run(),0,'actual syscall-info helper check (C line number on failure)');
''',str(binary)],check=True)
            print(f"{cc} wasm{bits}: actual syscall-info helpers, accessors and rejection paths passed")
