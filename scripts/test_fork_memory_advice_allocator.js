// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("host reference preserves allocator fork-advice records", (t) => {
  const cc = process.env.CC || "cc";
  const dir = mkdtempSync(join(tmpdir(), "fork-memory-advice-allocator-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));

  const source = readFileSync(new URL("../sources/musl/src/mman/mmap.c", import.meta.url), "utf8");
  const start = source.indexOf("#ifndef WASM_MMAP_DEDUP_SEARCH");
  const end = source.indexOf("\n#endif\n\nvoid *__mmap", start);
  assert.ok(start > 0 && end > start, "must extract the real Wasm allocator body");

  const prefix = `
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sys/mman.h>
#define PAGESIZE 65536
static int live_allocations, fail_after = -1;
static void *allocate(size_t n) {
  if (fail_after == 0) { errno = ENOMEM; return NULL; }
  if (fail_after > 0) fail_after--;
  void *p = malloc(n); if (p) live_allocations++; return p;
}
static void release(void *p) { if (p) { live_allocations--; free(p); } }
#define __libc_malloc allocate
#define __libc_free release
`;
  const fixture = readFileSync(
    new URL("fixtures/fork_memory_advice_allocator.c", import.meta.url),
    "utf8",
  );
  const input = join(dir, "allocator.c");
  const binary = join(dir, "allocator");
  writeFileSync(input, prefix + source.slice(start, end) + fixture);

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

  const run = spawnSync(binary, [], { encoding: "utf8", timeout: 20000 });
  assert.equal(run.error, undefined);
  assert.equal(run.status, 0, run.stdout + run.stderr);
  assert.equal(
    run.stdout.trim(),
    "allocator fork advice: descriptor splits, atomic failure, unmap and remap inheritance pass",
  );
});
