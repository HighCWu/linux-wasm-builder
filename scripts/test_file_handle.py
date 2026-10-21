#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Existing libc dispatch and native smoke; privileged ext4 needs real target CI."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/file-handle.c"


class FileHandle(unittest.TestCase):
    def test_native_and_static_analysis(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="handle-native-") as tmp:
                binary = pathlib.Path(tmp) / "test"
                subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                                str(SOURCE), "-o", str(binary)], check=True)
                result = subprocess.run([str(binary), tmp], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue("target still required" in result.stdout or "::vm-test::pass" in result.stdout,
                                result.stdout)
                self.assertEqual(list(pathlib.Path(tmp).iterdir()), [binary])

    def test_exact_upstream_wrappers_and_both_word_widths(self):
        with tempfile.TemporaryDirectory(prefix="handle-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"), "-I", str(MUSL / "include")]
            for bits in (32, 64):
                with self.subTest(bits=bits):
                    common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                    subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
                    analyzed = subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror",
                                               str(SOURCE), "-o", "/dev/null"], capture_output=True, text=True)
                    self.assertEqual(analyzed.returncode, 0, analyzed.stderr)
                    binary = path / "test.wasm"
                    compiled = subprocess.run([*common, "-O2", "-nostdlib", "-ffreestanding", "-Wl,--no-entry", "-Wl,--export-memory",
                                               *[str(MUSL / "src/linux" / name) for name in
                                                 ("name_to_handle_at.c", "open_by_handle_at.c")],
                                               str(MUSL / "src/internal/syscall_ret.c"),
                                               str(ROOT / "scripts/fixtures/file_handle_calls.c"), "-o", str(binary)],
                                              capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    subprocess.run(["node", "--input-type=module", "-e", """
import {readFileSync} from 'node:fs';
const wide = process.argv[2] === '64';
let calls = 0, instance;
({instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {linux: {
  syscall(n, ...raw) {
    const args = raw.map(Number), api = instance.exports, encode = calls++ % 2 === 0;
    if (Number(n) !== (encode ? 264 : 265) || raw.length !== 6 ||
        args[0] !== (encode ? 37 : 39) || args[encode ? 2 : 1] !== Number(api.handle_address()))
      throw new Error('handle syscall routing or pointer width');
    if (encode) {
      const bytes = new Uint8Array(api.memory.buffer, args[1], 5);
      if (new TextDecoder().decode(bytes) !== 'file\\0' || args[3] !== Number(api.mount_address()) ||
          args[4] !== 4096 || args[5] !== 0) throw new Error('encode arguments');
    } else if (args[2] !== 0x80000 || args.slice(3).some(Boolean)) throw new Error('decode flags');
    const value = calls <= 2 ? (encode ? 0 : 41) : -116;
    return wide ? BigInt(value) : value;
  }
}}));
const api = instance.exports;
if (api.encode() !== 0 || api.decode() !== 41 || api.encode() !== -1 || api.last_error() !== 116 ||
    api.decode() !== -1 || api.last_error() !== 116 || calls !== 4) throw new Error('handle result or errno');
""", str(binary), str(bits)], check=True)


if __name__ == "__main__":
    unittest.main()
