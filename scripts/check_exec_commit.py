#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual Wasm loader/commit helper with mocked generic exec, not credential acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("WASM_EXEC_SOURCE", ROOT / "sources/linux/arch/wasm/kernel/binfmt_wasm.c"))
source = SOURCE.read_text()


def function(signature):
    start = source.index(signature + "\n{")
    return source[start:source.index("\n}\n", start) + 3]


loader = function("static int load_wasm_binary(struct linux_binprm *bprm)")
commit = function("static void commit_wasm_exec_args(struct linux_binprm *bprm)")
copy_args = function("static int copy_args(struct linux_binprm *bprm)")
assert "exec->secureexec = bprm->secureexec" not in copy_args
assert "exec->execfd = bprm->execfd" not in copy_args
prefix = r'''
typedef unsigned long size_t;
typedef long ssize_t;
typedef long long loff_t;
typedef unsigned char u8;
typedef unsigned int u32;
typedef _Bool bool;
#define true 1
#define false 0
#define NULL ((void *)0)
#define U32_MAX 0xffffffffU
#define ENOEXEC 8
#define EFBIG 27
#define ENOMEM 12
#define EAGAIN 11
#define EIO 5
#define GFP_KERNEL 0
#define WASM_EXEC_MAX_CHUNK_SIZE 262144
#define PER_LINUX 0
#define PER_LINUX_32BIT 8
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define WRITE_ONCE(x,v) ((x)=(v))
struct wasm_exec_args { int secureexec, have_execfd, execfd; };
struct mm_struct { struct { struct wasm_exec_args *exec_args; } context; };
struct linux_binprm { char buf[8]; void *file; struct mm_struct *mm; int secureexec, have_execfd, execfd; };
static struct wasm_exec_args original, prepared, observed;
static struct mm_struct oldmm, newmm;
static struct { struct mm_struct *mm; } task;
static struct { struct mm_struct *context_mm; } thread;
#define current (&task)
#define current_thread_info() (&thread)
static int mode, committed, aborts, copies, begins, instances;
static u8 storage[8];
static int wasm_format;
static int memcmp(const void *a,const void *b,size_t size) {
    const u8 *x=a,*y=b;
    for(size_t i=0;i<size;i++)if(x[i]!=y[i])return x[i]-y[i];
    return 0;
}
static int strncmp(const char *a,const char *b,size_t size) {
    for(size_t i=0;i<size;i++){if(a[i]!=b[i])return (u8)a[i]-(u8)b[i];if(!a[i])return 0;}
    return 0;
}
static int file_get_size(void *file,loff_t *size) { (void)file;*size=8;return 0; }
static void *kmalloc(size_t size,int flags) {
    (void)size;(void)flags;if(committed)__builtin_trap();return storage;
}
static void kfree(void *p) {(void)p;}
static int wasm_user_compile_begin(u32 length) {(void)length;return mode==4?-ENOMEM:0;}
static ssize_t kernel_read(void *file,void *buffer,u32 size,loff_t *position) {
    (void)file;(void)buffer;if(mode==5)return 0;*position+=size;return size;
}
static int wasm_user_compile_write(u8 *p,u32 offset,u32 size) {(void)p;(void)offset;(void)size;return 0;}
static u32 user_memory_limit_pages(void) {return 32;}
static int wasm_user_compile_end(u32 pages) {(void)pages;return mode==3?-ENOEXEC:0;}
static void wasm_user_compile_abort(void) {aborts++;}
static int copy_args(struct linux_binprm *bprm) {
    if(committed)__builtin_trap();copies++;
    if(mode==1)return -ENOMEM;
    bprm->mm->context.exec_args=&prepared;
    /* Conservative model of the old early snapshot: the commit helper must
     * overwrite these values before userspace first consumes the arguments. */
    prepared.secureexec=bprm->secureexec;
    prepared.have_execfd=bprm->have_execfd;
    prepared.execfd=bprm->execfd;
    return 0;
}
static int begin_new_exec(struct linux_binprm *bprm) {
    begins++;if(mode==2)return -EAGAIN;
    committed=1;bprm->secureexec=1;bprm->execfd=37;
    current->mm=bprm->mm;bprm->mm=NULL;return 0;
}
static void set_personality(int value) {(void)value;}
static void setup_new_exec(struct linux_binprm *bprm) {(void)bprm;}
static void set_binfmt(void *fmt) {(void)fmt;}
static void finalize_exec(struct linux_binprm *bprm) {(void)bprm;}
static void wasm_user_instantiate(bool exec) {
    if(!exec||!committed)__builtin_trap();instances++;
    observed=*current->mm->context.exec_args;
}
'''
driver = r'''
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
int run(int which) {
    mode=which;committed=aborts=copies=begins=instances=0;
    original=(struct wasm_exec_args){.secureexec=101,.have_execfd=102,.execfd=103};
    prepared=observed=(struct wasm_exec_args){0};
    oldmm.context.exec_args=&original;newmm.context.exec_args=NULL;
    current->mm=&oldmm;thread.context_mm=NULL;
    struct linux_binprm bprm={.buf={0,'a','s','m',1,0,0,0},.mm=&newmm,.have_execfd=1};
    if(mode==6)bprm.buf[1]='b';
    int ret=load_wasm_binary(&bprm);
    if(!mode) {
        CHECK(ret==0&&committed&&instances==1&&aborts==0&&copies==1&&begins==1);
        CHECK(observed.secureexec==1&&observed.have_execfd==1&&observed.execfd==37);
        CHECK(thread.context_mm==&newmm);
    } else {
        const int errors[]={0,-ENOMEM,-EAGAIN,-ENOEXEC,-ENOMEM,-EIO,-ENOEXEC};
        CHECK(ret==errors[mode]&&!committed&&!instances&&current->mm==&oldmm);
        CHECK(original.secureexec==101&&original.have_execfd==102&&original.execfd==103);
        CHECK(aborts==(mode==4||mode==6?0:1));
        if(mode==6)CHECK(!copies&&!begins);
    }
    return 0;
}
'''
controls = {
    "fixed": loader,
    "old-snapshot": loader.replace("\tcommit_wasm_exec_args(bprm);", ""),
    "early-commit": loader.replace("\tcommit_wasm_exec_args(bprm);", "").replace(
        "\tret = begin_new_exec(bprm);", "\tcommit_wasm_exec_args(bprm);\n\tret = begin_new_exec(bprm);"),
    "nul-header": loader.replace("memcmp(bprm->buf", "strncmp(bprm->buf"),
}
with tempfile.TemporaryDirectory(prefix="wasm-exec-commit-") as tmp:
    unit, module = Path(tmp) / "loader.c", Path(tmp) / "loader.wasm"
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            for kind, implementation in controls.items():
                assert kind == "fixed" or implementation != loader
                unit.write_text(prefix + commit + implementation + driver)
                flags = [cc, f"--target=wasm{bits}", "-ffreestanding"]
                subprocess.run([*flags, "-O2", "-nostdlib", "-Wl,--no-entry", "-Wl,--export=run",
                                str(unit), "-o", str(module)], check=True)
                if kind == "fixed":
                    subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror",
                                    "-o", "/dev/null", str(unit)], check=True)
                subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance:{exports:e}}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
const kind=process.argv[2];
if(kind==='fixed')for(let mode=0;mode<=6;mode++)assert.equal(e.run(mode),0,'mode '+mode);
else assert.notEqual(e.run(kind==='nul-header'?6:0),0,kind+' must expose the regression');
''', str(module), kind], check=True)
            print(f"{cc} wasm{bits}: actual loader commit, recoverable preparation and stale/early/NUL controls passed")
