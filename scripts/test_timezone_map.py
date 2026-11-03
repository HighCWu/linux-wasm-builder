#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute actual Wasm helper bodies with bounded faults; not libc/Linux acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("WASM_TIMEZONE_MAP_SOURCE", root / "sources/musl/src/time/__map_file.c")).read_text()
start = source.index("const char unsigned *__map_file", source.index("#ifdef __wasm__\nconst"))
body = source[start:source.index("#else", start)]
model = (root / "scripts/fixtures/timezone_map_model.c").read_text()
variants = {
    "normal": body,
    "skip-close": body.replace("__syscall(SYS_close, fd);", "(void)fd;"),
    "cancellable-close": body.replace("__syscall(SYS_close, fd)", "close(fd)"),
    "shared-map": body.replace("PROT_READ, MAP_PRIVATE", "PROT_READ, MAP_SHARED"),
}
assert all(changed != body for name, changed in variants.items() if name != "normal")
with tempfile.TemporaryDirectory(prefix="wasm-timezone-map-") as tmp:
    path = Path(tmp)
    musl = root / "sources/musl"
    headers = path / "headers"
    (headers / "bits").mkdir(parents=True)
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                               text=True, capture_output=True, check=True)
    (headers / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
    (headers / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    for bits in (32, 64):
        compiler = os.environ.get("CC", "clang")
        actual = [compiler, f"--target=wasm{bits}", "-std=c99", "-ffreestanding", "-nostdinc", "-D_XOPEN_SOURCE=700"]
        for include in (musl / "arch/wasm32", musl / "arch/generic", musl / "src/include",
                        musl / "src/internal", headers, musl / "include"):
            actual.extend(["-I", str(include)])
        filename = os.environ.get("WASM_TIMEZONE_MAP_SOURCE", str(musl / "src/time/__map_file.c"))
        subprocess.run([*actual, "-fsyntax-only", filename], check=True)
        subprocess.run([*actual, "--analyze", "-Xanalyzer", "-analyzer-werror", filename, "-o", "/dev/null"], check=True)
        consumer = str(root / "sources/distro/distro/timezone/runtime.c")
        subprocess.run([*actual, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", consumer], check=True)
        subprocess.run([*actual, "--analyze", "-Xanalyzer", "-analyzer-werror", consumer, "-o", "/dev/null"], check=True)
        # Link the actual helper in a separate object: hidden libc references
        # must really reach the observation wrappers before their real target.
        runtime = Path(consumer).read_text()
        wrappers = runtime[runtime.index("#ifdef __wasm__\n/* Test-only link observation"):]
        wrappers = wrappers[:wrappers.index("#endif") + len("#endif")]
        probe = r'''
#include <sys/mman.h>
#include <sys/stat.h>
#include <stdint.h>
static int saved_errno;
int *__errno_location(void) { return &saved_errno; }
int *___errno_location(void) { return &saved_errno; }
long __syscall_ret(unsigned long r) { if(r>(unsigned long)-4096){saved_errno=-(long)r;return -1;}return r; }
int __fstat(int fd, struct stat *st) { if(fd!=17)__builtin_trap();st->st_size=12;return 0; }
static char contents[12];
void *__mmap(void *p,size_t n,int prot,int flags,int fd,off_t off) {
 if(p||n!=12||prot!=PROT_READ||flags!=MAP_PRIVATE||fd!=17||off)__builtin_trap();
 return contents;
}
int __munmap(void *p,size_t n) { if(p!=contents||n!=12)__builtin_trap();return 0; }
''' + wrappers + r'''
const unsigned char *__map_file(const char *,size_t *);
void __unmap_file(const char *,size_t);
__attribute__((export_name("check"))) int check(void) {
 size_t n=0;const unsigned char *p=__map_file("zone",&n);
 if(p!=(void*)contents||n!=12)return 1;
 __unmap_file((const char*)p,n);
 return private_maps==1&&unmaps==1?0:2;
}
'''
        (path / "link-probe.c").write_text(probe)
        for wrapped in (True, False):
            binary = path / "link-probe.wasm"
            subprocess.run([*actual, "-O2", "-nostdlib", filename, str(path / "link-probe.c"),
                "-Wl,--no-entry", *(["-Wl,--wrap=__mmap,--wrap=__munmap"] if wrapped else ["-Wl,--allow-undefined"]),
                "-o", str(binary)], check=True)
            subprocess.run(["node", "--input-type=module", "-e", """
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
let opened=0,closed=0;
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]),{linux:{syscall(n){
 if(Number(n)===56){opened++;return typeof n==='bigint'?17n:17;}
 assert.equal(Number(n),57);closed++;return typeof n==='bigint'?0n:0;
}}});
assert.equal(instance.exports.check(),Number(process.argv[2]));assert.equal(opened,1);assert.equal(closed,1);
""", str(binary), "0" if wrapped else "2"], check=True)
        for name, changed in variants.items():
            unit, binary = path / "model.c", path / "model.wasm"
            unit.write_text(model.replace("/* ACTUAL_WASM_TIMEZONE_MAP */", changed))
            command = [compiler, f"--target=wasm{bits}", "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-ffreestanding", "-fno-builtin", "-Wno-unused-parameter"]
            subprocess.run([*command, "-O2", "-nostdlib", "-Wl,--no-entry", "-Wl,--export=check", str(unit), "-o", str(binary)], check=True)
            if name == "normal":
                subprocess.run([*command, "--analyze", "-Xanalyzer", "-analyzer-werror", str(unit), "-o", "/dev/null"], check=True)
            subprocess.run(["node", "--input-type=module", "-e", """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]));
const results=Array.from({length:9},(_,i)=>instance.exports.check(i));
if(process.argv[2]==='normal') assert.deepEqual(results,Array(9).fill(0));
else assert.equal(results[0],{'skip-close':20,'cancellable-close':21,'shared-map':10}[process.argv[2]],
 'negative control must fail at the intended fd/cancellation/mapping boundary');
""", str(binary), name], check=True)
        print(f"wasm{bits}: actual private timezone mmap, hidden-symbol link wrapping/missing-wrap control, EINTR retry, size/error refusal, munmap and fd/cancellation/shared-map controls passed")
    for compiler in ("gcc", "clang"):
        binary = path / "native-timezone"
        subprocess.run([compiler, "-O2", "-Wall", "-Wextra", "-Werror", str(root / "sources/distro/distro/timezone/runtime.c"), "-o", str(binary)], check=True)
        subprocess.run([str(binary), "/usr/share/zoneinfo/America/New_York", "/usr/share/zoneinfo/Asia/Tokyo"], check=True)
