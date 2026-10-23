#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual anonymous mmap admission plus native Linux reference; no large mappings."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("WASM_SYSCALL_SOURCE", ROOT / "sources/linux/arch/wasm/kernel/syscall.c")).read_text()
start = source.index("SYSCALL_DEFINE6(wasm_mmap,")
body = source[start:source.index("\n}\n", start) + 3]
old = body.replace("if (!len || (flags & MAP_TYPE)", "if (!len || pgoff || (flags & MAP_TYPE)")
assert old != body
compilers = os.environ.get("WASM_OFFSET_COMPILERS", "clang").split()
assert compilers, "at least one Wasm compiler must execute anonymous admission"
prefix = r'''
typedef __SIZE_TYPE__ size_t;
#define SYSCALL_DEFINE6(n,t0,a0,t1,a1,t2,a2,t3,a3,t4,a4,t5,a5) long n(t0 a0,t1 a1,t2 a2,t3 a3,t4 a4,t5 a5)
#define PAGE_SIZE 65536UL
#define PAGE_ALIGNED(a) (!((a)&(PAGE_SIZE-1)))
#define ALIGN(a,n) (((a)+(n)-1)&-(__typeof__(a))(n))
#define ULONG_MAX (~0UL)
#ifdef CONFIG_64BIT
#define TASK_SIZE (1UL<<34)
#else
#define TASK_SIZE 0xffffffffUL
#endif
#define MAP_PRIVATE 2
#define MAP_TYPE 15
#define MAP_FIXED 16
#define MAP_ANONYMOUS 32
#define MAP_DENYWRITE 0x800
#define MAP_EXECUTABLE 0x1000
#define MAP_NORESERVE 0x4000
#define MAP_POPULATE 0x8000
#define MAP_NONBLOCK 0x10000
#define MAP_STACK 0x20000
#define MAP_FIXED_NOREPLACE 0x100000
#define PROT_READ 1
#define PROT_WRITE 2
#define EINVAL 22
#define ENOMEM 12
static unsigned normal_count,fixed_count,file_count;
static unsigned long saved_offset,saved_flags;
static long saved_fd;
static long wasm_user_v2_mmap(unsigned long a,unsigned long n,unsigned int p,unsigned int f,int fd,unsigned long off) {
    (void)a;(void)n;(void)p;normal_count++;saved_offset=off;saved_flags=f;saved_fd=fd;return 0x40000;
}
static long wasm_user_v2_mmap_fixed(unsigned long a,unsigned long n) {(void)n;fixed_count++;return a;}
static long wasm_mmap_file(unsigned long a,unsigned long n,unsigned long p,unsigned long f,long fd,unsigned long off) {
    (void)a;(void)n;(void)p;(void)f;file_count++;saved_offset=off;saved_fd=fd;return -95;
}
void reset(void) { normal_count=fixed_count=file_count=0;saved_offset=saved_flags=0;saved_fd=0; }
unsigned normal(void) {return normal_count;}
unsigned fixed(void) {return fixed_count;}
unsigned files(void) {return file_count;}
unsigned long offset(void) {return saved_offset;}
unsigned long flags(void) {return saved_flags;}
long fd(void) {return saved_fd;}
'''
native = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>
int main(void) {
    long page=sysconf(_SC_PAGESIZE);
    FILE *file=tmpfile(); assert(file && lseek(fileno(file),7,SEEK_SET)==7);
    uintptr_t offsets[]={0,(uintptr_t)page,1ULL<<32,UINTPTR_MAX&-(uintptr_t)page};
    for (unsigned i=0;i<sizeof offsets/sizeof offsets[0];i++) {
        unsigned char *p=(void *)syscall(SYS_mmap,0L,page,(long)(PROT_READ|PROT_WRITE),
            (long)(MAP_PRIVATE|MAP_ANONYMOUS),(long)fileno(file),(long)offsets[i]);
        assert(p!=MAP_FAILED);
        for (long j=0;j<page;j++) assert(!p[j]);
        p[0]=0x5a;assert(!munmap(p,page));
    }
    errno=0;
    assert(syscall(SYS_mmap,0L,page,(long)(PROT_READ|PROT_WRITE),
        (long)(MAP_PRIVATE|MAP_ANONYMOUS),12345L,1L)==-1 && errno==EINVAL);
    assert(lseek(fileno(file),0,SEEK_CUR)==7 && !fclose(file));
}
'''
with tempfile.TemporaryDirectory(prefix="wasm-anon-offset-") as tmp:
    work=Path(tmp)
    musl=ROOT/"sources/musl"
    (work/"bits").mkdir()
    templates=(musl/"arch/wasm32/bits/alltypes.h.in").read_text()+(musl/"include/alltypes.h.in").read_text()
    generated=subprocess.run(["sed","-f",str(musl/"tools/mkalltypes.sed")],input=templates,capture_output=True,text=True,check=True)
    (work/"bits/alltypes.h").write_text(generated.stdout)
    numbers=(musl/"arch/wasm32/bits/syscall.h.in").read_text()
    (work/"bits/syscall.h").write_text(numbers+numbers.replace("__NR_","SYS_"))
    for cc in ("gcc","clang"):
        unit,binary=work/"native.c",work/"native"
        unit.write_text(native)
        subprocess.run([cc,"-O2","-Wall","-Wextra","-Werror",str(unit),"-o",str(binary)],check=True)
        subprocess.run([str(binary)],check=True,timeout=10)
    for cc in compilers:
        for bits in (32,64):
            workload=str(ROOT/"sources/distro/distro/basic-init/tests/mmap-offsets.c")
            includes=["-I",tmp,"-I",str(musl/"arch/wasm32"),"-I",str(musl/"arch/generic"),"-I",str(musl/"include")]
            frontend=[cc,f"--target=wasm{bits}","-nostdinc",*includes]
            subprocess.run([*frontend,"-fsyntax-only","-Wall","-Wextra","-Werror",workload],check=True)
            subprocess.run([*frontend,"--analyze","-Xanalyzer","-analyzer-werror",workload,"-o","/dev/null"],check=True)
            for file_mode in (False,True):
                for actual,fixed in ((body,True),(old,False)):
                    unit,binary=work/"map.c",work/"map.wasm"
                    config=("#define CONFIG_64BIT 1\n" if bits==64 else "")
                    config+=("#define CONFIG_WASM_FILE_MMAP 1\n" if file_mode else "")
                    unit.write_text(config+prefix+actual)
                    flags=[cc,f"--target=wasm{bits}","-ffreestanding"]
                    subprocess.run([*flags,"--analyze","-Xanalyzer","-analyzer-werror",str(unit),"-o","/dev/null"],check=True)
                    exports=["wasm_mmap","reset","normal","fixed","files","offset","flags","fd"]
                    subprocess.run([*flags,"-O2","-nostdlib","-Wl,--no-entry",*["-Wl,--export="+x for x in exports],
                                    str(unit),"-o",str(binary)],check=True)
                    subprocess.run(["node","--input-type=module","-e",r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance:{exports:a}}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
const wide=process.argv[2]==='64', good=process.argv[3]==='True', file=process.argv[4]==='True';
const p=n=>wide ? BigInt(n) : Number(n)|0, unit=wide ? 65536n : 16n;
const max=(1n<<(wide?64n:32n))-1n;
const call=(off,fl=0x22,addr=0,len=65536,prot=3)=>a.wasm_mmap(p(addr),p(len),p(prot),p(fl),p(12345),p(off));
for (const off of [0n,unit,unit*65536n,max&-unit]) {
  a.reset();
  assert.equal(call(off),p(good||off===0n ? 0x40000 : -22));
  assert.equal(a.normal(),good||off===0n ? 1 : 0);
  if (good||off===0n) { assert.equal(a.offset(),p(0));assert.equal(a.fd(),p(-1));assert.equal(a.flags(),p(0x22)); }
}
for (const off of [1n,unit-1n,max]) {
  a.reset();assert.equal(call(off),p(-22));
  assert.equal(a.normal()+a.fixed()+a.files(),0,'alignment failure must not call any allocator');
}
a.reset();assert.equal(call(unit,0x32,8*65536),p(good?8*65536:-22));assert.equal(a.fixed(),good?1:0);
a.reset();assert.equal(call(unit,0x100032,8*65536),p(good?0x40000:-22));
if (good) {assert.equal(a.flags(),p(0x100022));assert.equal(a.offset(),p(0));}
a.reset();assert.equal(call(1n,2),p(file?-95:-22));assert.equal(a.files(),file?1:0);
if (file) {assert.equal(a.offset(),p(1));assert.equal(a.fd(),p(12345));}
for (const [len,prot] of [[0,3],[65536,0]]) {
  a.reset();assert.equal(call(0n,0x22,0,len,prot),p(-22));assert.equal(a.normal(),0);
}
''',str(binary),str(bits),str(fixed),str(file_mode)],check=True)
            print(f"{cc} wasm{bits}: actual anonymous admission, raw units, unchanged file delegation and old rejection control passed")
