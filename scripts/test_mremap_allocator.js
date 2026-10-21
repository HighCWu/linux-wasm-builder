// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

for (const cc of ["gcc", "clang"])
  test(`${cc}: native fixed-move workload validates copied data and exact destination`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), "mremap-fixed-native-"));
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    const source = readFileSync(
      new URL("../sources/distro/distro/toolchain-smoke/mremap.c", import.meta.url),
      "utf8",
    );
    const anchor = "move, base + 5 * page) == base + 5 * page";
    const wrong = source.replace(anchor, "MREMAP_MAYMOVE, base + 5 * page) == base + 5 * page");
    assert.notEqual(source, wrong);
    for (const [mode, body] of [
      ["normal", source],
      ["not-fixed", wrong],
    ]) {
      const input = join(dir, "test.c"),
        binary = join(dir, "test");
      writeFileSync(
        input,
        "#define main original_mremap_main\n" +
          body +
          '\n#undef main\nint main(void) { fixed_move(sysconf(_SC_PAGESIZE)); puts("native fixed move pass"); return 0; }\n',
      );
      const build = spawnSync(cc, ["-O2", "-Wall", "-Wextra", "-Werror", input, "-o", binary], {
        encoding: "utf8",
      });
      assert.equal(build.status, 0, build.stderr);
      const run = spawnSync(binary, [], { encoding: "utf8", timeout: 10000 });
      assert.equal(run.error, undefined);
      if (mode === "normal") {
        assert.equal(run.status, 0, run.stdout + run.stderr);
        assert.match(
          run.stdout,
          /fixed cross-backing replacement, zero expansion and full-source cleanup pass/,
        );
      } else {
        assert.notEqual(run.status, 0);
        assert.match(run.stdout, /fixed interior growth/);
      }
    }
  });

for (const cc of ["gcc", "clang"])
  test(`${cc}: restored Wasm libc wrapper passes six machine words and retains errno`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), "wasm-mremap-wrapper-"));
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    const source = readFileSync(
      new URL("../sources/musl/src/mman/mremap.c", import.meta.url),
      "utf8",
    );
    const start = source.indexOf("void *__mremap(");
    const end = source.indexOf("\nweak_alias(__mremap, mremap);", start);
    assert.ok(start > 0 && end > start);
    const prefix = `
#define _GNU_SOURCE
#define __wasm__ 1
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdarg.h>
#include <sys/mman.h>
#define SYS_mremap 216
static int waits, calls, failure;
static long words[6];
static void __vm_wait(void) { waits++; }
static long forward(long number, ...) {
  assert(number == 216); calls++;
  va_list args; va_start(args, number);
  for (int i = 0; i < 6; i++) words[i] = va_arg(args, long);
  va_end(args);
  if (failure) { errno = ENOMEM; return -1; }
  return 0x100030000L;
}
#define syscall forward
`;
    const fixture = `
int main(void) {
  void *old = (void *)(uintptr_t)0x100010000UL;
  void *next = (void *)(uintptr_t)0x100030000UL;
  assert(__mremap(old, 0x100000007UL, 0x100020000UL, 1) == next);
  assert(calls == 1 && words[0] == (long)old && words[1] == 0x100000007L &&
    words[2] == 0x100020000L && words[3] == 1 && words[4] == 0 && words[5] == 0);
  failure = 1;
  assert(__mremap(old, 65536, 131072, 3, next) == MAP_FAILED && errno == ENOMEM);
  assert(calls == 2 && waits == 1 && words[3] == 3 && words[4] == (long)next && words[5] == 0);
  assert(__mremap(old, 65536, PTRDIFF_MAX, 0) == MAP_FAILED && errno == ENOMEM && calls == 2);
}
`;
    const input = join(dir, "wrapper.c"),
      binary = join(dir, "wrapper");
    writeFileSync(input, prefix + source.slice(start, end) + fixture);
    const build = spawnSync(
      cc,
      ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", input, "-o", binary],
      { encoding: "utf8" },
    );
    assert.equal(build.status, 0, build.stderr);
    const run = spawnSync(binary, [], { encoding: "utf8", timeout: 10000 });
    assert.equal(run.status, 0, run.stdout + run.stderr);
  });

for (const cc of ["gcc", "clang"])
  test(`${cc}: exact musl direct allocator resize with address/undefined sanitizers`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), "wasm-mremap-allocator-"));
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    const source = readFileSync(
      new URL("../sources/musl/src/mman/mmap.c", import.meta.url),
      "utf8",
    );
    const start = source.indexOf("#ifndef WASM_MMAP_DEDUP_SEARCH");
    const end = source.indexOf("\n#endif\n\nvoid *__mmap", start);
    assert.ok(start > 0 && end > start);
    const prefix = `
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sys/mman.h>
#define PAGESIZE 65536
static int live_allocations, fail_after = -1;
static void (*allocation_hook)(void);
static void *allocate(size_t n) {
  if (allocation_hook) { void (*hook)(void) = allocation_hook; allocation_hook = NULL; hook(); }
  if (fail_after == 0) { errno = ENOMEM; return NULL; }
  if (fail_after > 0) fail_after--;
  void *p = malloc(n); if (p) live_allocations++; return p;
}
static void release(void *p) { if (p) { live_allocations--; free(p); } }
#define __libc_malloc allocate
#define __libc_free release
`;
    const fixture = readFileSync(new URL("fixtures/mremap_allocator.c", import.meta.url), "utf8");
    for (const broken of [false, true]) {
      const body = source.slice(start, end);
      const changed = broken
        ? body.replace(
            "memcpy(prepared->address, (void *)begin, old_length);",
            "/* deliberately lose copied contents */",
          )
        : body;
      if (broken) assert.ok(changed !== body, "copy negative-control anchor must match");
      const input = join(dir, "test.c"),
        binary = join(dir, "test");
      writeFileSync(input, prefix + changed + fixture);
      const build = spawnSync(
        cc,
        [
          "-std=c11",
          "-O1",
          "-g",
          "-Wall",
          "-Wextra",
          "-Werror",
          "-fsanitize=address,undefined",
          "-fno-omit-frame-pointer",
          "-fno-pie",
          "-no-pie",
          "-pthread",
          input,
          "-o",
          binary,
        ],
        { encoding: "utf8" },
      );
      assert.equal(build.status, 0, build.stderr);
      if (cc === "clang" && !broken) {
        const review = spawnSync(
          cc,
          [
            "--analyze",
            "-Xanalyzer",
            "-analyzer-werror",
            "-Xanalyzer",
            "-analyzer-output=text",
            input,
            "-o",
            "/dev/null",
          ],
          { encoding: "utf8" },
        );
        assert.equal(review.status, 0, review.stderr);
      }
      const run = spawnSync(binary, [], { encoding: "utf8", timeout: 20000 });
      assert.equal(run.error, undefined);
      if (broken) {
        assert.notEqual(run.status, 0);
        assert.match(run.stderr, /copy\[i\] == 37/);
      } else {
        assert.equal(run.status, 0, run.stdout + run.stderr);
        assert.match(run.stdout, /resize, relocation, zero tail, failure rollback, revalidation/);
      }
    }
  });
