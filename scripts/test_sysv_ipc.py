#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native IPC, wire layouts and exact libc conversion; not a Wasm kernel run."""
import pathlib
import os
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/sysv-ipc.c"


class SysVIPC(unittest.TestCase):
    def test_native_queues_semaphores_and_waiter_removal(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="sysv-native-") as tmp:
                binary = pathlib.Path(tmp) / "test"
                subprocess.run([cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                                str(SOURCE), "-o", str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 3)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)

    def test_both_layouts_exact_control_functions_and_old_layout_control(self):
        with tempfile.TemporaryDirectory(prefix="sysv-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                                       input=templates, text=True, capture_output=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            for bits in (32, 64):
                with self.subTest(bits=bits):
                    includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                                "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"), "-I", str(MUSL / "include")]
                    subprocess.run(["clang", f"--target=wasm{bits}", "-fsyntax-only", "-nostdinc", "-matomics", "-mbulk-memory",
                                    *includes, str(SOURCE)], check=True)
                    analyzed = subprocess.run(["clang", f"--target=wasm{bits}", "--analyze", "-Xanalyzer", "-analyzer-werror",
                                               "-pthread", "-nostdinc", "-matomics", "-mbulk-memory", *includes,
                                               str(SOURCE), "-o", "/dev/null"], capture_output=True, text=True)
                    self.assertEqual(analyzed.returncode, 0, analyzed.stderr)
                    binary = path / "test.wasm"
                    compiled = subprocess.run(["clang", f"--target=wasm{bits}", "-O2", "-nostdlib", "-ffreestanding",
                                    "-Wl,--no-entry", "-Wl,--export=run", "-Wl,--export-memory", *includes,
                                    *[str(MUSL / "src/ipc" / name) for name in ("msgctl.c", "semctl.c", "shmctl.c")],
                                    str(MUSL / "src/string/memcpy.c"), str(MUSL / "src/string/memset.c"),
                                    str(ROOT / "scripts/fixtures/sysv_ipc_abi.c"), "-o", str(binary)], capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    subprocess.run(["node", "--input-type=module", "-e", """
import {readFileSync} from 'node:fs';
const wide = process.argv[2] === '64';
let count = 0, instance;
({instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {linux: {
  syscall(n, ...args) {
    const phase = count++, sem = phase === 1;
    if (Number(n) !== [187, 191, 195][phase] || Number(args[0]) !== 40 + phase ||
        Number(args[sem ? 2 : 1]) !== 258 || (sem && Number(args[1]) !== 0)) throw new Error('IPC command ABI');
    const pointer = Number(args[sem ? 3 : 2]), view = new DataView(instance.exports.memory.buffer);
    const u32 = (off, value) => view.setUint32(pointer + off, value, true);
    const word = (off, value) => wide ? view.setBigUint64(pointer + off, BigInt(value), true) : u32(off, value);
    const time = (off, value) => view.setBigUint64(pointer + off, value, true);
    new Uint8Array(instance.exports.memory.buffer, pointer, wide ? [120,88,112][phase] : [88,64,84][phase]).fill(0);
    if (phase === 0) {
      time(wide ? 48 : 36, 0x189abcdefn); time(wide ? 56 : 44, 0x200000009n); time(wide ? 64 : 52, 0x30000000an);
      word(wide ? 72 : 60, 7); word(wide ? 80 : 64, 1); word(wide ? 88 : 68, 8192);
      u32(wide ? 96 : 72, 43); u32(wide ? 100 : 76, 44);
    } else if (phase === 1) {
      time(wide ? 48 : 36, 0x400000011n); time(wide ? 56 : 44, 0x500000012n); word(wide ? 64 : 52, 2);
    } else {
      word(wide ? 48 : 36, 65536); time(wide ? 56 : 40, 0x600000015n);
      time(wide ? 64 : 48, 0x700000016n); time(wide ? 72 : 56, 0x800000017n);
      u32(wide ? 80 : 64, 45); u32(wide ? 84 : 68, 46); word(wide ? 88 : 72, 3);
    }
    return wide ? 0n : 0;
  }
}}));
const result = instance.exports.run();
if (result !== 0 || count !== 3) throw new Error(`IPC metadata conversion case ${result}`);
""", str(binary), str(bits)], check=True)
            old = path / "old/bits"
            old.mkdir(parents=True)
            for name in ("ipcstat.h", "msg.h", "sem.h", "shm.h"):
                (old / name).write_bytes((MUSL / "arch/generic/bits" / name).read_bytes())
            negative = subprocess.run(["clang", "--target=wasm32", "-fsyntax-only", "-nostdinc", "-I", str(old.parent),
                                       *includes, str(ROOT / "scripts/fixtures/sysv_ipc_abi.c")], capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn("kernel wire offset", negative.stderr)

    def test_actual_pinned_kernel_uapi_layout(self):
        headers = pathlib.Path(os.environ.get("WASM_IPC_UAPI_DIR", ROOT / "sources/linux/include/uapi/asm-generic"))
        self.assertTrue((headers / "ipcbuf.h").is_file(), "provide pinned UAPI with WASM_IPC_UAPI_DIR")
        with tempfile.TemporaryDirectory(prefix="sysv-kernel-wire-") as tmp:
            path = pathlib.Path(tmp)
            for name in ("asm", "linux", "bits"):
                (path / name).mkdir()
            for name in ("ipcbuf.h", "msgbuf.h", "sembuf.h", "shmbuf.h"):
                (path / "asm" / name).write_bytes((headers / name).read_bytes())
            (path / "asm/bitsperlong.h").write_text("#define __BITS_PER_LONG (__SIZEOF_LONG__ * 8)\n")
            (path / "asm/posix_types.h").write_text('#include <linux/posix_types.h>\n')
            (path / "linux/posix_types.h").write_text("""
#ifndef IPC_TEST_KERNEL_TYPES
#define IPC_TEST_KERNEL_TYPES
typedef int __kernel_key_t, __kernel_pid_t;
typedef unsigned int __kernel_uid32_t, __kernel_gid32_t, __kernel_mode_t;
typedef unsigned long __kernel_ulong_t, __kernel_size_t;
#endif
""")
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            result = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                    text=True, capture_output=True, check=True)
            (path / "bits/alltypes.h").write_text(result.stdout)
            for bits in (32, 64):
                checked = subprocess.run(["clang", f"--target=wasm{bits}", "-fsyntax-only", "-nostdinc", "-DIPC_KERNEL_UAPI_TEST",
                                          "-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                                          "-I", str(MUSL / "include"), str(ROOT / "scripts/fixtures/sysv_ipc_abi.c")],
                                         capture_output=True, text=True)
                self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
