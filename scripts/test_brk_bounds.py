#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute the exact existing Wasm brk implementation with tiny capacity models."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"


class BrkBounds(unittest.TestCase):
    def test_real_wasm_body_without_large_memory_allocation(self):
        with tempfile.TemporaryDirectory(prefix="wasm-brk-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            header = path / "model.h"
            header.write_text("#include <stddef.h>\nsize_t brk_model_size(int);\nsize_t brk_model_grow(int,size_t);\n")
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"), "-I", str(MUSL / "include")]
            compilers = os.environ.get("WASM_BRK_COMPILERS", "clang").split()
            self.assertTrue(compilers, "at least one Wasm compiler must execute the model")
            for cc in compilers:
                for bits in (32, 64):
                    with self.subTest(cc=cc, bits=bits):
                        binary = path / "brk.wasm"
                        source = pathlib.Path(os.environ.get("WASM_BRK_SOURCE", MUSL / "src/linux/brk.c"))
                        common = [cc, f"--target=wasm{bits}", "-nostdinc", *includes, "-include", str(header),
                                  "-D__builtin_wasm_memory_size=brk_model_size",
                                  "-D__builtin_wasm_memory_grow=brk_model_grow"]
                        subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(source),
                                        "-o", "/dev/null"], check=True)
                        driver = ROOT / "sources/distro/distro/toolchain-smoke/brk.c"
                        subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(driver)], check=True)
                        subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(driver),
                                        "-o", "/dev/null"], check=True)
                        exports = ["brk", "sbrk", "model_configure", "last_error", "lock_state", "grow_count", "grow_delta"]
                        subprocess.run([*common, "-O2", "-nostdlib", "-ffreestanding", "-Wl,--no-entry",
                                        "-Wl,-z,stack-size=8192", *["-Wl,--export=" + name for name in exports],
                                        str(source), str(ROOT / "scripts/fixtures/brk_model.c"), "-o", str(binary)], check=True)
                        subprocess.run(["node", "--input-type=module", "-e", """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const module = await WebAssembly.compile(readFileSync(process.argv[1]));
const wide = process.argv[2] === '64';
const word = n => wide ? BigInt(n) : Number(n);
const uint = n => wide ? BigInt.asUintN(64,n) : BigInt(n >>> 0);
const zero = word(0), minusOne = word(-1), max = (1n << (wide ? 64n : 32n)) - 1n;
const fresh = async (pages, maximum) => {
  const api = (await WebAssembly.instantiate(module)).exports;
  api.model_configure(word(pages),word(maximum));
  return api;
};
let api = await fresh(1, wide ? 262144 : 65536);
if (process.argv[3] !== 'capacity') {
const start = uint(api.sbrk(zero));
assert.ok(start > 0n && start <= 65536n);
assert.equal(api.grow_count(),zero);
for (const negative of [-1n, -(1n << (wide ? 63n : 31n))]) {
  assert.equal(api.sbrk(word(negative)),minusOne,'negative increment refused');
  assert.equal(api.last_error(),12);
  assert.equal(api.grow_count(),zero,'negative increment cannot request growth');
  assert.equal(uint(api.sbrk(zero)),start);
  assert.equal(api.lock_state(),0);
}
assert.equal(uint(api.sbrk(word(65536))),start);
assert.equal(uint(api.sbrk(zero)),start + 65536n);
assert.equal(api.grow_delta(),word(1));
const before = uint(api.sbrk(zero));
api.model_configure(word(2),word(2));
assert.equal(api.brk(word(2*65536+1)), -1);
assert.equal(uint(api.sbrk(zero)),before);
assert.equal(api.last_error(),12);
assert.equal(api.lock_state(),0);
}
// Model a pre-existing full-capacity memory; never allocate a 4/16 GiB ArrayBuffer.
api = await fresh(wide ? 262144 : 65536,wide ? 262144 : 65536);
const fullStart = uint(api.sbrk(zero));
assert.ok(fullStart > 0n && fullStart <= 65536n,'full capacity query must not overflow');
assert.equal(api.grow_count(),zero);
assert.equal(uint(api.sbrk(word(1))),fullStart);
assert.equal(api.grow_count(),zero);
if (process.argv[3] === 'capacity') process.exit(0);
// Reach the highest representable break in a fake-capacity model, then reject wrap.
api = await fresh(1,max/65536n+1n);
assert.equal(api.brk(word(max-7n)),0);
const high = uint(api.sbrk(zero));
assert.equal(high,max-7n);
api.model_configure(word(max/65536n+1n),word(max/65536n+1n));
assert.equal(api.sbrk(word(16)),minusOne);
assert.equal(api.grow_count(),zero);
assert.equal(uint(api.sbrk(zero)),high);
assert.equal(api.lock_state(),0);
""", str(binary), str(bits), os.environ.get("WASM_BRK_CASE", "all")], check=True)


if __name__ == "__main__":
    unittest.main()
