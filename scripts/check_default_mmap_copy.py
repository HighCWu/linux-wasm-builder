#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real private musl archive extraction/ABI; allocator is a stand-in, not VFS proof."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
flag = "--export=__wasm_mmap_init_v1"
assert '"' + flag + '"' in (ROOT / "sources/distro/distro/platform.nix").read_text()
checker = ROOT / "sources/distro/distro/sdk/check-mmap-capability.mjs"
compiler = "clang"
resource = subprocess.check_output([compiler, "-print-resource-dir"], text=True).strip()
major = Path(resource).name.split(".")[0]
ar = shutil.which("llvm-ar-" + major) or shutil.which("llvm-ar")
assert ar, "matching LLVM archiver required for Wasm archive extraction"
with tempfile.TemporaryDirectory(prefix="default-mmap-copy-") as tmp:
    work = Path(tmp)
    (work / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.check_output(
        ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates, text=True
    )
    (work / "bits/alltypes.h").write_text(generated)
    # Only the allocator is replaced; the optional archive member is real musl.
    stub = work / "allocator.c"
    stub.write_text("""#include <stddef.h>
long __wasm_mmap_initialized(size_t rounded, int (*fn)(void *, size_t, void *), void *argument)
{
    return fn((void *)65536, rounded, argument) ? -5 : 65536;
}
""")
    profile = work / "profile.json"
    capability = {
        "version": 1,
        "exportName": "__wasm_mmap_init_v1",
        "importModule": "linux_mmap_init_v1",
        "importName": "copy",
        "requiresKernelExport": "abort_file_mmap_v1",
        "admission": "kernel",
    }
    profile.write_text(
        json.dumps(
            {"execution": {"initializedPrivateCopy": capability}, "linkerFlags": [flag]}
        )
    )
    for bits in (32, 64):
        common = [
            compiler,
            f"--target=wasm{bits}",
            "-O2",
            "-nostdinc",
            "-I",
            tmp,
            "-I",
            str(MUSL / "arch/wasm32"),
            "-I",
            str(MUSL / "arch/generic"),
            "-I",
            str(MUSL / "include"),
            "-isystem",
            resource + "/include",
            "-Wall",
            "-Wextra",
            "-Werror",
        ]
        member, allocator = work / "member.o", work / "allocator.o"
        subprocess.run(
            [
                *common,
                "-c",
                str(MUSL / "src/mman/wasm32/mmap_init.c"),
                "-o",
                str(member),
            ],
            check=True,
        )
        subprocess.run([*common, "-c", str(stub), "-o", str(allocator)], check=True)
        archive = work / f"libcopy{bits}.a"
        subprocess.run([ar, "rcs", str(archive), str(member)], check=True)
        for mode in ("present", "absent"):
            binary = work / f"copy-{bits}-{mode}.wasm"
            subprocess.run(
                [
                    compiler,
                    f"--target=wasm{bits}",
                    "-nostdlib",
                    "-Wl,--no-entry",
                    *(["-Wl," + flag] if mode == "present" else []),
                    str(allocator),
                    str(archive),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "node",
                    str(checker),
                    str(binary),
                    mode,
                    *([str(profile)] if mode == "present" else []),
                ],
                check=True,
            )
            refused = subprocess.run(
                [
                    "node",
                    str(checker),
                    str(binary),
                    "absent" if mode == "present" else "present",
                ],
                capture_output=True,
                text=True,
            )
            assert refused.returncode != 0, "reversing capability expectation must fail"
            if mode == "present":
                subprocess.run(
                    [
                        "node",
                        "--input-type=module",
                        "-e",
                        """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const wide=process.argv[2]==='64', word=n=>wide?BigInt(n):n;
let copies=0;
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]), {
  linux_mmap_init_v1: { copy(to,length) {
    assert.equal(to,word(65536)); assert.equal(typeof length,wide?'bigint':'number');
    assert.equal(length,word(copies===0?0:3)); copies++; return 0;
  }}
});
const map=instance.exports.__wasm_mmap_init_v1;
assert.equal(map(word(65536),word(0)),word(65536));
assert.equal(map(word(65536),word(3)),word(65536));
assert.equal(map(word(65536),word(65537)),word(-22));
assert.equal(copies,2);
""",
                        str(binary),
                        str(bits),
                    ],
                    check=True,
                )
        print(
            f"wasm{bits}: real optional archive member, old absence and private copy scalar ABI passed"
        )
        # An export name alone is not the installed copy contract.
        fake = work / "fake.c"
        fake.write_text("long __wasm_mmap_init_v1(void) { return 0; }\n")
        forged = work / f"forged-{bits}.wasm"
        subprocess.run(
            [
                compiler,
                f"--target=wasm{bits}",
                "-nostdlib",
                "-Wl,--no-entry",
                "-Wl," + flag,
                str(fake),
                "-o",
                str(forged),
            ],
            check=True,
        )
        rejected = subprocess.run(
            ["node", str(checker), str(forged), "present"],
            capture_output=True,
            text=True,
        )
        assert rejected.returncode != 0 and "linux_mmap_init_v1" in rejected.stderr
