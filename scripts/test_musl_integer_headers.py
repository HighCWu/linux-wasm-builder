#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile public integer, memfd and syscall headers without building libc."""

import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = r"""
#define _GNU_SOURCE 1
#include <inttypes.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/syscall.h>
_Static_assert(SYS_clone3 == 435, "standard clone3 syscall number");
_Static_assert(_Generic(&memfd_create,
    int (*)(const char *, unsigned): 1, default: 0), "memfd_create prototype");
#define SAME(expr, type) _Static_assert(_Generic((expr), type: 1, default: 0), #expr)
SAME(INT64_C(1), int_least64_t);
SAME(UINT64_C(1), uint_least64_t);
SAME(INTMAX_C(1), intmax_t);
SAME(UINTMAX_C(1), uintmax_t);
#define CHECK(suffix, stype, utype) \
void check_##suffix(stype s, utype u) { \
  printf("%" PRId##suffix " %" PRIi##suffix, s, s); \
  printf("%" PRIu##suffix " %" PRIo##suffix " %" PRIx##suffix " %" PRIX##suffix, u,u,u,u); \
  sscanf("", "%" SCNd##suffix " %" SCNi##suffix, &s, &s); \
  sscanf("", "%" SCNu##suffix " %" SCNo##suffix " %" SCNx##suffix, &u,&u,&u); \
}
CHECK(64, int64_t, uint64_t)
CHECK(LEAST64, int_least64_t, uint_least64_t)
CHECK(FAST64, int_fast64_t, uint_fast64_t)
CHECK(MAX, intmax_t, uintmax_t)
CHECK(PTR, intptr_t, uintptr_t)
"""


class IntegerHeaders(unittest.TestCase):
    def test_public_integer_memory_and_syscall_headers(self):
        for target, arch in [
            ("wasm32", "wasm32"),
            ("wasm64", "wasm32"),
            ("x86_64-linux-gnu", "x86_64"),
        ]:
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory(prefix="musl-headers-") as tmp,
            ):
                bits = pathlib.Path(tmp) / "bits"
                bits.mkdir()
                templates = (MUSL / f"arch/{arch}/bits/alltypes.h.in").read_text() + (
                    MUSL / "include/alltypes.h.in"
                ).read_text()
                generated = subprocess.run(
                    ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                    input=templates,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                (bits / "alltypes.h").write_text(generated.stdout)
                numbers = (MUSL / f"arch/{arch}/bits/syscall.h.in").read_text()
                (bits / "syscall.h").write_text(
                    numbers + numbers.replace("__NR_", "SYS_")
                )
                result = subprocess.run(
                    [
                        "clang",
                        f"--target={target}",
                        "-std=c11",
                        "-fsyntax-only",
                        "-nostdinc",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-Wformat=2",
                        "-I",
                        tmp,
                        "-I",
                        str(MUSL / f"arch/{arch}"),
                        "-I",
                        str(MUSL / "arch/generic"),
                        "-I",
                        str(MUSL / "include"),
                        "-x",
                        "c",
                        "-",
                    ],
                    input=SOURCE,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
