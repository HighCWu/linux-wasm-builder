#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check real export/pre-boot guards without building or linking a kernel."""

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def read_source(env, path):
    if env in os.environ:
        return Path(os.environ[env]).read_text()
    local = ROOT / "sources/linux" / path
    return (
        local.read_text()
        if local.exists()
        else subprocess.check_output(
            ["git", "-C", str(ROOT / "sources/linux"), "show", "HEAD:" + path],
            text=True,
        )
    )


exports = read_source("WASM_EXPORT_HEADER", "include/linux/export.h")
arch = read_source("WASM_ARCH_MAKEFILE", "arch/wasm/Makefile")
sha = read_source("WASM_SHA256_LIBRARY", "lib/crypto/sha256.c")
assert "-D__DISABLE_EXPORTS" not in arch, (
    "whole kernel must not request a pre-boot crypto subset"
)
sha = "\n".join(line for line in sha.splitlines() if not line.startswith("#include"))
symbols = (
    "__hmac_sha256_init",
    "hmac_sha224_final",
    "hmac_sha256_final",
    "hmac_sha224",
    "hmac_sha256",
    "hmac_sha224_preparekey",
    "hmac_sha256_preparekey",
)

with tempfile.TemporaryDirectory(prefix="wasm-exports-") as tmp:
    directory = Path(tmp)
    (directory / "linux").mkdir()
    (directory / "linux/compiler.h").write_text("#define __ADDRESSABLE(x)\n")
    (directory / "linux/linkage.h").write_text("#define ASM_NL ;\n")
    (directory / "linux/stringify.h").write_text(
        "#define __stringify_1(x...) #x\n#define __stringify(x...) __stringify_1(x)\n"
    )
    header = directory / "export.h"
    header.write_text(exports)
    path = directory / "sha256.c"
    path.write_text(sha)
    for cc in ("gcc", "clang"):
        for case, flags, full, records in (
            ("wasm32", ["-DCONFIG_WASM=1"], True, False),
            ("wasm64", ["-DCONFIG_WASM=1", "-DCONFIG_64BIT=1"], True, False),
            ("native", ["-DCONFIG_64BIT=1"], True, True),
            ("pre-boot", ["-D__DISABLE_EXPORTS"], False, False),
            (
                "old-wasm-negative",
                ["-DCONFIG_WASM=1", "-D__DISABLE_EXPORTS"],
                False,
                False,
            ),
        ):
            out = subprocess.check_output(
                [cc, "-E", "-P", "-I", tmp, "-include", str(header), *flags, str(path)],
                text=True,
            )
            for symbol in symbols:
                found = re.search(r"\bvoid\s+" + symbol + r"\s*\(", out) is not None
                assert found == full, (cc, case, symbol)
            assert (".export_symbol" in out) == records, (cc, case, "export records")
    # Compile the real header against both Wasm targets: no unsupported ELF
    # export assembler is emitted. This is not a full crypto/kernel link test.
    path.write_text("int marker;\nEXPORT_SYMBOL(marker);\n")
    for bits in (32, 64):
        subprocess.run(
            [
                "clang",
                f"--target=wasm{bits}",
                "-DCONFIG_WASM=1",
                "-I",
                tmp,
                "-include",
                str(header),
                "-c",
                str(path),
                "-o",
                str(directory / f"marker{bits}.o"),
            ],
            check=True,
        )

print(
    "Export policy: real SHA HMAC bodies visible, Wasm export records suppressed, native/pre-boot guards unchanged; full target link still requires CI"
)
