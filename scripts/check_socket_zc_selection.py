#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual draft route selectors with iterator shims; not socket completion or kernel acceptance."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
kernel = Path(os.environ.get("WASM_SOCKET_ZEROCOPY_ROOT", root / "sources/linux"))
cc = os.environ.get("CC", "clang")
shim = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#define IS_ENABLED(x) (x)
struct iov_iter { int user; };
struct msghdr { struct iov_iter msg_iter; };
static struct msghdr message;
static unsigned reads;
static bool user_backed_iter(const struct iov_iter *i) {
    assert(i == &message.msg_iter); reads++; return i->user;
}
static int ip_generic_getfrag(void) { return 0; }
static int other_getfrag(void) { return 1; }
static bool can_pin(int user, int generic) {
    message.msg_iter.user = user;
    struct msghdr *msg = generic ? &message : (void *)1;
    int (*getfrag)(void) = generic ? ip_generic_getfrag : other_getfrag;
    (void)getfrag;
"""
checks = r"""
    return zc_supported;
}
int main(void) {
    for (int user = 0; user <= 1; user++) {
        reads = 0;
        assert(can_pin(user,1) == !(CONFIG_WASM && user));
    }
#ifdef DATAGRAM
    /* A non-generic callback need not receive a struct msghdr at all. */
    reads = 0;
    assert(can_pin(1,0));
    assert(!reads);
#endif
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="socket-zc-select-") as tmp:
    path = Path(tmp)
    unit, binary = path / "select.c", path / "select"
    for file in ("net/ipv4/tcp.c", "net/ipv4/ip_output.c", "net/ipv6/ip6_output.c"):
        source = (kernel / file).read_text()
        matches = re.findall(r"bool zc_supported = .*?;", source, re.S)
        assert len(matches) == 1
        selector = matches[0]
        datagram = file != "net/ipv4/tcp.c"
        for wasm in (0, 1):
            unit.write_text(shim + selector + checks)
            flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", f"-DCONFIG_WASM={wasm}",
                     *(["-DDATAGRAM=1"] if datagram else []), "-fsanitize=address,undefined"]
            subprocess.run([*flags, str(unit), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True, env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1"})
        # Non-Wasm remains untouched. Wasm user data must not choose pinning.
        bad = selector.replace("!user_backed_iter(&msg->msg_iter)", "true")
        assert bad != selector
        unit.write_text(shim + bad + checks)
        subprocess.run([cc, "-O2", "-DCONFIG_WASM=1", *(["-DDATAGRAM=1"] if datagram else []),
                        str(unit), "-o", str(binary)], check=True)
        failed = subprocess.run([str(binary)], capture_output=True)
        assert failed.returncode != 0 and b"can_pin" in failed.stderr, failed.stderr
        if datagram:
            bad = selector.replace("getfrag != ip_generic_getfrag ||", "")
            unit.write_text(shim + bad + checks)
            subprocess.run([cc, "-O2", "-DCONFIG_WASM=1", "-DDATAGRAM=1",
                            str(unit), "-o", str(binary)], check=True)
            failed = subprocess.run([str(binary)], capture_output=True)
            assert failed.returncode != 0
        print(f"{file}: Wasm user-copy selection, kernel iterators, non-Wasm behavior and unsafe-selector controls passed")
