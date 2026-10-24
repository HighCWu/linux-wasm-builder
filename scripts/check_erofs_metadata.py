#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native xattr semantics and Wasm frontend checks, not an EROFS kernel boot."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/erofs-metadata/runtime.c"
SHIM = r'''
#include <errno.h>
#include <stddef.h>
#include <sys/types.h>
ssize_t __wrap_getxattr(const char *p,const char *n,void *v,size_t s) {
    (void)p; (void)n; (void)v; (void)s;
    errno=EOPNOTSUPP;
    return -1;
}
'''
with tempfile.TemporaryDirectory(prefix="erofs-metadata-") as tmp:
    path = Path(tmp)
    data = path / "file"
    data.write_bytes(b"contents\n")
    (path / "link").symlink_to("file")
    os.setxattr(data, "user.binary", bytes([0, 1, 2, 0, 255, 127, 128]))
    os.setxattr(data, "user.empty", b"")
    os.setxattr(path, "user.directory", b"dir")
    shim, binary = path / "unsupported.c", path / "reference"
    shim.write_text(SHIM)
    for cc in ("gcc", "clang"):
        for unsupported in (False, True):
            extra = [str(shim), "-Wl,--wrap=getxattr"] if unsupported else []
            subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCE),
                            *extra, "-o", str(binary)], check=True)
            result = subprocess.run([str(binary), tmp], capture_output=True, text=True, timeout=10)
            if unsupported:
                assert result.returncode != 0 and "::vm-test::pass" not in result.stdout, result.stdout
                assert "binary attribute size" in result.stdout, result.stdout
            else:
                assert result.returncode == 0, result.stdout + result.stderr
                assert result.stdout.count("::vm-test::pass") == 1, result.stdout
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
    generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                               capture_output=True, text=True, check=True)
    (path / "bits/alltypes.h").write_text(generated.stdout)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-nostdinc", "-I", tmp,
                     "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                     "-I", str(MUSL / "include"), "-isystem", resource + "/include"]
            subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
            subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null", str(SOURCE)], check=True)
print("EROFS attribute native reference, unsupported control and Wasm frontend/analysis passed")
