#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated helper protocol/native shims and Wasm analysis, not setuid acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCES = ROOT / "sources/distro/distro/exec-security"
SHIM = r'''
#define _GNU_SOURCE
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <unistd.h>
static const char *mode(void) { return getenv("EXEC_SECURITY_CASE"); }
uid_t __wrap_getuid(void) { return !strcmp(mode(),"plain")?0:1000; }
uid_t __wrap_geteuid(void) { return !strcmp(mode(),"suid")?0:__wrap_getuid(); }
unsigned long __wrap_getauxval(unsigned long key) {
    int secure=!strcmp(mode(),"suid"), plain=!strcmp(mode(),"plain");
    switch(key) {
    case AT_SECURE:return secure ^ !!getenv("WRONG_SECURE");
    case AT_UID:return __wrap_getuid();
    case AT_EUID:return __wrap_geteuid();
    case AT_GID:case AT_EGID:return plain?0:1000;
    case AT_EXECFN:return (unsigned long)(secure||!strcmp(mode(),"nnp")?"/secure-helper":"/plain-helper");
    default:_Exit(99);
    }
}
char *__wrap_secure_getenv(const char *name) { return !strcmp(mode(),"suid")?NULL:getenv(name); }
'''
with tempfile.TemporaryDirectory(prefix="exec-security-") as tmp:
    path = Path(tmp)
    shim, binary = path / "protocol.c", path / "helper"
    shim.write_text(SHIM)
    for cc in ("gcc", "clang"):
        subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCES / "runtime.c"),
                        "-o", str(path / "controller")], check=True)
        subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCES / "helper.c"), str(shim),
                        "-Wl,--wrap=getuid", "-Wl,--wrap=geteuid", "-Wl,--wrap=getauxval",
                        "-Wl,--wrap=secure_getenv", "-o", str(binary)], check=True)
        for mode in ("plain", "suid", "nnp", "recovery"):
            for wrong in (False, True):
                env = {**os.environ, "EXEC_SECURITY_CASE": mode, "EXEC_SECURITY_SENTINEL": "present"}
                env.pop("WRONG_SECURE", None)
                if wrong:
                    env["WRONG_SECURE"] = "1"
                result = subprocess.run([str(binary), mode], env=env, capture_output=True, text=True, timeout=10)
                assert result.returncode == (84 if wrong else 37), (cc, mode, wrong, result.stdout, result.stderr)
                assert "::vm-test::pass" not in result.stdout
    (path / "bits").mkdir()
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
    for cc in os.environ.get("WASM_CONTEXT_COMPILERS", "clang clang-22").split():
        resource = subprocess.check_output([cc, "-print-resource-dir"], text=True).strip()
        for bits in (32, 64):
            flags = [cc, f"--target=wasm{bits}", "-nostdinc", "-I", tmp,
                     "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                     "-I", str(MUSL / "include"), "-isystem", resource + "/include"]
            for filename in ("runtime.c", "helper.c"):
                source = str(SOURCES / filename)
                subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", source], check=True)
                subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null", source], check=True)
print("Exec security helper protocol, wrong-AT_SECURE controls and Wasm frontend/analysis passed")
