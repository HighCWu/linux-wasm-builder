#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native dnotify, disabled-feature control and Wasm frontend review, not target execution."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/dnotify.c"


class Dnotify(unittest.TestCase):
    def test_native_and_disabled_control(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="dnotify-native-") as tmp:
                path = pathlib.Path(tmp)
                source, binary = path / "main.c", path / "test"
                source.write_text(SOURCE.read_text().replace('/tmp/dnotify-XXXXXX', tmp + '/files-XXXXXX'))
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", str(source)]
                subprocess.run([*flags, "-o", str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 3)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                self.assertEqual(len(list(path.glob("files-*"))), 0)
                subprocess.run([*flags, str(ROOT / "scripts/fixtures/dnotify_disabled.c"),
                                "-Wl,--wrap=fcntl", "-o", str(binary)], check=True)
                negative = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                self.assertNotEqual(negative.returncode, 0)
                self.assertIn("one-shot registration", negative.stdout)
                self.assertNotIn("::vm-test::pass", negative.stdout)

    def test_both_wasm_frontends_and_static_analysis(self):
        with tempfile.TemporaryDirectory(prefix="dnotify-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "include")]
            for bits in (32, 64):
                with self.subTest(bits=bits):
                    common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                    subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
                    analyzed = subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror",
                                               str(SOURCE), "-o", "/dev/null"], capture_output=True, text=True)
                    self.assertEqual(analyzed.returncode, 0, analyzed.stderr)


if __name__ == "__main__":
    unittest.main()
