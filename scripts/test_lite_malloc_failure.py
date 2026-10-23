#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute actual Wasm lite allocator with bounded growth/stack-guard models."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"


class LiteFailure(unittest.TestCase):
    def test_actual_allocator_and_old_trap_control(self):
        with tempfile.TemporaryDirectory(prefix="wasm-lite-oom-") as tmp:
            work = Path(tmp)
            (work / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (work / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (work / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            source = Path(os.environ.get("WASM_LITE_SOURCE", MUSL / "src/malloc/lite_malloc.c"))
            body = source.read_text()
            begin = body.index("\t\t\t#ifdef __wasm__\n")
            end = body.index("\t\t\t#else\n", begin)
            self.assertIn("UNLOCK(lock);", body[begin:end])
            self.assertIn("errno = ENOMEM;", body[begin:end])
            old = work / "old.c"
            old.write_text(body[:begin] + "\t\t\t#ifdef __wasm__\n\t\t\ta_crash();\n" + body[end:])
            includes = ["-I", tmp, *sum((["-I", str(MUSL / path)] for path in
                        ("arch/wasm32", "arch/generic", "src/include", "src/internal", "include")), [])]
            exports = ["__libc_malloc", "model_allow", "model_stack_guard", "last_error", "lock_state", "grow_count", "break_value"]
            for cc in os.environ.get("WASM_LITE_COMPILERS", "clang").split():
                for bits in (32, 64):
                    flags = [cc, f"--target=wasm{bits}", "-nostdinc", *includes]
                    subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", str(source),
                                    "-o", "/dev/null"], check=True)
                    workload = str(ROOT / "sources/distro/distro/toolchain-smoke/lite-oom.c")
                    subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", workload], check=True)
                    subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", workload,
                                    "-o", "/dev/null"], check=True)
                    for label, actual in (("fixed", source), ("old", old)):
                        binary = work / (label + ".wasm")
                        subprocess.run([*flags, "-O2", "-nostdlib", "-ffreestanding", "-Wl,--no-entry",
                                        "-Wl,-z,stack-size=8192", *["-Wl,--export=" + name for name in exports],
                                        str(actual), str(ROOT / "scripts/fixtures/lite_malloc_model.c"),
                                        "-o", str(binary)], check=True)
                        subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const mod = await WebAssembly.compile(readFileSync(process.argv[1]));
const wide = process.argv[2] === '64', word = n => wide ? BigInt(n) : Number(n);
const fresh = async () => (await WebAssembly.instantiate(mod)).exports;
let api = await fresh();
if (process.argv[3] === 'old') {
  assert.throws(() => api.__libc_malloc(word(32)), WebAssembly.RuntimeError);
  assert.equal(api.lock_state(),1,'old trap abandons locked allocator');
  process.exit(0);
}
const start = api.break_value();
assert.equal(api.__libc_malloc(word(32)),word(0),'first growth exhaustion is recoverable');
assert.equal(api.last_error(),12);
assert.equal(api.lock_state(),0);
assert.equal(api.break_value(),start);
api.model_allow(1);
assert.equal(api.__libc_malloc(word(32)),start);
assert.equal(api.__libc_malloc(word(16)),start+word(32));
const grown = api.break_value(), attempts = api.grow_count();
api.model_allow(0);
assert.equal(api.__libc_malloc(word(131072)),word(0),'later growth exhaustion is recoverable');
assert.equal(api.last_error(),12);
assert.equal(api.break_value(),grown);
assert.equal(api.grow_count(),attempts+1);
assert.equal(api.lock_state(),0);
assert.equal(api.__libc_malloc(word(16)),start+word(48),'failed growth does not consume tail');
api.model_allow(1);
assert.equal(api.__libc_malloc(word(131072)),start+word(64),'subsequent growth works');
const beforeHuge=api.grow_count();
assert.equal(api.__libc_malloc(word(1n << (wide ? 63n : 31n))),word(0));
assert.equal(api.grow_count(),beforeHuge);
assert.equal(api.lock_state(),0);
api=await fresh(); api.model_allow(1); api.model_stack_guard(1);
assert.equal(api.__libc_malloc(word(32)),word(0),'stack crossing guard refuses without trap');
assert.equal(api.grow_count(),0);
assert.equal(api.last_error(),12);
assert.equal(api.lock_state(),0);
api.model_stack_guard(0);
assert.equal(api.__libc_malloc(word(32)),api.break_value()-word(65536));
assert.equal(api.lock_state(),0);
''', str(binary), str(bits), label], check=True)


if __name__ == "__main__":
    unittest.main()
