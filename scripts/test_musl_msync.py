#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the public declaration and actual wrapper, without building libc."""

import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"


class MsyncContract(unittest.TestCase):
    def test_real_mapping_sources_with_musl_build_feature_flags(self):
        for target in ("wasm32", "wasm64"):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix="mapping-syntax-") as tmp:
                bits = pathlib.Path(tmp) / "bits"
                bits.mkdir()
                templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
                    MUSL / "include/alltypes.h.in"
                ).read_text()
                generated = subprocess.run(
                    ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                    input=templates, text=True, capture_output=True, check=True,
                )
                (bits / "alltypes.h").write_text(generated.stdout)
                numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
                (bits / "syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
                for name in ("mmap.c", "mremap.c"):
                    checked = subprocess.run([
                        "clang", f"--target={target}", "-fsyntax-only", "-std=c99",
                        "-ffreestanding", "-nostdinc", "-matomics", "-mbulk-memory",
                        "-D_XOPEN_SOURCE=700", "-I", str(MUSL / "arch/wasm32"),
                        "-I", str(MUSL / "arch/generic"), "-I", str(MUSL / "src/include"),
                        "-I", str(MUSL / "src/internal"), "-I", tmp,
                        "-I", str(MUSL / "include"), str(MUSL / "src/mman" / name),
                    ], text=True, capture_output=True)
                    self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_public_declaration_on_both_wasm_widths(self):
        for target in ("wasm32", "wasm64"):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix="msync-headers-") as tmp:
                bits = pathlib.Path(tmp) / "bits"
                bits.mkdir()
                templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
                    MUSL / "include/alltypes.h.in"
                ).read_text()
                generated = subprocess.run(
                    ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                    input=templates, text=True, capture_output=True, check=True,
                )
                (bits / "alltypes.h").write_text(generated.stdout)
                result = subprocess.run(
                    [
                        "clang", f"--target={target}", "-fsyntax-only", "-std=c11",
                        "-nostdinc", "-Wall", "-Wextra", "-Werror",
                        "-I", tmp, "-I", str(MUSL / "arch/wasm32"),
                        "-I", str(MUSL / "arch/generic"), "-I", str(MUSL / "include"),
                        "-x", "c", "-",
                    ],
                    input="""
#define _GNU_SOURCE
#include <sys/mman.h>
int (*operation)(void *, size_t, int) = msync;
void *(*remap_operation)(void *, size_t, size_t, int, ...) = mremap;
_Static_assert(MS_SYNC == 4, "standard flags");
_Static_assert(sizeof(size_t) == sizeof(void *), "native size_t");
""",
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_wasm_wrapper_forwards_arguments_and_result(self):
        for compiler in ("gcc", "clang"):
            with self.subTest(compiler=compiler), tempfile.TemporaryDirectory(prefix="msync-forward-") as tmp:
                root = pathlib.Path(tmp)
                # Rename the public symbol so accidentally excluding the Wasm
                # wrapper cannot fall back to the host libc's implementation.
                (root / "syscall.h").write_text("""
#include <stddef.h>
#include <sys/syscall.h>
int msync_test_forward(long, void *, size_t, int);
#define syscall_cp(n, p, len, flags) msync_test_forward(n, p, len, flags)
""")
                (root / "main.c").write_text("""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <sys/mman.h>
#include <sys/syscall.h>
static int calls;
static void *expected_pointer;
static size_t expected_length;
int msync_test_forward(long number, void *pointer, size_t length, int flags)
{
    assert(number == SYS_msync);
    assert(pointer == expected_pointer);
    assert(length == expected_length);
    assert(flags == MS_SYNC);
    if (++calls == 1) { errno = ENOSYS; return -1; }
    return 0;
}
int main(void)
{
    expected_pointer = (void *)(uintptr_t)0x12345;
    expected_length = sizeof(size_t) == 8 ? (size_t)UINT64_C(0x100000007) : 7;
    assert(msync(expected_pointer, expected_length, MS_SYNC) == -1);
    assert(errno == ENOSYS && calls == 1);
    assert(msync(expected_pointer, expected_length, MS_SYNC) == 0);
    assert(calls == 2);
    return 0;
}
""")
                binary = root / "msync-test"
                compiled = subprocess.run(
                    [
                        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-D__wasm__", "-Dmsync=wasm_test_msync", "-I", tmp,
                        str(MUSL / "src/mman/msync.c"), str(root / "main.c"), "-o", str(binary),
                    ],
                    text=True, capture_output=True,
                )
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
