#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native event framing and exact existing musl ABI, not privileged event delivery."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/fanotify/runtime.c"
DRIVER = r'''
#include <stdint.h>
#include <sys/fanotify.h>
long __syscall_ret(unsigned long value) { return (long)value; }
int run(void) {
    if(fanotify_init(3,0x80000))return 1;
    return fanotify_mark(11,1,0x123456789abcdef0ULL,-100,(const char *)(uintptr_t)0x12345678);
}
'''
with tempfile.TemporaryDirectory(prefix="fanotify-abi-") as tmp:
    path = Path(tmp)
    binary = path / "reference"
    for cc in ("gcc", "clang"):
        subprocess.run([cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror", str(SOURCE),
                        "-o", str(binary)], check=True)
        result = subprocess.run([str(binary), "--protocol"], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and "native event framing reference pass" in result.stdout, result.stdout + result.stderr
        assert "::vm-test::pass" not in result.stdout, "native framing must not claim kernel delivery"
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (path / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    driver, module = path / "driver.c", path / "abi.wasm"
    driver.write_text(DRIVER)
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-nostdinc", "-I", tmp,
                     "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                     "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"),
                     "-I", str(MUSL / "include"), "-isystem", resource + "/include"]
            subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
            subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null", str(SOURCE)], check=True)
            subprocess.run([*flags, "-O2", "-nostdlib", "-ffreestanding", "-Wl,--no-entry", "-Wl,--export=run",
                            str(MUSL / "src/linux/fanotify.c"), str(driver), "-o", str(module)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const wide=process.argv[2]==='64';
const expected=[ [262n,3n,0x80000n,0n,0n,0n,0n], wide ?
  [263n,11n,1n,0x123456789abcdef0n,-100n,0x12345678n,0n] :
  [263n,11n,1n,0x9abcdef0n,0x12345678n,-100n,0x12345678n] ];
let count=0;
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]),{linux:{syscall(...args){
  assert.ok(count<expected.length);
  const word=v=>BigInt.asUintN(wide?64:32,BigInt(v));
  assert.deepEqual(args.map(word),expected[count++].map(word));
  return wide?0n:0;
}}});
assert.equal(instance.exports.run(),0); assert.equal(count,2);
''', str(module), str(bits)], check=True)
print("fanotify native framing, real musl mask-word ABI and Wasm frontend/analysis passed")
