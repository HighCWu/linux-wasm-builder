// SPDX-License-Identifier: MIT
// Compile the exact architecture wrapper with lightweight host definitions.
// This validates admission/forwarding, not Linux/Wasm execution or libc linkage.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

for (const cc of ["gcc", "clang"])
  test(`${cc}: exact mmap routes FIXED separately and gives NOREPLACE priority`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), "wasm-fixed-mmap-syscall-"));
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    const source = readFileSync(
      process.env.WASM_MREMAP_SYSCALL_SOURCE ??
        new URL("../sources/linux/arch/wasm/kernel/syscall.c", import.meta.url),
      "utf8",
    );
    const start = source.indexOf("SYSCALL_DEFINE6(wasm_mmap,");
    const end = source.indexOf("\n}\n", start);
    assert.ok(start >= 0 && end > start);
    const prefix = `
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <sys/mman.h>
#define PAGE_SIZE 65536UL
#define PAGE_ALIGNED(x) (!((x) & (PAGE_SIZE - 1)))
#define ALIGN(x,n) (((x)+(n)-1)&~((n)-1))
#define TASK_SIZE 0x400000000UL
#define SYSCALL_DEFINE6(n,t0,a0,t1,a1,t2,a2,t3,a3,t4,a4,t5,a5) long n(t0 a0,t1 a1,t2 a2,t3 a3,t4 a4,t5 a5)
static int fixed_calls, legacy_calls;
static long wasm_user_v2_mmap_fixed(unsigned long a, unsigned long n) {
  assert(a == 65536 && n == 65536); fixed_calls++; return a;
}
static long wasm_user_v2_mmap(unsigned long a, unsigned long n, unsigned long p,
  unsigned long f, long fd, unsigned long o) {
  assert(a == 65536 && n == 65536 && p == 3 && f == (MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE));
  assert(fd == -1 && o == 0); legacy_calls++; return -EEXIST;
}
`;
    const fixture = `
int main(void) {
  int f = MAP_PRIVATE | MAP_ANONYMOUS;
  assert(wasm_mmap(65536, 1, 3, f | MAP_FIXED, -1, 0) == 65536 && fixed_calls == 1);
  assert(wasm_mmap(65536, 1, 3, f | MAP_FIXED | MAP_FIXED_NOREPLACE, -1, 0) == -EEXIST);
  assert(wasm_mmap(65536, 1, 3, f | MAP_FIXED_NOREPLACE, -1, 0) == -EEXIST && legacy_calls == 2);
  assert(wasm_mmap(65537, 1, 3, f | MAP_FIXED, -1, 0) == -EINVAL);
  assert(wasm_mmap(0, 1, 3, f | MAP_FIXED, -1, 0) == -ENOMEM);
  assert(wasm_mmap(TASK_SIZE, 1, 3, f | MAP_FIXED, -1, 0) == -ENOMEM);
  assert(wasm_mmap(65536, ULONG_MAX, 3, f | MAP_FIXED, -1, 0) == -ENOMEM);
  assert(wasm_mmap(65536, 1, 1, f | MAP_FIXED, -1, 0) == -EINVAL);
  assert(wasm_mmap(65536, 1, 3, f | MAP_FIXED | 0x80000000UL, -1, 0) == -EINVAL);
  assert(fixed_calls == 1 && legacy_calls == 2);
}
`;
    const input = join(dir, "test.c"),
      binary = join(dir, "test");
    writeFileSync(input, prefix + source.slice(start, end + 3) + fixture);
    const build = spawnSync(
      cc,
      ["-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", input, "-o", binary],
      { encoding: "utf8" },
    );
    assert.equal(build.status, 0, build.stderr);
    const run = spawnSync(binary, [], { encoding: "utf8", timeout: 10000 });
    assert.equal(run.status, 0, run.stdout + run.stderr);
  });

for (const cc of ["gcc", "clang"])
  test(`${cc}: exact madvise validates geometry and preserves typed advice`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), "wasm-madvise-syscall-"));
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    const source = readFileSync(
      process.env.WASM_MREMAP_SYSCALL_SOURCE ??
        new URL("../sources/linux/arch/wasm/kernel/syscall.c", import.meta.url),
      "utf8",
    );
    const start = source.indexOf("SYSCALL_DEFINE3(wasm_madvise,");
    const end = source.indexOf("\n}\n", start);
    assert.ok(start >= 0 && end > start);
    const prefix = `
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <limits.h>
#include <sys/mman.h>
#define PAGE_SIZE 65536UL
#define PAGE_MASK (~(PAGE_SIZE - 1))
#define PAGE_ALIGNED(x) (!((x) & (PAGE_SIZE - 1)))
#define TASK_SIZE 0x400000000UL
#define check_add_overflow(a,b,c) __builtin_add_overflow(a,b,c)
#define SYSCALL_DEFINE3(n,t0,a0,t1,a1,t2,a2) long n(t0 a0,t1 a1,t2 a2)
static unsigned calls;
static long response;
static long wasm_user_v2_madvise(unsigned long a, unsigned long b, int c) {
  calls++; assert(a == 0x100010000UL && b == 2 * PAGE_SIZE && c == MADV_DONTNEED);
  return response;
}
`;
    const fixture = `
int main(void) {
  assert(wasm_madvise(0, 0, MADV_DONTNEED) == 0);
  assert(wasm_madvise(TASK_SIZE * 2, 0, MADV_NORMAL) == 0);
  assert(wasm_madvise(1, 0, MADV_NORMAL) == -EINVAL);
  assert(wasm_madvise(65536, 1, -1) == -EINVAL);
  assert(wasm_madvise(65536, 1, MADV_FREE) == -EINVAL);
  assert(wasm_madvise(65536, ULONG_MAX, MADV_DONTNEED) == -EINVAL);
  assert(wasm_madvise(ULONG_MAX & PAGE_MASK, PAGE_SIZE * 2, 0) == -EINVAL);
  assert(wasm_madvise(TASK_SIZE, 1, MADV_DONTNEED) == -ENOMEM);
  assert(calls == 0);
  assert(wasm_madvise(0x100010000UL, PAGE_SIZE + 1, MADV_DONTNEED) == 0 && calls == 1);
  response = -ENOSYS;
  assert(wasm_madvise(0x100010000UL, PAGE_SIZE + 1, MADV_DONTNEED) == -ENOSYS && calls == 2);
}
`;
    const input = join(dir, "test.c"),
      binary = join(dir, "test");
    writeFileSync(input, prefix + source.slice(start, end + 3) + fixture);
    const build = spawnSync(
      cc,
      ["-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", input, "-o", binary],
      { encoding: "utf8" },
    );
    assert.equal(build.status, 0, build.stderr);
    const run = spawnSync(binary, [], { encoding: "utf8", timeout: 10000 });
    assert.equal(run.status, 0, run.stdout + run.stderr);
  });

for (const cc of ["gcc", "clang"])
  test(`${cc}: exact private msync validates geometry and flags before forwarding`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), "wasm-msync-syscall-"));
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    const source = readFileSync(
      process.env.WASM_MREMAP_SYSCALL_SOURCE ??
        new URL("../sources/linux/arch/wasm/kernel/syscall.c", import.meta.url),
      "utf8",
    );
    const start = source.indexOf("SYSCALL_DEFINE3(wasm_msync,");
    const end = source.indexOf("\n}\n", start);
    assert.ok(start >= 0 && end > start);
    const prefix = `
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <limits.h>
#include <sys/mman.h>
#define PAGE_SIZE 65536UL
#define PAGE_MASK (~(PAGE_SIZE - 1))
#define PAGE_ALIGNED(x) (!((x) & (PAGE_SIZE - 1)))
#define TASK_SIZE 0x400000000UL
#define check_add_overflow(a,b,c) __builtin_add_overflow(a,b,c)
#define SYSCALL_DEFINE3(n,t0,a0,t1,a1,t2,a2) long n(t0 a0,t1 a1,t2 a2)
static unsigned calls;
static unsigned long captured[2];
static int captured_flags;
static long response;
static long wasm_user_v2_msync(unsigned long a, unsigned long b, int f) {
  calls++; captured[0]=a; captured[1]=b; captured_flags=f; return response;
}
`;
    const fixture = `
int main(void) {
  assert(wasm_msync(0, 0, MS_SYNC) == 0);
  assert(wasm_msync(TASK_SIZE * 2, 0, 0) == 0);
  assert(wasm_msync(1, 0, MS_SYNC) == -EINVAL);
  assert(wasm_msync(65536, 0, MS_SYNC | MS_ASYNC) == -EINVAL);
  assert(wasm_msync(65536, 1, 8) == -EINVAL);
  assert(wasm_msync(65536, ULONG_MAX, MS_SYNC) == -ENOMEM);
  assert(wasm_msync(TASK_SIZE, 1, MS_SYNC) == -ENOMEM);
  assert(wasm_msync(ULONG_MAX & PAGE_MASK, PAGE_SIZE * 2, 0) == -ENOMEM);
  assert(calls == 0);
  assert(wasm_msync(0x100010000UL, PAGE_SIZE + 1, MS_SYNC | MS_INVALIDATE) == 0);
  assert(calls == 1 && captured[0] == 0x100010000UL && captured[1] == 2 * PAGE_SIZE && captured_flags == 6);
  response = -ENOSYS;
  assert(wasm_msync(65536, 1, MS_SYNC) == -ENOSYS && calls == 2);
}
`;
    const input = join(dir, "test.c"),
      binary = join(dir, "test");
    writeFileSync(input, prefix + source.slice(start, end + 3) + fixture);
    const build = spawnSync(
      cc,
      ["-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", input, "-o", binary],
      { encoding: "utf8" },
    );
    assert.equal(build.status, 0, build.stderr);
    const run = spawnSync(binary, [], { encoding: "utf8", timeout: 10000 });
    assert.equal(run.status, 0, run.stdout + run.stderr);
  });

for (const cc of ["gcc", "clang"])
  test(`${cc}: exact mremap wrapper rejects before forwarding and rounds at 64 KiB`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), "wasm-mremap-syscall-"));
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    const source = readFileSync(
      process.env.WASM_MREMAP_SYSCALL_SOURCE ??
        new URL("../sources/linux/arch/wasm/kernel/syscall.c", import.meta.url),
      "utf8",
    );
    const start = source.indexOf("SYSCALL_DEFINE5(wasm_mremap,");
    const end = source.indexOf("\n}\n", start);
    assert.ok(start >= 0 && end > start);
    const wrapper = source.slice(start, end + 3);
    const prefix = `
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#define PAGE_SIZE 65536UL
#define PAGE_MASK (~(PAGE_SIZE - 1))
#define PAGE_ALIGNED(x) (!((x) & (PAGE_SIZE - 1)))
#define TASK_SIZE 0x400000000UL
#define check_add_overflow(a,b,c) __builtin_add_overflow(a,b,c)
#define SYSCALL_DEFINE5(n,t0,a0,t1,a1,t2,a2,t3,a3,t4,a4) long n(t0 a0,t1 a1,t2 a2,t3 a3,t4 a4)
static unsigned calls;
static unsigned long captured[4];
static long response = 0x12340000;
static long wasm_user_v2_mremap(unsigned long a, unsigned long b, unsigned long c, unsigned long d) {
  calls++; captured[0]=a; captured[1]=b; captured[2]=c; captured[3]=d; return response;
}
`;
    const fixture = `
int main(void) {
  assert(wasm_mremap(65537, 1, 1, 0, 0) == -EINVAL);
  assert(wasm_mremap(65536, 1, 0, 0, 0) == -EINVAL);
  assert(wasm_mremap(65536, 1, 1, 8, 0) == -EINVAL);
  assert(wasm_mremap(65536, 1, 1, 2, 0) == -EINVAL);
  assert(wasm_mremap(65536, 1, 1, 3, 1) == -EINVAL);
  assert(wasm_mremap(65536, 1, 1, 3, 131072) == -EOPNOTSUPP);
  assert(wasm_mremap(65536, 0, 1, 0, 0) == -EOPNOTSUPP);
  assert(wasm_mremap(65536, ULONG_MAX, 1, 0, 0) == -EINVAL);
  assert(wasm_mremap(65536, 1, ULONG_MAX, 0, 0) == -ENOMEM);
  assert(wasm_mremap(TASK_SIZE, 1, 1, 0, 0) == -EFAULT);
  assert(wasm_mremap(65536, 1, TASK_SIZE + PAGE_SIZE, 0, 0) == -ENOMEM);
  assert(wasm_mremap(65536, 1, 2, 5, 0) == -EOPNOTSUPP);
  assert(wasm_mremap(65536, 1, PAGE_SIZE + 1, 5, 0) == -EINVAL);
  assert(calls == 0);
  assert(wasm_mremap(0x100010000UL, PAGE_SIZE + 1, 2 * PAGE_SIZE + 1, 1, 77) == response);
  assert(calls == 1 && captured[0] == 0x100010000UL && captured[1] == 2 * PAGE_SIZE &&
    captured[2] == 3 * PAGE_SIZE && captured[3] == 1);
  response = -ENOMEM;
  assert(wasm_mremap(65536, 1, 1, 0, 0) == -ENOMEM && calls == 2);
  puts("mremap admission: flags, overflow, address extent, rounding and callback result pass");
}
`;
    const input = join(dir, "test.c"),
      binary = join(dir, "test");
    writeFileSync(input, prefix + wrapper + fixture);
    const build = spawnSync(
      cc,
      ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", input, "-o", binary],
      { encoding: "utf8" },
    );
    assert.equal(build.status, 0, build.stderr);
    const run = spawnSync(binary, [], { encoding: "utf8", timeout: 10000 });
    assert.equal(run.status, 0, run.stdout + run.stderr);
    assert.match(run.stdout, /flags, overflow, address extent, rounding and callback result pass/);
  });
