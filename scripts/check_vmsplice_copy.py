#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual Wasm iter_to_pipe body with modeled page/uaccess ownership, not VFS acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1] if len(sys.argv) > 1 else root / "sources/linux/fs/splice.c").read_text()
start = source.index("static ssize_t iter_to_pipe(", source.index("#ifdef CONFIG_WASM"))
body = source[start:source.index("\n#else", start)]
shim = r"""
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#define PAGE_SIZE 64
#define GFP_USER 0
#define min_t(type,a,b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
struct page { unsigned char data[PAGE_SIZE]; };
struct pipe_buffer { struct page *page; const void *ops; unsigned flags, offset, len; };
struct pipe_inode_info { struct pipe_buffer bufs[4]; unsigned head, limit; };
struct iov_iter { unsigned char data[256]; size_t pos, count, valid; };
static int live, allocations, fail_alloc, reject_add, reads, user_page_pipe_buf_ops;
static size_t iov_iter_count(struct iov_iter *i) { return i->count - i->pos; }
static int pipe_is_full(struct pipe_inode_info *p) { return p->head == p->limit; }
static struct page *alloc_page(int flags) {
    (void)flags;
    if (++allocations == fail_alloc) return NULL;
    struct page *p = malloc(sizeof *p);
    assert(p); memset(p, 0xa5, sizeof *p); live++; return p;
}
static void put_page(struct page *p) { assert(p && live > 0); live--; free(p); }
static size_t copy_page_from_iter(struct page *p, size_t off, size_t n, struct iov_iter *i) {
    reads++; assert(off == 0 && n <= PAGE_SIZE);
    if (i->pos >= i->valid) return 0;
    if (n > i->valid - i->pos) n = i->valid - i->pos;
    memcpy(p->data, i->data + i->pos, n); i->pos += n; return n;
}
static ssize_t add_to_pipe(struct pipe_inode_info *p, struct pipe_buffer *b) {
    if (reject_add || pipe_is_full(p)) { put_page(b->page); return reject_add ? -EPIPE : -EAGAIN; }
    assert(b->ops == &user_page_pipe_buf_ops && !b->offset && b->len <= PAGE_SIZE);
    p->bufs[p->head++] = *b; return b->len;
}
static void iov_iter_revert(struct iov_iter *i, size_t n) { assert(i->pos >= n); i->pos -= n; }
"""
checks = r"""
static void clear(struct pipe_inode_info *p) {
    for (unsigned n = 0; n < p->head; n++) put_page(p->bufs[n].page);
    p->head = 0; assert(live == 0);
}
static struct iov_iter input(size_t count, size_t valid) {
    struct iov_iter i = { .count = count, .valid = valid };
    for (size_t n = 0; n < sizeof i.data; n++) i.data[n] = (unsigned char)(n * 7 + 3);
    return i;
}
int main(void) {
    struct pipe_inode_info p = { .limit = 4 };
    struct iov_iter i = input(145, 145);
    assert(iter_to_pipe(&i, &p, 8) == 145 && i.pos == 145 && p.head == 3);
    size_t off = 0;
    for (unsigned n = 0; n < p.head; n++) {
        assert(p.bufs[n].flags == 8 && !memcmp(p.bufs[n].page->data, i.data + off, p.bufs[n].len));
        off += p.bufs[n].len;
    }
    memset(i.data, 0, sizeof i.data);
    assert(p.bufs[0].page->data[0] == 3); /* no retained user alias */
    clear(&p);
    i = input(145, 70);
    assert(iter_to_pipe(&i, &p, 0) == 70 && i.pos == 70 && p.head == 2);
    clear(&p);
    i = input(1, 0);
    assert(iter_to_pipe(&i, &p, 0) == -EFAULT && i.pos == 0 && !p.head && !live);
    fail_alloc = allocations + 1;
    i = input(145, 145);
    assert(iter_to_pipe(&i, &p, 0) == -ENOMEM && i.pos == 0 && !live);
    fail_alloc = allocations + 2;
    assert(iter_to_pipe(&i, &p, 0) == PAGE_SIZE && i.pos == PAGE_SIZE && p.head == 1);
    clear(&p); fail_alloc = 0;
    p.limit = 1; i = input(145, 145);
    assert(iter_to_pipe(&i, &p, 0) == PAGE_SIZE && i.pos == PAGE_SIZE && p.head == 1);
    int before = reads, allocated = allocations;
    assert(iter_to_pipe(&i, &p, 0) == -EAGAIN && reads == before && allocations == allocated);
    clear(&p); p.limit = 4;
    reject_add = 1; i = input(145, 145);
    assert(iter_to_pipe(&i, &p, 0) == -EPIPE && i.pos == 0 && !live && !p.head);
    reject_add = 0; i = input(0, 0);
    assert(iter_to_pipe(&i, &p, 0) == 0 && !live && !p.head);
    i = input(145, 145);
    assert(iter_to_pipe(&i, &p, 0) == 145); clear(&p);
    return 0;
}
"""
compiler = os.environ.get("CC", "clang")
with tempfile.TemporaryDirectory(prefix="vmsplice-copy-") as tmp:
    path = Path(tmp)
    unit, binary = path / "copy.c", path / "copy"
    unit.write_text(shim + body + checks)
    subprocess.run([compiler, "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1",
                                     "UBSAN_OPTIONS": "halt_on_error=1"}, check=True)
    if "clang" in Path(compiler).name:
        subprocess.run([compiler, "--analyze", "-Xanalyzer", "-analyzer-werror", str(unit),
                        "-o", "/dev/null"], check=True)
    # Removing the failure-path iterator rollback must break the ownership contract.
    bad = body.replace("\t\t\tiov_iter_revert(from, buf.len);", "")
    assert bad != body
    unit.write_text(shim + bad + checks)
    subprocess.run([compiler, "-O1", "-Wno-unused-function", str(unit), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True)
    assert result.returncode != 0 and b"i.pos == 0" in result.stderr, result.stderr
print("vmsplice copy: payload, bounds, partial faults, allocation failure, rejected insertion, ownership and rollback control passed")

# The workload uses only existing headers and standard syscall numbers. Build
# an isolated header tree, as in Nix's individual-source input, for both ABIs.
musl = root / "sources/musl"
workload = root / "sources/distro/distro/toolchain-smoke/vmsplice.c"
with tempfile.TemporaryDirectory(prefix="vmsplice-abi-") as tmp:
    path = Path(tmp)
    (path / "bits").mkdir()
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (path / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    unit = path / "vmsplice.c"
    unit.write_text(workload.read_text())
    includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                "-I", str(musl / "include")]
    for bits in (32, 64):
        common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
        subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(unit)], check=True)
        subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(unit),
                        "-o", "/dev/null"], check=True)
    for cc in ("gcc", "clang"):
        binary = path / "native"
        subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                        str(unit), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=15,
                                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1",
                                     "UBSAN_OPTIONS": "halt_on_error=1"})
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count(" pass\n") == 3 and result.stdout.count("::vm-test::pass") == 1
print("vmsplice workload: native reference and wasm32/64 frontends/static analysis passed; target kernel execution still required")
