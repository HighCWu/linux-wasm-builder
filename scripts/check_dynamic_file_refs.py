#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the pinned kernel file-reference functions with small ownership shims."""

from pathlib import Path
import os
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
arch = Path(os.environ.get("WASM_DYNAMIC_ARCH", root / "sources/linux/arch/wasm"))
source = (arch / "kernel/remote_vm.c").read_text()
section = source.split("/* WASM_DYNAMIC_FILE_REFS_BEGIN", 1)[1]
section = "/*" + section.split("*/", 1)[1]
section = section[2:].split("/* WASM_DYNAMIC_FILE_REFS_END */", 1)[0]
assert (
    "wasm_dynamic_file_refs_release(mm);"
    in source.split("/* WASM_DYNAMIC_FILE_REFS_BEGIN", 1)[0]
)
init = (arch / "mm/init.c").read_text()
assert "mm->context.dynamic_files = NULL;" in init
assert "mm->context.dynamic_file_count = 0;" in init
assert "mm->context.dynamic_file_next = 0;" in init
assert "result = wasm_dynamic_files_clone(old_mm, mm);" in init
evidence_dir = os.environ.get("WASM_DYNAMIC_EVIDENCE_DIR")
evidence = Path(evidence_dir).resolve() if evidence_dir else None
if evidence:
    evidence.mkdir(parents=True, exist_ok=True)

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
static int warn_on_count;
static int kmalloc_calls, kmalloc_fail_at;
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
static struct file *get_file(struct file *file) {
 assert(file && file->refs > 0); file->refs++; return file;
}
static void fput(struct file *file) { assert(file->refs > 0); file->refs--; }
#define file_inode(file) ((file)->inode)
#define huge_encode_dev(dev) (dev)
#define WARN_ON_ONCE(condition) ((condition) ? (++warn_on_count, 1) : 0)
static void *kmalloc(size_t size, int flags) {
 (void)flags; kmalloc_calls++;
 if (allocation_fail || (kmalloc_fail_at && kmalloc_calls == kmalloc_fail_at)) return 0;
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
 wasm_dynamic_file_refs_release(&mm);
 assert(second.refs == 0 && allocated == 0 && !mm.context.dynamic_files);
 assert(!mm.context.dynamic_file_count);
 wasm_dynamic_file_refs_release(&mm);
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

 struct mm_struct copy_parent = { .context.remote.accepting = true };
 struct mm_struct copy_child = { .context.remote.accepting = true };
 struct mm_struct copy_child_second = { .context.remote.accepting = true };
 struct mm_struct rejected_child = { .context.remote.accepting = true };
 struct mm_struct empty_parent = { .context.remote.accepting = true };
 struct mm_struct empty_child = { .context.remote.accepting = true };
 struct inode c = { S_IFREG | 0600, 333, &sb, 13 }, d = { S_IFREG | 0600, 444, &sb, 14 };
 struct file third = { FMODE_READ, 1, &c, { &c } }, fourth = { FMODE_READ, 1, &d, { &d } };
 fds[1] = &third; fds[2] = &fourth;
 task.mm = &copy_parent; ti.context_mm = &copy_parent;
 int copy_id_a = wasm_dynamic_file_pin_v1(1, 7, 13);
 int copy_id_b = wasm_dynamic_file_pin_v1(2, 7, 14);
 assert(copy_id_a == 1 && copy_id_b == 2);
 assert(copy_parent.context.dynamic_file_count == 2 && copy_parent.context.dynamic_file_next == 2);
 assert(wasm_dynamic_file_copy_abi_v1() == 1);

 /* Fail the second allocation: the first copied file reference must roll back. */
 kmalloc_calls = 0; kmalloc_fail_at = 2;
 assert(wasm_dynamic_files_clone(&copy_parent, &copy_child) == -ENOMEM);
 kmalloc_fail_at = 0;
 assert(!copy_child.context.dynamic_files && !copy_child.context.dynamic_file_count);
 assert(copy_child.context.dynamic_file_next == 0);
 assert(third.refs == 2 && fourth.refs == 2 && allocated == 2);

 /* A closed source mm cannot be cloned even when a destination is available. */
 copy_parent.context.remote.accepting = false;
 assert(wasm_dynamic_files_clone(&copy_parent, &rejected_child) == -ESRCH);
 assert(!rejected_child.context.dynamic_files && !rejected_child.context.dynamic_file_count);
 assert(third.refs == 2 && fourth.refs == 2 && allocated == 2);
 copy_parent.context.remote.accepting = true;

 kmalloc_calls = 0;
 assert(!wasm_dynamic_files_clone(&copy_parent, &copy_child));
 assert(copy_child.context.dynamic_file_count == 2 && copy_child.context.dynamic_file_next == 2);
 assert(copy_child.context.dynamic_files && copy_parent.context.dynamic_files);
 assert(copy_child.context.dynamic_files != copy_parent.context.dynamic_files);
 assert(copy_child.context.dynamic_files->id == copy_parent.context.dynamic_files->id);
 assert(copy_child.context.dynamic_files->next != copy_parent.context.dynamic_files->next);
 assert(copy_child.context.dynamic_files->next->id == copy_parent.context.dynamic_files->next->id);
 assert(third.refs == 3 && fourth.refs == 3 && allocated == 4);

 kmalloc_calls = 0;
 assert(!wasm_dynamic_files_clone(&copy_parent, &copy_child_second));
 assert(copy_child_second.context.dynamic_file_count == 2);
 assert(copy_child_second.context.dynamic_file_next == 2);
 assert(copy_child_second.context.dynamic_files != copy_child.context.dynamic_files);
 assert(copy_child_second.context.dynamic_files->id == copy_child.context.dynamic_files->id);
 assert(third.refs == 4 && fourth.refs == 4 && allocated == 6);

 /* Releasing one child does not detach or unpin the parent or another child. */
 wasm_dynamic_file_refs_release(&copy_child);
 assert(!copy_child.context.dynamic_files && !copy_child.context.dynamic_file_count);
 assert(copy_parent.context.dynamic_file_count == 2);
 assert(copy_child_second.context.dynamic_file_count == 2);
 assert(third.refs == 3 && fourth.refs == 3 && allocated == 4);

 /* Releasing the parent leaves the remaining child's equal IDs intact. */
 wasm_dynamic_file_refs_release(&copy_parent);
 assert(!copy_parent.context.dynamic_files && !copy_parent.context.dynamic_file_count);
 assert(copy_child_second.context.dynamic_file_count == 2 && copy_child_second.context.dynamic_file_next == 2);
 assert(third.refs == 2 && fourth.refs == 2 && allocated == 2);
 task.mm = &copy_child_second; ti.context_mm = &copy_child_second;
 assert(!wasm_dynamic_file_unpin_v1(copy_id_a));
 assert(copy_child_second.context.dynamic_file_count == 1 && third.refs == 1);
 assert(!copy_parent.context.dynamic_files && copy_child_second.context.dynamic_files);
 wasm_dynamic_file_refs_release(&copy_child_second);
 assert(!copy_child_second.context.dynamic_files && !copy_child_second.context.dynamic_file_count);
 assert(fourth.refs == 1 && allocated == 0);
 fput(fds[1]); fds[1] = 0;
 fput(fds[2]); fds[2] = 0;

 /* The high-water ID is copied even when the source list is empty. */
 empty_parent.context.dynamic_file_next = 37;
 assert(!empty_parent.context.dynamic_files && !empty_parent.context.dynamic_file_count);
 assert(!wasm_dynamic_files_clone(&empty_parent, &empty_child));
 assert(!empty_child.context.dynamic_files && !empty_child.context.dynamic_file_count);
 assert(empty_child.context.dynamic_file_next == 37);
 third.refs = 1; fds[1] = &third;
 task.mm = &empty_child; ti.context_mm = &empty_child;
 assert(wasm_dynamic_file_pin_v1(1, 7, 13) == 38);
 assert(!wasm_dynamic_file_unpin_v1(38) && third.refs == 1 && !allocated);
 fput(fds[1]); fds[1] = 0;
 assert(!warn_on_count);
 return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="wasm-dynamic-file-") as directory:
    path = Path(directory)
    test_source = path / "test.c"
    test_source.write_text(SHIM + section + TEST)
    if evidence:
        (evidence / "test.c").write_bytes(test_source.read_bytes())
    commands = []
    for compiler in os.environ.get("WASM_DYNAMIC_COMPILERS", "gcc clang").split():
        compile_command = [
            compiler,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(test_source),
            "-o",
            str(path / "check"),
        ]
        commands.append(shlex.join(compile_command))
        subprocess.run(compile_command, check=True, timeout=30)
        run_command = [str(path / "check")]
        commands.append(shlex.join(run_command))
        subprocess.run(run_command, check=True, timeout=10)
        print(f"{compiler}: actual kernel file-ref ownership and teardown model pass")
    if evidence:
        (evidence / "commands.txt").write_text("\n".join(commands) + "\n")
