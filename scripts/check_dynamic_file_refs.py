#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the pinned kernel file-reference functions with small ownership shims."""

from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
arch = Path(os.environ.get("WASM_DYNAMIC_ARCH", root / "sources/linux/arch/wasm"))
source = (arch / "kernel/remote_vm.c").read_text()
section = source.split("/* WASM_DYNAMIC_FILE_REFS_BEGIN", 1)[1]
section = "/*" + section.split("*/", 1)[1]
section = section[2:].split("/* WASM_DYNAMIC_FILE_REFS_END */", 1)[0]
assert (
    "release_dynamic_files(mm);"
    in source.split("/* WASM_DYNAMIC_FILE_REFS_BEGIN", 1)[0]
)
init = (arch / "mm/init.c").read_text()
assert "mm->context.dynamic_files = NULL;" in init
assert "mm->context.dynamic_file_next = 0;" in init

SHIM = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/stat.h>
typedef uint64_t u64;
#define READ_ONCE(x) (x)
#define GFP_KERNEL 0
#define FMODE_READ 1
struct mutex { int held; };
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held = 1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held = 0; }
struct super_block { u64 s_dev; };
struct inode { unsigned i_mode; u64 i_ino; struct super_block *i_sb; u64 reported; };
struct path { struct inode *inode; };
struct kstat { u64 dev, ino; };
struct file { int f_mode, refs; struct inode *inode; struct path f_path; };
#ifndef STATX_INO
#define STATX_INO 0x100
#endif
#define AT_STATX_SYNC_AS_STAT 0
static int getattr_failure;
static int vfs_getattr(const struct path *path, struct kstat *out, unsigned mask, unsigned flags) {
 assert(mask == STATX_INO && flags == AT_STATX_SYNC_AS_STAT);
 if (getattr_failure) return -EACCES;
 out->dev = path->inode->i_sb->s_dev;
 out->ino = path->inode->reported; return 0;
}
struct wasm_dynamic_file;
struct mm_struct { struct {
 struct { struct mutex mutex; bool accepting; } remote;
 struct wasm_dynamic_file *dynamic_files;
 unsigned dynamic_file_count; int dynamic_file_next;
} context; };
static struct { struct mm_struct *mm; } task;
#define current (&task)
static struct { struct mm_struct *context_mm; } ti;
#define current_thread_info() (&ti)
static struct file *fds[4];
static int allocated, allocation_fail;
static struct file *fget(int fd) {
 if (fd < 0 || fd >= 4 || !fds[fd]) return 0;
 fds[fd]->refs++; return fds[fd];
}
static void fput(struct file *file) { assert(file->refs > 0); file->refs--; }
#define file_inode(file) ((file)->inode)
#define huge_encode_dev(dev) (dev)
static void *kmalloc(size_t size, int flags) {
 (void)flags; if (allocation_fail) return 0;
 void *p = malloc(size); assert(p); allocated++; return p;
}
static void kfree(void *p) { assert(p && allocated > 0); allocated--; free(p); }
"""
TEST = r"""
int main(void) {
 struct mm_struct mm = { .context.remote.accepting = true }, other = {0};
 struct super_block sb = { 7 };
 struct inode a = { S_IFREG | 0600, 111, &sb, 11 }, b = { S_IFREG | 0600, 222, &sb, 12 };
 struct file first = { FMODE_READ, 1, &a, { &a } }, second = { FMODE_READ, 1, &b, { &b } };
 assert(wasm_dynamic_file_pin_abi_v1() == 1);
 task.mm = &mm; ti.context_mm = &other;
 assert(wasm_dynamic_file_pin_v1(0, 7, 11) == -EAGAIN);
 ti.context_mm = &mm;
 assert(wasm_dynamic_file_pin_v1(0, 7, 11) == -EBADF);
 fds[0] = &first;
 getattr_failure = 1;
 assert(wasm_dynamic_file_pin_v1(0, 7, 11) == -EACCES && first.refs == 1);
 getattr_failure = 0;
 assert(wasm_dynamic_file_pin_v1(0, 7, 12) == -ESTALE && first.refs == 1);
 allocation_fail = 1;
 assert(wasm_dynamic_file_pin_v1(0, 7, 11) == -ENOMEM && first.refs == 1);
 allocation_fail = 0;
 int id = wasm_dynamic_file_pin_v1(0, 7, 11);
 assert(id == 1 && first.refs == 2 && allocated == 1);
 fput(fds[0]); fds[0] = &second; /* Close and reuse fd 0. */
 assert(first.refs == 1);
 assert(wasm_dynamic_file_pin_v1(0, 7, 11) == -ESTALE && second.refs == 1);
 int next = wasm_dynamic_file_pin_v1(0, 7, 12);
 assert(next == 2 && second.refs == 2);
 assert(!wasm_dynamic_file_unpin_v1(id) && first.refs == 0);
 assert(wasm_dynamic_file_unpin_v1(id) == -ENOENT && mm.context.dynamic_file_count == 1);
 ti.context_mm = &other;
 assert(wasm_dynamic_file_unpin_v1(next) == -EAGAIN && second.refs == 2);
 ti.context_mm = &mm;
 fput(fds[0]); fds[0] = 0;
 mm.context.remote.accepting = false;
 release_dynamic_files(&mm);
 assert(second.refs == 0 && allocated == 0 && !mm.context.dynamic_files);
 assert(!mm.context.dynamic_file_count);
 release_dynamic_files(&mm);
 second.refs = 1; fds[0] = &second;
 assert(wasm_dynamic_file_pin_v1(0, 7, 12) == -ESRCH && second.refs == 1);
 mm.context.remote.accepting = true;
 mm.context.dynamic_file_count = 1024;
 int large_count_id = wasm_dynamic_file_pin_v1(0, 7, 12);
 assert(large_count_id == 3 && second.refs == 2 && allocated == 1);
 assert(mm.context.dynamic_file_count == 1025);
 assert(!wasm_dynamic_file_unpin_v1(large_count_id));
 assert(second.refs == 1 && allocated == 0 && mm.context.dynamic_file_count == 1024);
 assert(!mm.context.dynamic_files);
 mm.context.dynamic_file_next = INT_MAX;
 assert(wasm_dynamic_file_pin_v1(0, 7, 12) == -ENOSPC && second.refs == 1);
 assert(!allocated && !mm.context.remote.mutex.held && mm.context.dynamic_file_count == 1024);
 return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="wasm-dynamic-file-") as directory:
    path = Path(directory)
    (path / "test.c").write_text(SHIM + section + TEST)
    for compiler in os.environ.get("WASM_DYNAMIC_COMPILERS", "gcc clang").split():
        subprocess.run(
            [
                compiler,
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(path / "test.c"),
                "-o",
                str(path / "check"),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(path / "check")], check=True, timeout=10)
        print(f"{compiler}: actual kernel file-ref ownership and teardown model pass")
