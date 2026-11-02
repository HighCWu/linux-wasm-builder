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
    const char *rows = "u_str LISTEN 0 1 @linux-wasm-ss-12-65534 12 * 0 <-> peers:\n"
        "udp UNCONN 0 0 127.0.0.1:12345 0.0.0.0:* uid:655340 ino:123 sk:def\n";
    assert(!inode_row(rows, 12));
    assert(unix_inode_row(rows, 12) == rows);
    assert(!unix_inode_row(rows, 1) && !unix_inode_row(rows, 123));
    assert(column_is(rows, 4, "@linux-wasm-ss-12-65534"));
    assert(!column_is(rows, 4, "@linux-wasm-ss-12-6553"));
    assert(!column_is(rows, 4, "@linux-wasm-ss-12-655340"));
    assert(!column_is(rows, 12, "uid:655340"));
    assert(!unix_inode_row("u_str LISTEN 12 1 @other 123 * 12 ino:12\n", 12));
    assert(!unix_inode_row("u_str LISTEN 0 1 @other\n12 * 0\n", 12));
    assert(inode_row(rows, 123) == strchr(rows, '\n') + 1);
    assert(!inode_row(rows, 1) && !inode_row(rows, 1234) && !inode_row("", 12));
    assert(row_has(rows, "linux-wasm-ss-12-65534") && !row_has(rows, "uid:65534"));
    assert(!row_has(rows, "127.0.0.1:12345") && !row_has(rows, "uid:6553"));
    assert(row_has(inode_row(rows, 123), "127.0.0.1:12345"));
    assert(!row_has(inode_row(rows, 123), "127.0.0.1:1234"));
    assert(!row_has(inode_row(rows, 123), "uid:65534"));
    const char *netlink = "UNCONN 0 0 usersock:123 *\nUNCONN 0 0 usersock:1234 *\n";
    assert(row_has(netlink, "usersock:123"));
    assert(!row_has(netlink, "usersock:12") && !row_has(netlink, "usersock:1234"));
    assert(!row_has(netlink, "usersock:12345"));
    assert(row_has(strchr(netlink, '\n') + 1, "usersock:1234"));
    struct {
        struct nlmsghdr header;
        struct unix_diag_msg record;
        struct { struct nlattr header; uint32_t value; } attributes[2];
    } uid_message = {0};
    uid_message.header.nlmsg_len = sizeof(uid_message) - sizeof(uid_message.attributes[1]);
    uid_message.attributes[0].header.nla_type = UNIX_DIAG_UID;
    uid_message.attributes[0].header.nla_len = NLA_HDRLEN + sizeof(uint32_t);
    uid_message.attributes[0].value = 65534;
    uint32_t uid = UINT32_MAX;
    assert(unix_uid(&uid_message.header, &uid) && uid == 65534);
    uid_message.header.nlmsg_len--;
    assert(!unix_uid(&uid_message.header, &uid));
    uid_message.header.nlmsg_len++;
    uid_message.attributes[0].header.nla_len--;
    assert(!unix_uid(&uid_message.header, &uid));
    uid_message.attributes[0].header.nla_len++;
    uid_message.attributes[0].header.nla_type |= NLA_F_NESTED;
    assert(!unix_uid(&uid_message.header, &uid));
    uid_message.attributes[0].header.nla_type = UNIX_DIAG_UID;
    uid_message.header.nlmsg_len = sizeof(uid_message);
    uid_message.attributes[1] = uid_message.attributes[0];
    assert(!unix_uid(&uid_message.header, &uid));
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
    "Actual ss verifier: real UNIX inode columns/raw UID attributes, INET tags, Netlink ports and malformed/prefix/row rejection pass; no host socket/credential execution"
)
