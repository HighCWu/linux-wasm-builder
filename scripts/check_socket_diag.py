#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the real ss output verifier without opening sockets or changing credentials."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
program = ROOT / "sources/distro/distro/socket-diag/runtime.c"
fixture = r"""
#define main socket_diag_vm_entry
#include "CONSUMER"
#undef main
#include <assert.h>
int main(void)
{
    const char *rows = "u_str LISTEN 0 1 @linux-wasm-ss-12-65534 12 * 0 uid:65534 ino:12 sk:abc\n"
        "udp UNCONN 0 0 127.0.0.1:12345 0.0.0.0:* uid:655340 ino:123 sk:def\n";
    assert(inode_row(rows, 12) == rows);
    assert(inode_row(rows, 123) == strchr(rows, '\n') + 1);
    assert(!inode_row(rows, 1) && !inode_row(rows, 1234) && !inode_row("", 12));
    assert(row_has(rows, "linux-wasm-ss-12-65534") && row_has(rows, "uid:65534"));
    assert(!row_has(rows, "127.0.0.1:12345") && !row_has(rows, "uid:6553"));
    assert(row_has(inode_row(rows, 123), "127.0.0.1:12345"));
    assert(!row_has(inode_row(rows, 123), "127.0.0.1:1234"));
    assert(!row_has(inode_row(rows, 123), "uid:65534"));
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="socket-diag-parser-") as tmp:
    path = Path(tmp) / "fixture.c"
    path.write_text(fixture.replace("CONSUMER", str(program)))
    for compiler in ("gcc", "clang"):
        binary = Path(tmp) / compiler
        command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", str(path)]
        subprocess.run([*command, "-O2", "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
        if compiler == "clang":
            subprocess.run(
                [
                    *command,
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    "-o",
                    "/dev/null",
                ],
                check=True,
            )

print(
    "Actual ss verifier: exact inodes/UIDs/addresses, row boundaries and empty-output refusal pass; no host socket/credential execution"
)
