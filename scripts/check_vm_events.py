#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check event-counter restoration and consumer parsing; never mount on the host."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = Path(os.environ.get("WASM_VM_EVENTS_SOURCE_ROOT", ROOT / "sources/linux"))
DISTRO = ROOT / "sources/distro/distro"
source = (DISTRO / "vm-events/runtime.c").read_text()
shell = (DISTRO / "vm-events/runtime-test.sh").read_text()
config = (
    (LINUX / "mm/Kconfig")
    .read_text()
    .split("config VM_EVENT_COUNTERS\n", 1)[1]
    .split("\nconfig ", 1)[0]
)
assert "default y" in config and "depends on MMU" not in config
for name in ("defconfig", "wasm32_defconfig", "wasm64_defconfig"):
    assert (
        "CONFIG_VM_EVENT_COUNTERS"
        not in (LINUX / "arch/wasm/configs" / name).read_text()
    )
assert (
    "grep -qx 'CONFIG_VM_EVENT_COUNTERS=y' .config"
    in (DISTRO / "linux/package.nix").read_text()
)
busybox = (DISTRO / "busybox/package.nix").read_text()
assert "config VMSTAT y" in busybox and "grep -qx 'CONFIG_VMSTAT=y' .config" in busybox

harness = r"""
#include <assert.h>
static int parse(const char *text, struct vm_events *events) {
    FILE *f=fmemopen((void *)text,strlen(text),"r");assert(f);
    int result=read_events(f,events);assert(!fclose(f));return result;
}
int main(void) {
    struct vm_events events={0};
    const char *good="nr_free_pages 1\npgalloc_normal 4294967296\npgfree 18446744073709551615\npgpgin 0\npgpgout 23\n";
    assert(!parse(good,&events));
    assert(events.value[ALLOC]==UINT64_C(4294967296) && events.value[FREE]==UINT64_MAX);
    assert(events.value[IN]==0 && events.value[OUT]==23);
    const char *bad[]={
        "nr_free_pages 1\n", /* disabled event counters cannot become zeros */
        "pgalloc_normal 1\npgfree 1\npgpgin 0\npgpgout 2\npgfree 1\n",
        "pgalloc_normal -1\npgfree 1\npgpgin 0\npgpgout 2\n",
        "pgalloc_normal +1\npgfree 1\npgpgin 0\npgpgout 2\n",
        "pgalloc_normal 18446744073709551616\npgfree 1\npgpgin 0\npgpgout 2\n",
        "pgalloc_normal 1\npgfree 1\npgpgin 0\npgpgout 2 extra\n",
        "pgalloc_normal 1\npgfree 1\npgpgin 0\npgpgout 2",
    };
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) assert(parse(bad[i],&events)==-1);
}
"""
with tempfile.TemporaryDirectory(prefix="vm-events-check-") as tmp:
    path = Path(tmp)
    unit = path / "parser.c"
    unit.write_text(
        "#define main vm_events_target_main\n" + source + "\n#undef main\n" + harness
    )
    for cc in ("gcc", "clang"):
        binary = path / "parser"
        subprocess.run(
            [
                cc,
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(unit),
                "-o",
                str(binary),
            ],
            check=True,
        )
        subprocess.run([str(binary)], check=True)
    subprocess.run(
        [
            "clang",
            "--analyze",
            "-Xanalyzer",
            "-analyzer-werror",
            str(unit),
            "-o",
            "/dev/null",
        ],
        check=True,
    )

    # Exercise the exact awk admission independently of a live vmstat process.
    awk = shell.split("awk '\n", 1)[1].split("\n' /tmp/vmstat.out", 1)[0]
    row = " ".join(["0"] * 17) + "\n"
    for report, valid in (
        ("header\n" + row * 2, True),
        (row, False),
        (row * 3, False),
        (row + row.replace("0", "bad", 1), False),
        (row + " ".join(["0"] * 15) + "\n", False),
    ):
        result = subprocess.run(["awk", awk], input=report, text=True)
        assert (result.returncode == 0) == valid

    musl = ROOT / "sources/musl"
    (path / "bits").mkdir()
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        musl / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.check_output(
        ["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates, text=True
    )
    (path / "bits/alltypes.h").write_text(generated)
    numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    resource = subprocess.check_output(
        ["clang", "-print-resource-dir"], text=True
    ).strip()
    for bits in (32, 64):
        command = [
            "clang",
            f"--target=wasm{bits}",
            "-std=c11",
            "-nostdinc",
            "-I",
            tmp,
            "-I",
            str(musl / "arch/wasm32"),
            "-I",
            str(musl / "arch/generic"),
            "-I",
            str(musl / "include"),
            "-isystem",
            resource + "/include",
            "-Wall",
            "-Wextra",
            "-Werror",
        ]
        program = str(DISTRO / "vm-events/runtime.c")
        subprocess.run([*command, "-fsyntax-only", program], check=True)
        subprocess.run(
            [
                *command,
                "--analyze",
                "-Xanalyzer",
                "-analyzer-werror",
                program,
                "-o",
                "/dev/null",
            ],
            check=True,
        )
print(
    "VM events: default intent, missing/duplicate/overflow parser controls, vmstat sample gate and Wasm frontends/analysis passed; no host mounts"
)
