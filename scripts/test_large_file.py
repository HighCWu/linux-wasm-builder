#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native sparse-file workload and Wasm libc compilation, not a target kernel run."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/large-file.c"
MUSL = ROOT / "sources/musl"


class LargeFile(unittest.TestCase):
    def test_native_sparse_workload(self):
        for compiler in ("gcc", "clang"):
            with self.subTest(compiler=compiler), tempfile.TemporaryDirectory(prefix="large-file-") as tmp:
                source, binary = pathlib.Path(tmp) / "test.c", pathlib.Path(tmp) / "test"
                source.write_text(SOURCE.read_text().replace("/tmp/large-file-XXXXXX", tmp + "/sparse-XXXXXX"))
                subprocess.run([compiler, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                                str(source), "-o", str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                self.assertEqual(result.stdout.count(" pass\n"), 4)

    def test_existing_libc_workload_both_widths(self):
        with tempfile.TemporaryDirectory(prefix="large-file-abi-") as tmp:
            bits = pathlib.Path(tmp) / "bits"
            bits.mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                                       input=templates, capture_output=True, text=True, check=True)
            (bits / "alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (bits / "syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            for target in ("wasm32", "wasm64"):
                with self.subTest(target=target):
                    subprocess.run(["clang", f"--target={target}", "-fsyntax-only", "-std=c11",
                                    "-nostdinc", "-Wall", "-Wextra", "-Werror", "-isystem", tmp,
                                    "-isystem", str(MUSL / "arch/wasm32"), "-isystem", str(MUSL / "arch/generic"),
                                    "-isystem", str(MUSL / "include"), str(SOURCE)], check=True)
                    binary = pathlib.Path(tmp) / "sync.wasm"
                    subprocess.run(["clang", f"--target={target}", "-O2", "-nostdlib", "-ffreestanding",
                                    "-Wl,--no-entry", "-Wl,--export=run", "-I", tmp,
                                    "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                                    "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"),
                                    "-I", str(MUSL / "include"), str(MUSL / "src/linux/sync_file_range.c"),
                                    str(ROOT / "scripts/fixtures/sync_range.c"), "-o", str(binary)], check=True)
                    subprocess.run(["node", "--input-type=module", "-e", """
import {readFileSync} from 'node:fs';
const wide = process.argv[2] === 'wasm64';
const expected = wide ? [84n, 7n, 0x1234567889abcdefn, 0x234567899abcdef0n, 5n, 0n, 0n] :
  [84n, 7n, 5n, 0x89abcdefn, 0x12345678n, 0x9abcdef0n, 0x23456789n];
let calls = 0;
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {linux: {
  syscall(...args) {
    calls++;
    if (args.length !== 7 || args.some((v, i) => BigInt.asUintN(wide ? 64 : 32, BigInt(v)) !== expected[i]))
      throw new Error('real musl sync_file_range argument order or width mismatch');
    return wide ? 0n : 0;
  }
}});
if (instance.exports.run() !== 0 || calls !== 1) throw new Error('wrapper did not reach syscall import');
""", str(binary), target], check=True)


if __name__ == "__main__":
    unittest.main()
