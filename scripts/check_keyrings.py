#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Workload frontends/static analysis and actual musl raw-syscall word ABI, not keyring execution."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCES = ROOT / "sources/distro/distro/keyrings"
if "WASM_KEYCTL_HEADER" in os.environ:
    header = Path(os.environ["WASM_KEYCTL_HEADER"]).read_text()
else:
    header = subprocess.check_output(["git", "-C", str(ROOT / "sources/linux"), "show",
                                      "HEAD:include/uapi/linux/keyctl.h"], text=True)
# Only numeric constants are needed by this workload. This does not validate
# the exported structs or headers_install; the real target uses installed UAPI.
constants = "\n".join(line for line in header.splitlines()
                      if re.match(r"#define\s+(?:KEY_SPEC_|KEYCTL_)\w*\s+-?(?:0x[0-9a-fA-F]+|[0-9]+)\b", line))
assert "KEYCTL_READ" in constants and "KEY_SPEC_SESSION_KEYRING" in constants
with tempfile.TemporaryDirectory(prefix="keyring-abi-") as tmp:
    path = Path(tmp)
    for cc in ("gcc", "clang"):
        for filename in ("runtime.c", "helper.c"):
            subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCES / filename),
                            "-o", str(path / filename.removesuffix(".c"))], check=True)
    (path / "bits").mkdir()
    (path / "linux").mkdir()
    (path / "linux/keyctl.h").write_text(constants + "\n")
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (path / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    unistd = (MUSL / "include/unistd.h").read_text()
    gate = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
    assert gate in unistd
    (path / "unistd.h").write_text(unistd.replace(gate, "pid_t fork(void);\npid_t _Fork(void);"))
    driver = path / "driver.c"
    driver.write_text(r'''
#define _GNU_SOURCE
#include "cases.h"
long __syscall_ret(unsigned long value) { return (long)value; }
long run(void) {
    if(kc(KEYCTL_GET_KEYRING_ID,KEY_SPEC_SESSION_KEYRING,0,0,0))return 1;
    if(read_key(17,(void *)0x12345678,7))return 2;
    if(syscall(SYS_request_key,(long)"user",(long)"wasm-binary",0L,0L,0L,0L))return 3;
    return syscall(SYS_add_key,(long)"user",(long)"wasm-new",0x12345678L,7L,-3L,0L);
}
''')
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-nostdinc", "-I", tmp, "-I", str(SOURCES),
                     "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                     "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"),
                     "-I", str(MUSL / "include"), "-isystem", resource + "/include"]
            for filename in ("runtime.c", "helper.c"):
                source = str(SOURCES / filename)
                subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", source], check=True)
                subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null", source], check=True)
            module = path / "abi.wasm"
            subprocess.run([*flags, "-O2", "-nostdlib", "-ffreestanding", "-Wl,--no-entry", "-Wl,--export=run",
                            str(MUSL / "src/misc/syscall.c"), str(driver), "-o", str(module)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const wide=process.argv[2]==='64';let count=0;
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]),{linux:{syscall(...args){
 const word=v=>BigInt.asUintN(wide?64:32,BigInt(v));const actual=args.map(word);
 if(count===0)assert.deepEqual(actual,[219n,0n,-3n,0n,0n,0n,0n].map(word));
 else if(count===1)assert.deepEqual(actual,[219n,11n,17n,0x12345678n,7n,0n,0n].map(word));
 else {assert.ok(count===2||count===3);
  assert.equal(actual[0],count===2?218n:217n);
  assert.deepEqual(actual.slice(3),(count===2?[0n,0n,0n,0n]:[0x12345678n,7n,-3n,0n]).map(word));
  const mem=new Uint8Array(instance.exports.memory.buffer);const dec=new TextDecoder();
  for(const [index,text]of [[1,'user'],[2,count===2?'wasm-binary':'wasm-new']]){
   const start=Number(actual[index]);assert.equal(dec.decode(mem.subarray(start,mem.indexOf(0,start))),text);
  }}count++;return wide?0n:0;
}}});
assert.equal(instance.exports.run(),wide?0n:0);assert.equal(count,4);
''', str(module), str(bits)], check=True)
print("keyring workload compilation/analysis and real musl raw-syscall Wasm word ABI passed; no host key mutation")
