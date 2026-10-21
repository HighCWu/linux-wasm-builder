#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the exact kernel argument wrapper in tiny Wasm modules, not a kernel build."""
import os
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = pathlib.Path(os.environ.get("WASM_SYSCALL_WRAPPER_SOURCE",
                  ROOT / "sources/linux/arch/wasm/include/asm/syscall_wrapper.h")).read_text()
context = pathlib.Path(os.environ.get("WASM_SIGCONTEXT_SOURCE",
                   ROOT / "sources/linux/arch/wasm/include/uapi/asm/sigcontext.h")).read_text()
with tempfile.TemporaryDirectory(prefix="syscall-words-") as tmp:
    path = pathlib.Path(tmp)
    (path / "asm").mkdir()
    (path / "linux").mkdir()
    # Like kernel/sys_ni.c, a caller may only have a forward declaration here.
    (path / "asm/ptrace.h").write_text("struct pt_regs;\n")
    (path / "asm/sigcontext.h").write_text(context)
    (path / "linux/errno.h").write_text("#define ENOSYS 38\n")
    (path / "wrapper.h").write_text(source)
    for bits, negative in ((32, False), (64, False), (32, True)):
        binary = path / "test.wasm"
        subprocess.run(["clang", f"--target=wasm{bits}", "-std=gnu2x", "-O2", "-nostdlib", "-Wall", "-Wextra", "-Werror",
                        "-Wl,--no-entry", "-Wl,--export=run", "-I", tmp,
                        *(["-DCONFIG_64BIT=1"] if bits == 64 else []),
                        *(["-DWASM_WORD_NEGATIVE=1"] if negative else []),
                        str(ROOT / "scripts/fixtures/syscall_words.c"), "-o", str(binary)], check=True)
        subprocess.run(["node", "--input-type=module", "-e", """
import {readFileSync} from 'node:fs';
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]));
const result = instance.exports.run();
const expected = Number(process.argv[2]);
if (result !== expected) throw new Error(`syscall word decoding case ${result}, expected ${expected}`);
console.log('exact syscall word decoding pass');
""", str(binary), "1" if negative else "0"], check=True)
        print(f"wasm{bits}: {'old-layout rejection' if negative else 'exact wrapper argument reconstruction'} pass", flush=True)
