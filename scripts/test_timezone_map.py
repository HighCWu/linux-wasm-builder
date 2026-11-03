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
        print(f"wasm{bits}: actual private timezone mmap, EINTR retry, size/error refusal, munmap, fd/cancellation/shared-map controls passed")
    for compiler in ("gcc", "clang"):
        binary = path / "native-timezone"
        subprocess.run([compiler, "-O2", "-Wall", "-Wextra", "-Werror", str(root / "sources/distro/distro/timezone/runtime.c"), "-o", str(binary)], check=True)
        subprocess.run([str(binary), "/usr/share/zoneinfo/America/New_York", "/usr/share/zoneinfo/Asia/Tokyo"], check=True)
