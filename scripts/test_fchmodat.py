#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real musl dispatch, old-table control and native workload; not kernel target evidence."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/fchmodat.c"


class Fchmodat(unittest.TestCase):
    def test_native_workload(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="fchmodat-native-") as tmp:
                source, binary = pathlib.Path(tmp) / "test.c", pathlib.Path(tmp) / "test"
                source.write_text(SOURCE.read_text().replace("/tmp/fchmodat-XXXXXX", tmp + "/files-XXXXXX"))
                subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                                str(source), "-o", str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 3)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)

    def test_existing_libc_dispatch_and_fallback(self):
        with tempfile.TemporaryDirectory(prefix="fchmodat-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                                       input=templates, text=True, capture_output=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            for bits, old in ((32, False), (64, False), (32, True)):
                with self.subTest(bits=bits, old_table=old):
                    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
                    if old:
                        numbers = numbers.replace("#define __NR_fchmodat2 452", "")
                    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
                    includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                                "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"), "-I", str(MUSL / "include")]
                    subprocess.run(["clang", f"--target=wasm{bits}", "-fsyntax-only", "-nostdinc", *includes, str(SOURCE)], check=True)
                    binary = path / "test.wasm"
                    subprocess.run(["clang", f"--target=wasm{bits}", "-O2", "-nostdlib", "-ffreestanding",
                                    "-Wl,--no-entry", "-Wl,--export=run", "-Wl,--export=noflags", "-Wl,--export=nofollow",
                                    "-Wl,--export=last_error", "-Wl,--export=fallback_count", *includes,
                                    str(MUSL / "src/stat/fchmodat.c"), str(ROOT / "scripts/fixtures/fchmodat_calls.c"),
                                    "-o", str(binary)], check=True)
                    subprocess.run(["node", "--input-type=module", "-e", """
import {readFileSync} from 'node:fs';
const wide = process.argv[2] === '64', old = process.argv[3] === 'true';
let calls = 0;
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {linux: {
  syscall(number, ...args) {
    const phase = calls++, nr = phase === 2 ? 53 : 452, flags = phase === 2 ? 0 : phase === 3 ? 256 : 4096;
    if (Number(number) !== nr || args.length !== 6 || Number(args[0]) !== 37 ||
        Number(args[2]) !== (phase < 2 ? 0o640 : 0o600) || Number(args[3]) !== flags ||
        args.slice(4).some(value => Number(value) !== 0)) throw new Error('fchmodat syscall routing or words mismatch');
    const result = phase === 1 ? -9 : phase === 3 ? -38 : 0;
    return wide ? BigInt(result) : result;
  }
}});
const api = instance.exports, first = api.run();
if (old) {
  if (first !== -1 || api.last_error() !== 22 || calls !== 0) throw new Error('old table did not expose the missing path');
} else {
  if (first !== 0 || calls !== 1) throw new Error('existing fchmodat did not use fchmodat2');
  if (api.run() !== -1 || api.last_error() !== 9) throw new Error('kernel errno lost');
  if (api.noflags() !== 0) throw new Error('legacy flags-zero path changed');
  if (api.nofollow() !== -1 || api.last_error() !== 2 || api.fallback_count() !== 1 || calls !== 4)
    throw new Error('old-kernel ENOSYS fallback changed');
}
""", str(binary), str(bits), str(old).lower()], check=True)


if __name__ == "__main__":
    unittest.main()
