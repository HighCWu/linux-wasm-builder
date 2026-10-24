#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Public syscall call-site packing against unchanged variadic implementation."""

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
DRIVER = r"""
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <unistd.h>
#ifdef __cplusplus
extern "C" {
#endif
long __syscall_ret(unsigned long value) { return (long)value; }
long run(void) {
    if(syscall(436,41,43,0,0,0,0))return 1;
    if(syscall(500))return 2;
    if(syscall(501,-1))return 3;
    if(syscall(502,1,2))return 4;
    if(syscall(503,1,2,3))return 5;
    if(syscall(504,1,2,3,4))return 6;
    if(syscall(505,1,2,3,4,5))return 7;
    if(syscall(506,1,2,3,4,5,6))return 8;
    int once=1;
    if(syscall(507,(void *)0x12345678,-100,0x89abcdefU,++once,0,0))return 9;
    long (*raw)(long,...)=&syscall;
    if(raw(508,1L,2L,3L,4L,5L,6L))return 10;
    if(syscall(512,syscall(511,1,2,3),0,0,0,0,0))return 14;
#ifdef __cplusplus
    if(::syscall(509,1,2,3,4,5,6))return 11;
    if(::syscall(510,nullptr,0,0,0,0,0))return 12;
#endif
    return once==2?0:13;
}
#ifdef __cplusplus
}
#endif
"""
with tempfile.TemporaryDirectory(prefix="public-syscall-words-") as tmp:
    path = Path(tmp)
    workload = ROOT / "sources/distro/distro/public-syscall/runtime.c"
    for cc in ("gcc", "clang"):
        binary = path / "runtime"
        subprocess.run(
            [
                cc,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(workload),
                "-o",
                str(binary),
            ],
            check=True,
        )
        result = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for marker in (
            "direct calls, existing function symbol and errno pass",
            "mixed int close_range positions, errors and fd preservation pass",
            "pointer/int buffer call and bounded output pass",
        ):
            assert marker in result.stdout
        assert result.stdout.count("::vm-test::pass") == 1
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.run(
        ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
        input=templates,
        capture_output=True,
        text=True,
        check=True,
    )
    (path / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    driver, module = path / "driver.c", path / "abi.wasm"
    driver.write_text(DRIVER)
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output(
            [cc, "-print-resource-dir"], text=True
        ).strip()
        for bits in (32, 64):
            flags = [
                cc,
                f"--target=wasm{bits}",
                "-nostdinc",
                "-I",
                tmp,
                "-I",
                str(MUSL / "arch/wasm32"),
                "-I",
                str(MUSL / "arch/generic"),
                "-I",
                str(MUSL / "src/include"),
                "-I",
                str(MUSL / "src/internal"),
                "-I",
                str(MUSL / "include"),
                "-isystem",
                resource + "/include",
            ]
            implementation, consumer = path / "implementation.o", path / "consumer.o"
            subprocess.run(
                [*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(workload)],
                check=True,
            )
            subprocess.run(
                [
                    *flags,
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    "-o",
                    "/dev/null",
                    str(workload),
                ],
                check=True,
            )
            subprocess.run(
                [
                    *flags,
                    "-O2",
                    "-ffreestanding",
                    "-c",
                    str(MUSL / "src/misc/syscall.c"),
                    "-o",
                    str(implementation),
                ],
                check=True,
            )
            for language in ("c", "c++"):
                for negative in (False, True) if bits == 64 else (False,):
                    old_header = path / "unistd.h"
                    if negative:
                        original = (MUSL / "include/unistd.h").read_text()
                        old = re.sub(
                            r"#if defined\(__wasm__\) && __SIZEOF_LONG__ == 8\n[\s\S]*?\n#endif\n",
                            "",
                            original,
                        )
                        assert old != original
                        old_header.write_text(old)
                    subprocess.run(
                        [
                            *flags,
                            "-x",
                            language,
                            "-O2",
                            "-Wall",
                            "-Wextra",
                            "-Werror",
                            "-ffreestanding",
                            "-c",
                            str(driver),
                            "-o",
                            str(consumer),
                        ],
                        check=True,
                    )
                    subprocess.run(
                        [
                            cc,
                            f"--target=wasm{bits}",
                            "-nostdlib",
                            "-Wl,--no-entry",
                            "-Wl,--export=run",
                            str(implementation),
                            str(consumer),
                            "-o",
                            str(module),
                        ],
                        check=True,
                    )
                    result = subprocess.run(
                        [
                            "node",
                            "--input-type=module",
                            "-e",
                            r"""
import assert from 'node:assert/strict';import {readFileSync}from'node:fs';
const wide=process.argv[2]==='64';let called=0;
const rows=[[436n,41n,43n,0n,0n,0n,0n],...Array.from({length:7},(_,n)=>
 [BigInt(500+n),...Array.from({length:n},(_,i)=>n===1?-1n:BigInt(i+1))]),
 [507n,0x12345678n,-100n,0x89abcdefn,2n,0n,0n],[508n,1n,2n,3n,4n,5n,6n],
 [511n,1n,2n,3n],[512n,0n,0n,0n,0n,0n,0n]];
if(process.argv[3]==='c++')rows.push([509n,1n,2n,3n,4n,5n,6n],[510n,0n,0n,0n,0n,0n,0n]);
const word=v=>BigInt.asUintN(wide?64:32,BigInt(v));
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]),{linux:{syscall(...args){
 const expected=[...rows[called++]];
 if(wide)while(expected.length<7)expected.push(0n);
 assert.deepEqual(args.slice(0,expected.length).map(word),expected.map(word),'public syscall word order');
 return wide?0n:0;
}}});
assert.equal(instance.exports.run(),wide?0n:0);assert.equal(called,rows.length);
""",
                            str(module),
                            str(bits),
                            language,
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if negative:
                        bad_words = "public syscall word order" in result.stderr
                        bad_fetch = re.search(
                            r"RuntimeError: memory access out of bounds[\s\S]*at abi\.wasm\.syscall",
                            result.stderr,
                        )
                        assert result.returncode != 0 and (bad_words or bad_fetch), (
                            cc,
                            bits,
                            language,
                            result.returncode,
                            result.stderr[:1000],
                        )
                        old_header.unlink()
                    else:
                        assert result.returncode == 0, result.stdout + result.stderr
print("public syscall integer arguments preserve Linux machine-word positions")
