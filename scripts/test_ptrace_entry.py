#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native ptrace birth ordering and tiny Wasm trampoline model, not target acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/fork-continuation/ptrace-entry.c"
SKIP_STOP = r'''
#define _GNU_SOURCE
#include <stdarg.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
static pid_t newborn;
long __real_ptrace(enum __ptrace_request, ...);
pid_t __real_waitpid(pid_t,int *,int);
long __wrap_ptrace(enum __ptrace_request op, ...) {
    va_list ap;
    va_start(ap,op);
    pid_t pid = va_arg(ap,pid_t);
    void *addr = va_arg(ap,void *), *data = va_arg(ap,void *);
    va_end(ap);
    long result = __real_ptrace(op,pid,addr,data);
    if (!result && op == PTRACE_GETEVENTMSG) newborn = *(unsigned long *)data;
    return result;
}
pid_t __wrap_waitpid(pid_t pid,int *status,int flags) {
    pid_t result = __real_waitpid(pid,status,flags);
    if (pid == newborn && result == pid && status && WIFSTOPPED(*status)) {
        if (__real_ptrace(PTRACE_CONT,pid,(void *)0,(void *)0)) return -1;
        return __real_waitpid(pid,status,flags);
    }
    return result;
}
'''


class PtraceEntry(unittest.TestCase):
    def test_native_and_skipped_birth_stop_control(self):
        with tempfile.TemporaryDirectory(prefix="ptrace-entry-") as tmp:
            binary, shim = Path(tmp) / "entry", Path(tmp) / "skip.c"
            shim.write_text(SKIP_STOP)
            for cc in ("gcc", "clang"):
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCE)]
                for negative in (False, True):
                    extra = [str(shim), "-Wl,--wrap=ptrace", "-Wl,--wrap=waitpid"] if negative else []
                    subprocess.run([*flags, *extra, "-o", str(binary)], check=True)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                    if negative:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("newborn stops before first application operation", result.stdout)
                        self.assertNotIn("::vm-test::pass", result.stdout)
                    else:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertEqual(result.stdout.count(" pass\n"), 3)
                        self.assertEqual(result.stdout.count("::vm-test::pass"), 1)

    def test_real_trampoline_body_and_old_body_control(self):
        source = (MUSL / "src/thread/wasm32/clone.c").read_text()
        begin = source.index("static void clone_entry_inner(")
        body = source[begin:source.index("\n}", begin) + 2]
        old = body.replace("  __syscall(SYS_gettid);\n", "")
        self.assertNotEqual(body, old)
        prefix = r'''
#define SYS_gettid 178
#define SYS_exit 93
__attribute__((import_module("test"), import_name("syscall")))
extern long model_syscall(long,long);
__attribute__((import_module("test"), import_name("entered")))
extern void entered(void);
#define __syscall(n,...) model_syscall(n, ((long[]){0, ##__VA_ARGS__})[(n)==SYS_exit])
'''
        suffix = r'''
static int callback(void *arg) { (void)arg; entered(); return 42; }
void run(void) { clone_entry_inner(callback,(void *)0); }
'''
        with tempfile.TemporaryDirectory(prefix="ptrace-entry-model-") as tmp:
            unit, binary = Path(tmp) / "entry.c", Path(tmp) / "entry.wasm"
            for bits in (32, 64):
                for implementation, fixed in ((body, True), (old, False)):
                    unit.write_text(prefix + implementation + suffix)
                    subprocess.run([os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}",
                                    "-O2", "-nostdlib", "-ffreestanding", "-Wl,--no-entry",
                                    "-Wl,--export=run", str(unit), "-o", str(binary)], check=True)
                    subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const fixed = process.argv[2] === 'True', wide = process.argv[3] === '64';
for (const pending of [false,true]) {
  let started = 0, checkpoints = 0;
  const killed = Symbol('pending fatal signal'), exited = Symbol('exit');
  const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {test: {
    entered() { started++; },
    syscall(number, status) {
      if (Number(number) === 178) { checkpoints++; if (pending) throw killed; return wide ? 1n : 1; }
      assert.equal(Number(number),93);
      assert.equal(Number(status),42);
      throw exited;
    },
  }});
  assert.throws(() => instance.exports.run(), error => error === (pending && fixed ? killed : exited));
  assert.equal(started, pending && fixed ? 0 : 1);
  assert.equal(checkpoints, fixed ? 1 : 0);
}
''', str(binary), str(fixed), str(bits)], check=True)

    def test_wasm_frontends_and_existing_architecture_source(self):
        with tempfile.TemporaryDirectory(prefix="ptrace-entry-abi-") as tmp:
            path = Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            unistd = (MUSL / "include/unistd.h").read_text()
            gate = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
            self.assertIn(gate, unistd)
            (path / "unistd.h").write_text(unistd.replace(gate, "pid_t fork(void);\npid_t _Fork(void);"))
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"),
                        "-I", str(MUSL / "include")]
            for bits in (32, 64):
                for source in (SOURCE, MUSL / "src/thread/wasm32/clone.c"):
                    common = [os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}", "-nostdinc", *includes]
                    warnings = ["-Wall", "-Wextra", "-Werror"]
                    if source != SOURCE:
                        warnings.append("-Wno-unused-parameter")
                    subprocess.run([*common, "-fsyntax-only", *warnings, str(source)], check=True)
                    subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(source),
                                    "-o", "/dev/null"], check=True)


if __name__ == "__main__":
    unittest.main()
