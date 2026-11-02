#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Replay Linux cipher report variants through the real consumer, without sockets."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
program = ROOT / "sources/distro/distro/netlink-crypto/runtime.c"
fixture = r"""
#define main netlink_vm_entry
#include "CONSUMER"
#undef main
#include <stddef.h>

int main(int argc, char **argv)
{
    CHECK(argc == 2, "fixture mode");
    struct {
        struct nlmsghdr header;
        struct crypto_user_alg algorithm;
        struct nlattr attribute;
        struct crypto_report_blkcipher cipher;
    } message = {0};
    _Static_assert(offsetof(typeof(message), attribute) ==
        NLMSG_LENGTH(sizeof(struct crypto_user_alg)), "attribute placement");
    message.header.nlmsg_len = sizeof(message);
    strcpy(message.algorithm.cru_name, "cbc(aes)");
    strcpy(message.algorithm.cru_driver_name, "cbc-aes-generic");
    message.attribute.nla_type = CRYPTOCFGA_REPORT_BLKCIPHER;
    message.attribute.nla_len = NLA_HDRLEN + sizeof(message.cipher);
    message.cipher.blocksize = 16;
    message.cipher.min_keysize = 16;
    message.cipher.max_keysize = 32;
    message.cipher.ivsize = 16;
    const char *type = !strcmp(argv[1], "wrong-iv") ? "lskcipher" : argv[1];
    CHECK(strlen(type) < sizeof(message.cipher.type), "fixture type bound");
    strcpy(message.cipher.type, type);
    if (!strcmp(argv[1], "wrong-iv")) message.cipher.ivsize = 12;
    int hash_seen = 0, cipher_seen = 0;
    report(&message.header, "cbc(aes)", &hash_seen, &cipher_seen);
    CHECK(cipher_seen && !hash_seen, "parsed cipher record");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="netlink-crypto-reports-") as tmp:
    directory = Path(tmp)
    path = directory / "fixture.c"
    for cc in ("gcc", "clang"):
        path.write_text(fixture.replace("CONSUMER", str(program)))
        binary = directory / cc
        command = [cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", str(path)]
        subprocess.run([*command, "-O2", "-o", str(binary)], check=True)
        for mode in ("skcipher", "lskcipher"):
            subprocess.run([str(binary), mode], check=True)
        for mode in ("invalid-backend", "wrong-iv"):
            result = subprocess.run([str(binary), mode], capture_output=True, text=True)
            assert result.returncode == 1 and "CBC-AES metadata" in result.stdout
        if cc == "clang":
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
    old = directory / "old-consumer.c"
    source = program.read_text()
    expression = (
        '(!strcmp(cipher->type, "skcipher") || !strcmp(cipher->type, "lskcipher"))'
    )
    assert source.count(expression) == 1
    old.write_text(source.replace(expression, '!strcmp(cipher->type, "skcipher")'))
    path.write_text(fixture.replace("CONSUMER", str(old)))
    binary = directory / "old-predicate"
    subprocess.run(
        ["cc", "-std=gnu11", "-O2", str(path), "-o", str(binary)], check=True
    )
    result = subprocess.run([str(binary), "lskcipher"], capture_output=True, text=True)
    assert result.returncode == 1 and "CBC-AES metadata" in result.stdout

print(
    "Real Netlink parser accepts both Linux cipher reports, rejects invalid metadata and reproduces the old failure; no host socket/credential execution"
)
