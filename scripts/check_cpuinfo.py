#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact proc formatter and busy-CPU workload; native checks are not Wasm acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("WASM_CPUINFO_SOURCE", ROOT / "sources/linux/arch/wasm/kernel/cpuinfo.c")).read_text()
source = "\n".join(line for line in source.splitlines() if not line.startswith("#include"))
prefix = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <stdbool.h>
#define smp_processor_id() 0
#define smp_call_function_single(cpu,fn,arg,wait) ((void)(cpu),(void)(fn),(void)(arg),(void)(wait),exit(71))
struct seq_file { char buffer[256]; size_t used; };
struct seq_operations {
    void *(*start)(struct seq_file *,loff_t *);
    void *(*next)(struct seq_file *,void *,loff_t *);
    void (*stop)(struct seq_file *,void *);
    int (*show)(struct seq_file *,void *);
};
static int online(int cpu) { return cpu == 0 || cpu == 2 || cpu == 5; }
#define for_each_online_cpu(cpu) for ((cpu)=0;(cpu)<6;(cpu)++) if (online(cpu))
static void seq_printf(struct seq_file *m,const char *format,...) {
    va_list args;
    va_start(args,format);
    int n=vsnprintf(m->buffer+m->used,sizeof(m->buffer)-m->used,format,args);
    va_end(args);
    assert(n>=0 && (size_t)n<sizeof(m->buffer)-m->used);
    m->used+=n;
}
'''
suffix = r'''
int main(void) {
    struct seq_file m={0}; loff_t pos=0;
    void *v=cpuinfo_op.start(&m,&pos);
    assert(v && cpuinfo_op.show(&m,v)==0);
    assert(!strcmp(m.buffer,"processor       : 0\n\nprocessor       : 2\n\nprocessor       : 5\n\n"));
    assert(cpuinfo_op.next(&m,v,&pos)==NULL && pos==1);
    assert(cpuinfo_op.start(&m,&pos)==NULL);
    cpuinfo_op.stop(&m,v);
}
'''
old = r'''
static void percpu_print(void *arg) {
    struct seq_file *m=arg;
    seq_printf(m,"processor       : %d\n",smp_processor_id());
    seq_printf(m,"\n");
}
static int c_show(struct seq_file *m,void *v) {
    int cpu;
    for_each_online_cpu(cpu)
        smp_call_function_single(cpu,percpu_print,m,true);
    return 0;
}
const struct seq_operations cpuinfo_op={.start=c_start,.next=c_next,.stop=c_stop,.show=c_show};
'''
with tempfile.TemporaryDirectory(prefix="wasm-cpuinfo-") as tmp:
    work = Path(tmp)
    # Keep the original iterator in the negative control; replace only formatter.
    start = source.index("static int c_show(")
    end = source.index("static void *c_start", start)
    control = source[:start] + source[end:source.index("const struct seq_operations")] + old
    for cc in ("gcc", "clang"):
        for name, text in (("actual", source), ("blocked", control)):
            program, binary = work / f"{name}.c", work / name
            program.write_text(prefix + text + suffix)
            subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                            str(program), "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True)
            assert result.returncode == (0 if name == "actual" else 71), name
        binary = work / "workload"
        subprocess.run([cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "sources/distro/distro/toolchain-smoke/cpuinfo.c"), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count(" pass\n") == 2 and result.stdout.count("::vm-test::pass") == 1
        print(f"{cc}: sparse online CPU formatter, blocked-IPI control and native busy-CPU read passed")
    musl = ROOT / "sources/musl"
    (work / "bits").mkdir()
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (work / "bits/alltypes.h").write_text(generated.stdout)
    cc = os.environ.get("WASM_CC", "clang")
    resource = subprocess.run([cc, "-print-resource-dir"], capture_output=True, text=True, check=True).stdout.strip()
    includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                "-I", str(musl / "include"), "-isystem", str(Path(resource) / "include")]
    for bits in (32, 64):
        flags = [cc, f"--target=wasm{bits}", "-nostdinc", "-matomics", "-mbulk-memory", *includes]
        workload = str(ROOT / "sources/distro/distro/toolchain-smoke/cpuinfo.c")
        subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", workload], check=True)
        subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", workload,
                        "-o", "/dev/null"], check=True)
        print(f"wasm{bits}: existing musl ABI frontend and static analysis passed")
