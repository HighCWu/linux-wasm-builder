#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Wasm header analysis and isolated freeze-body model; never change host namespaces."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/fork-continuation/namespaces.c"
HOLDER = ROOT / "sources/distro/distro/busybox/namespace-holder.c"


class Namespaces(unittest.TestCase):
    def test_native_execution_is_not_permitted(self):
        for source in (SOURCE, HOLDER):
            result = subprocess.run(["cc", "-fsyntax-only", str(source)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("never the build host", result.stderr)

    def test_wasm_frontends_and_static_analysis(self):
        musl = ROOT / "sources/musl"
        with tempfile.TemporaryDirectory(prefix="namespaces-abi-") as tmp:
            path = Path(tmp)
            (path / "bits").mkdir()
            templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            unistd = (musl / "include/unistd.h").read_text()
            gate = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
            self.assertIn(gate, unistd)
            (path / "unistd.h").write_text(unistd.replace(gate, "pid_t fork(void);\npid_t _Fork(void);"))
            includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                        "-I", str(musl / "include")]
            for cc in (os.environ.get("WASM_CC", "clang"),):
                for bits in (32, 64):
                    flags = [cc, f"--target=wasm{bits}", "-nostdinc", *includes]
                    for source in (SOURCE, HOLDER):
                        subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(source)], check=True)
                        subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", str(source),
                                        "-o", "/dev/null"], check=True)

    def test_no_vdso_commit_freezes_under_the_writer_lock(self):
        source = Path(os.environ.get("WASM_TIME_NAMESPACE_SOURCE", ROOT / "sources/linux/kernel/time/namespace.c")).read_text()
        begin = source.index("void timens_commit(")
        end = source.index("\n}\n", begin) + 3
        body = source[begin:end]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <pthread.h>
struct task_struct { int unused; };
struct time_namespace { bool frozen_offsets; };
static pthread_mutex_t timens_offset_lock = PTHREAD_MUTEX_INITIALIZER;
static int lock_count;
static pthread_mutex_t *acquire(pthread_mutex_t *m) {
    assert(pthread_mutex_lock(m) == 0); ++lock_count; return m;
}
static void release(pthread_mutex_t **m) { assert(pthread_mutex_unlock(*m) == 0); }
#define guard(kind) pthread_mutex_t *held __attribute__((cleanup(release))) = acquire
BODY
int main(void) {
    struct task_struct task = {0};
    struct time_namespace ns = {0};
    timens_commit(&task, &ns);
    assert(ns.frozen_offsets && lock_count == 1);
    timens_commit(&task, &ns);
    assert(ns.frozen_offsets && lock_count == 2);
    assert(pthread_mutex_trylock(&timens_offset_lock) == 0);
    assert(pthread_mutex_unlock(&timens_offset_lock) == 0);
}
'''
        # guard(mutex)(&lock) is a cleanup-based scope lock in Linux. Use a
        # host shim for that primitive only; the commit body stays verbatim.
        with tempfile.TemporaryDirectory(prefix="timens-freeze-") as tmp:
            unit, binary = Path(tmp) / "freeze.c", Path(tmp) / "freeze"
            for cc in ("gcc", "clang"):
                for implementation, success in ((body, True), (body.replace("ns->frozen_offsets = true;", "(void)ns;"), False)):
                    unit.write_text(harness.replace("BODY", implementation))
                    subprocess.run([cc, "-pthread", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                                    "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode == 0, success, result.stderr)


if __name__ == "__main__":
    unittest.main()
