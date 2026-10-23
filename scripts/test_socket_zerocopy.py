#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native Linux copied-completion reference and Wasm ABI analysis; not target kernel acceptance."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/socket-zerocopy.c"
BAD_COMPLETION = r"""
#define _GNU_SOURCE
#include <netinet/in.h>
#include <sys/socket.h>
ssize_t __real_recvmsg(int, struct msghdr *, int);
ssize_t __wrap_recvmsg(int fd, struct msghdr *msg, int flags) {
    ssize_t n = __real_recvmsg(fd,msg,flags);
    if (n >= 0 && (flags & MSG_ERRQUEUE)) {
        for (struct cmsghdr *c = CMSG_FIRSTHDR(msg); c; c = CMSG_NXTHDR(msg,c)) {
            if ((c->cmsg_level == IPPROTO_IP && c->cmsg_type == IP_RECVERR) ||
                (c->cmsg_level == IPPROTO_IPV6 && c->cmsg_type == IPV6_RECVERR)) {
                if (c->cmsg_len >= CMSG_LEN(16)) {
#ifdef BAD_SEQUENCE
                    CMSG_DATA(c)[8] ^= 1;
#else
                    CMSG_DATA(c)[6] = 0; /* falsely claim no copy */
#endif
                }
            }
        }
    }
    return n;
}
"""


class SocketZerocopy(unittest.TestCase):
    def test_native_data_completions_and_bad_metadata_control(self):
        with tempfile.TemporaryDirectory(prefix="socket-zc-native-") as tmp:
            binary, shim = Path(tmp) / "test", Path(tmp) / "bad.c"
            shim.write_text(BAD_COMPLETION)
            for cc in ("gcc", "clang"):
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                         "-fno-sanitize-recover=all", str(SOURCE)]
                subprocess.run([*flags, "-o", str(binary)], check=True)
                env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1",
                       "UBSAN_OPTIONS": "halt_on_error=1"}
                result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30, env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 4)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                for extra in ([], ["-DBAD_SEQUENCE"]):
                    subprocess.run([*flags, *extra, str(shim), "-Wl,--wrap=recvmsg", "-o", str(binary)], check=True)
                    result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=15, env=env)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("copied completion and send sequence", result.stdout)
                    self.assertNotIn("::vm-test::pass", result.stdout)

    def test_both_wasm_frontends_and_static_analysis(self):
        musl = ROOT / "sources/musl"
        with tempfile.TemporaryDirectory(prefix="socket-zc-abi-") as tmp:
            path = Path(tmp)
            (path / "bits").mkdir()
            templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                        "-I", str(musl / "include")]
            for bits in (32, 64):
                flags = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                subprocess.run([*flags, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
                subprocess.run([*flags, "--analyze", "-Xanalyzer", "-analyzer-werror", str(SOURCE),
                                "-o", "/dev/null"], check=True)


if __name__ == "__main__":
    unittest.main()
