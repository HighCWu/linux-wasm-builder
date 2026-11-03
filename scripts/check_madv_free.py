#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute real admission/discard bodies with modeled mapping records and locks.

This checks Wasm32/64 artifacts, not a Linux boot or physical page reclaim.
"""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = Path(os.environ.get("WASM_MADVISE_KERNEL_SOURCE_ROOT", ROOT / "sources/linux"))
MUSL = ROOT / "sources/musl"


def function(source, start):
    body = source[source.index(start) :]
    return body[: body.index("\n}\n") + 3]


libc = function((MUSL / "src/mman/mmap.c").read_text(), "long __wasm_madvise(")
kernel = function(
    (LINUX / "arch/wasm/kernel/syscall.c").read_text(), "SYSCALL_DEFINE3(wasm_madvise,"
)
model = r"""
typedef unsigned long size_t;
typedef unsigned long uintptr_t;
#define UINTPTR_MAX (~0UL)
#define PAGESIZE 65536UL
#define PAGE_SIZE PAGESIZE
#define PAGE_MASK (~(PAGESIZE-1))
#define PAGE_ALIGNED(n) (!((n)&(PAGESIZE-1)))
#define TASK_SIZE (UINTPTR_MAX >> 1)
#define EINVAL 22
#define ENOMEM 12
#define EOPNOTSUPP 95
#define MADV_NORMAL 0
#define MADV_DONTNEED 4
#define MADV_FREE 8
#define check_add_overflow(a,b,to) __builtin_add_overflow(a,b,to)
#define SYSCALL_DEFINE3(name,t1,a1,t2,a2,t3,a3) long kernel_advice(t1 a1,t2 a2,t3 a3)
struct wasm_mapping {
 struct wasm_mapping *next;
 void *address;
 size_t length;
 int initialized;
};
static struct wasm_mapping *mappings;
static int mappings_lock;
static int pthread_mutex_lock(int *lock) {
 if(*lock) __builtin_trap(); *lock=1; return 0;
}
static int pthread_mutex_unlock(int *lock) {
 if(!*lock) __builtin_trap(); *lock=0; return 0;
}
void *memset(void *p,int value,size_t count) {
 unsigned char *bytes=p;
 for(size_t i=0;i<count;i++) bytes[i]=value;
 return p;
}
"""
checks = r"""
static unsigned char bytes[3*PAGESIZE] __attribute__((aligned(65536)));
static struct wasm_mapping records[3];
#define CHECK(test,code) do { if(!(test)) return code; } while(0)
static int all(unsigned char *p,size_t length,unsigned char value) {
 for(size_t i=0;i<length;i++) if(p[i]!=value) return 0;
 return 1;
}
__attribute__((export_name("check"))) int run(void) {
 uintptr_t base=(uintptr_t)bytes;
 mappings=records;
 for(int i=0;i<3;i++) {
  records[i].next=i==2?0:&records[i+1];
  records[i].address=bytes+i*PAGESIZE;
  records[i].length=PAGESIZE;
  records[i].initialized=0;
 }
 memset(bytes,0x57,sizeof bytes);
 CHECK(kernel_advice(base+PAGESIZE,1,MADV_FREE)==0,1);
 CHECK(all(bytes,PAGESIZE,0x57)&&all(bytes+PAGESIZE,PAGESIZE,0)&&
       all(bytes+2*PAGESIZE,PAGESIZE,0x57),2);
 /* A later hint must not erase writes made after FREE returned. */
 memset(bytes+PAGESIZE,0x6a,PAGESIZE);
 CHECK(kernel_advice(base,3*PAGESIZE,MADV_NORMAL)==0,3);
 CHECK(all(bytes+PAGESIZE,PAGESIZE,0x6a),4);
 CHECK(kernel_advice(base+1,0,MADV_FREE)==-EINVAL,5);
 CHECK(kernel_advice(0,0,MADV_FREE)==0,6);
 for(int advice=5;advice<8;advice++)
  CHECK(kernel_advice(base,PAGESIZE,advice)==-EINVAL,7);
 /* Validate the complete interval before modifying an earlier anonymous page. */
 memset(bytes,0x31,sizeof bytes);
 records[1].initialized=1;
 CHECK(kernel_advice(base,2*PAGESIZE,MADV_FREE)==-EINVAL,8);
 CHECK(all(bytes,sizeof bytes,0x31),9);
 CHECK(kernel_advice(base,2*PAGESIZE,MADV_DONTNEED)==-EOPNOTSUPP,10);
 CHECK(all(bytes,sizeof bytes,0x31),11);
 records[1].initialized=0;records[0].next=&records[2];
 CHECK(kernel_advice(base,3*PAGESIZE,MADV_FREE)==-ENOMEM,12);
 CHECK(all(bytes,sizeof bytes,0x31),13);
 records[0].next=&records[1];
 CHECK(kernel_advice(base,3*PAGESIZE,MADV_FREE)==0,14);
 CHECK(all(bytes,sizeof bytes,0),15);
 memset(bytes,0x3f,sizeof bytes);
 CHECK(all(bytes,sizeof bytes,0x3f)&&!mappings_lock,16);
 return 0;
}
"""
source = (
    model + libc + "\n#define wasm_user_v2_madvise __wasm_madvise\n" + kernel + checks
)
runner = """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[2]));
assert.equal(instance.exports.check(),0,'real kernel admission and allocator discard behavior');
"""
with tempfile.TemporaryDirectory(prefix="wasm-madv-free-") as tmp:
    path = Path(tmp)
    (path / "run.mjs").write_text(runner)
    for compiler in os.environ.get("WASM_MADVISE_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            for mode, body in (
                ("normal", source),
                (
                    "no-discard",
                    source.replace(
                        "memset((void *)begin, 0, rounded);", "(void)begin;"
                    ),
                ),
            ):
                (path / "check.c").write_text(body)
                binary = path / "check.wasm"
                subprocess.run(
                    [
                        compiler,
                        f"--target=wasm{bits}",
                        "-O2",
                        "-nostdlib",
                        "-ffreestanding",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-Wl,--no-entry",
                        str(path / "check.c"),
                        "-o",
                        str(binary),
                    ],
                    check=True,
                )
                if mode == "normal":
                    subprocess.run(
                        [
                            compiler,
                            f"--target=wasm{bits}",
                            "-ffreestanding",
                            "--analyze",
                            "-Xanalyzer",
                            "-analyzer-werror",
                            str(path / "check.c"),
                            "-o",
                            str(path / "analysis.plist"),
                        ],
                        check=True,
                    )
                run = subprocess.run(
                    ["node", str(path / "run.mjs"), str(binary)],
                    capture_output=True,
                    text=True,
                )
                if mode == "normal" and run.returncode:
                    raise RuntimeError(run.stderr)
                if mode == "no-discard" and not run.returncode:
                    raise RuntimeError(
                        "disabled discard incorrectly passed the actual-body check"
                    )
            print(
                f"{compiler} wasm{bits}: immediate FREE, later writes, adjacent records, holes and file rejection pass; disabled-discard control fails; not Linux boot acceptance"
            )
