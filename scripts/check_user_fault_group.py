#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native process-vs-thread fault policy, negative control and Wasm frontends, not target acceptance."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCES = ROOT / "sources/distro/distro/user-fault-group"
source = Path(os.environ.get("WASM_PROCESS_SOURCE", ROOT / "sources/linux/arch/wasm/kernel/process.c")).read_text()
assert re.search(r"wasm_run_user\(\);[\s\S]*?local_irq_enable\(\);\s*do_group_exit\(SIGSEGV\);\s*}", source)
stages = [
    "user-fault-group: unreachable in a worker terminates all process threads pass",
    "user-fault-group: out-of-bounds worker trap terminates all process threads pass",
    "user-fault-group: raw SYS_exit remains thread-only and later parent wait recovers pass",
]
with tempfile.TemporaryDirectory(prefix="user-fault-group-") as tmp:
    path = Path(tmp)
    controller, helper = path / "controller", path / "helper"
    for cc in ("gcc", "clang"):
        subprocess.run([cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                        str(SOURCES / "runtime.c"), "-o", str(controller)], check=True)
        for negative in (False, True):
            subprocess.run([cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                            *(["-DMODEL_THREAD_ONLY_EXIT"] if negative else []),
                            str(SOURCES / "helper.c"), "-o", str(helper)], check=True)
            result = subprocess.run([str(controller), str(helper)], capture_output=True, text=True, timeout=35)
            if negative:
                assert result.returncode == 1, (cc, result.stdout, result.stderr)
                assert "fatal worker must terminate its process" in result.stdout and "status=0x5a00" in result.stdout
                assert "::vm-test::pass" not in result.stdout
            else:
                assert result.returncode == 0, (cc, result.stdout, result.stderr)
                assert all(stage in result.stdout for stage in stages)
                assert result.stdout.count("::vm-test::pass") == 1
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
            flags = [cc, f"--target=wasm{bits}", "-matomics", "-mbulk-memory", "-nostdinc", "-I", tmp,
                     "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                     "-I", str(MUSL / "include"), "-isystem", resource + "/include"]
            for filename in ("runtime.c", "helper.c"):
                file = str(SOURCES / filename)
                subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", file], check=True)
                subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", "-o", "/dev/null", file], check=True)
            assembly = path / "helper.s"
            subprocess.run([*flags, "-O2", "-S", str(SOURCES / "helper.c"), "-o", str(assembly)], check=True)
            text = assembly.read_text()
            assert re.search(r"memory\.size[\s\S]{0,300}?i32\.load", text) and "unreachable" in text
print("native group-fault/thread-exit semantics, concrete old-policy failure, Wasm trap generation and static analysis passed")
