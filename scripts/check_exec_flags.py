#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual exec metadata bitfield/assignment with exact internal flag, not full exec acceptance."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("WASM_EXEC_SOURCE", ROOT / "sources/linux/arch/wasm/kernel/binfmt_wasm.c")).read_text()
if "WASM_BINFMTS_HEADER" in os.environ:
    header = Path(os.environ["WASM_BINFMTS_HEADER"]).read_text()
else:
    header = subprocess.check_output(["git", "-C", str(ROOT / "sources/linux"), "show",
                                      "HEAD:include/linux/binfmts.h"], text=True)
bit = int(re.search(r"#define BINPRM_FLAGS_PRESERVE_ARGV0_BIT (\d+)", header)[1])
assert bit > 0, "review regression control if the internal mask moves to bit zero"
assignment = re.search(r"exec->preserve_argv0\s*=\s*[^;]+;", source)[0]
process = re.search(r"struct wasm_process_args \{[\s\S]*?\n};", source)[0]
metadata = re.search(r"struct wasm_exec_args \{[\s\S]*?\n};", source)[0]
assert re.search(r"unsigned int preserve_argv0\s*:\s*1;", metadata)
prefix = "typedef __SIZE_TYPE__ size_t;\n" + process + "\n" + metadata + f"\n#define BINPRM_FLAGS_PRESERVE_ARGV0 (1U << {bit})\n"
driver = r'''
struct linux_binprm { unsigned int interp_flags; };
unsigned int run(unsigned int flags) {
    struct wasm_exec_args state = {0}, *exec = &state;
    struct linux_binprm input = {.interp_flags=flags}, *bprm = &input;
    ASSIGNMENT
    return exec->preserve_argv0;
}
int check(void) {
    unsigned int flags[]={0,1,BINPRM_FLAGS_PRESERVE_ARGV0,
        BINPRM_FLAGS_PRESERVE_ARGV0|1,BINPRM_FLAGS_PRESERVE_ARGV0<<1,~0U};
    for(unsigned i=0;i<sizeof(flags)/sizeof(flags[0]);i++)
        if(run(flags[i])!=!!(flags[i]&BINPRM_FLAGS_PRESERVE_ARGV0))return 1;
    return 0;
}
int main(void) { return check(); }
'''
with tempfile.TemporaryDirectory(prefix="exec-flag-bitfield-") as tmp:
    path = Path(tmp)
    good = path / "good.c"
    good.write_text(prefix + driver.replace("ASSIGNMENT", assignment))
    old = path / "old.c"
    old.write_text(prefix + driver.replace("ASSIGNMENT", "exec->preserve_argv0 = bprm->interp_flags & BINPRM_FLAGS_PRESERVE_ARGV0;"))
    for cc in ("gcc", "clang"):
        for file, expected in ((good, 0), (old, 1)):
            binary = path / "reference"
            subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", str(file), "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], timeout=10)
            assert result.returncode == expected, (cc, file.name, result.returncode)
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            for file, expected in ((good, 0), (old, 1)):
                module = path / "flags.wasm"
                subprocess.run([cc, f"--target=wasm{bits}", "-O2", "-nostdlib", "-ffreestanding",
                                "-Wl,--no-entry", "-Wl,--export=run", "-Wl,--export=check",
                                str(file), "-o", str(module)], check=True)
                subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';import {readFileSync}from'node:fs';
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]));
assert.equal(instance.exports.check(),Number(process.argv[2]));
const mask=2**Number(process.argv[3]);
assert.equal(instance.exports.run(mask),Number(process.argv[2])?0:1);
assert.equal(instance.exports.run(1),0);
''', str(module), str(expected), str(bit)], check=True)
            subprocess.run([cc, f"--target=wasm{bits}", "--analyze", "-Xanalyzer", "-analyzer-werror",
                            "-o", "/dev/null", str(good)], check=True)
print("actual exec one-bit metadata and internal mask normalization passed; old raw-mask assignment rejected")
