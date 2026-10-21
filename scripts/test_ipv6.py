#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native IPv6 workload and existing Wasm ABI checks; not target runtime evidence."""
import pathlib
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/ipv6.c"
MUSL = ROOT / "sources/musl"


class IPv6(unittest.TestCase):
    def test_host_busybox_http_over_ipv6(self):
        # A host reference applet is not the pinned Wasm BusyBox binary.
        with tempfile.TemporaryDirectory(prefix="ipv6-http-") as tmp:
            root = pathlib.Path(tmp)
            (root / "index.html").write_text("IPv6 HTTP content\n")
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as reservation:
                reservation.bind(("::1", 0))
                port = reservation.getsockname()[1]
            server = subprocess.Popen(["busybox", "httpd", "-f", "-p", f"[::1]:{port}", "-h", tmp],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 5
                while True:
                    self.assertIsNone(server.poll(), "host HTTP server exited before listening")
                    with open("/proc/net/tcp6") as table:
                        ready = any(len(fields := line.split()) > 3 and
                                    fields[1] == f"00000000000000000000000001000000:{port:04X}" and
                                    fields[3] == "0A" for line in table)
                    if ready:
                        break
                    self.assertLess(time.monotonic(), deadline, "host IPv6 listener deadline")
                    time.sleep(0.01)
                subprocess.run(["busybox", "wget", "-Y", "off", "-q", "-O", str(root / "download"),
                                f"http://[::1]:{port}/index.html"], check=True, timeout=10)
                self.assertEqual((root / "download").read_text(), "IPv6 HTTP content\n")
                response = subprocess.run(["busybox", "nc", "-w", "2", "::1", str(port)],
                                          input=b"GET /index.html HTTP/1.0\r\n\r\n", capture_output=True,
                                          check=True, timeout=10)
                self.assertIn(b"IPv6 HTTP content\n", response.stdout)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)

    def test_native_workload_and_packet_info_negative_control(self):
        for compiler in ("gcc", "clang"):
            with self.subTest(compiler=compiler), tempfile.TemporaryDirectory(prefix="ipv6-") as tmp:
                source, binary = pathlib.Path(tmp) / "test.c", pathlib.Path(tmp) / "test"
                for broken in (False, True):
                    text = SOURCE.read_text()
                    if broken:
                        text = text.replace("info.ipi6_ifindex != 0", "info.ipi6_ifindex == 0")
                        self.assertNotEqual(text, SOURCE.read_text())
                    source.write_text(text)
                    subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                    "-fsanitize=address,undefined", str(source), "-o", str(binary)], check=True)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                    if broken:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("packet info loopback and interface", result.stdout)
                        self.assertNotIn("::vm-test::pass", result.stdout)
                    else:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                        self.assertEqual(result.stdout.count(" pass\n"), 3)

    def test_existing_musl_headers_and_workload_both_widths(self):
        with tempfile.TemporaryDirectory(prefix="ipv6-abi-") as tmp:
            bits = pathlib.Path(tmp) / "bits"
            bits.mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")],
                                       input=templates, capture_output=True, text=True, check=True)
            (bits / "alltypes.h").write_text(generated.stdout)
            for target in ("wasm32", "wasm64"):
                with self.subTest(target=target):
                    subprocess.run(["clang", f"--target={target}", "-fsyntax-only", "-std=c11",
                                    "-nostdinc", "-Wall", "-Wextra", "-Werror", "-isystem", tmp,
                                    "-isystem", str(MUSL / "arch/wasm32"), "-isystem", str(MUSL / "arch/generic"),
                                    "-isystem", str(MUSL / "include"), str(SOURCE)], check=True)


if __name__ == "__main__":
    unittest.main()
