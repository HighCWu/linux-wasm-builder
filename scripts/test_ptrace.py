#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native tracing, remote-write negative control and Wasm source review; not target execution."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/fork-continuation/ptrace.c"


class Ptrace(unittest.TestCase):
    def test_native_and_no_write_control(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="ptrace-native-") as tmp:
                binary = pathlib.Path(tmp) / "test"
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                         "-fno-sanitize-recover=all", str(SOURCE)]
                subprocess.run([*flags, "-o", str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 4)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                for fixture, wrapped, reason in (("ptrace_no_write.c", "ptrace", "read back full-width remote data"),
                                                 ("ptrace_masked_stop.c", "syscall", "original stopped mask")):
                    subprocess.run([*flags, str(ROOT / "scripts/fixtures" / fixture),
                                    f"-Wl,--wrap={wrapped}", "-o", str(binary)], check=True)
                    negative = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(negative.returncode, 0)
                    self.assertIn(reason, negative.stdout)
                    self.assertNotIn("::vm-test::pass", negative.stdout)

    def test_wasm_frontends_and_existing_libc_call_path(self):
        with tempfile.TemporaryDirectory(prefix="ptrace-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            # Match the existing optional continuation profile's declaration
            # change without modifying the default musl checkout or workload.
            unistd = (MUSL / "include/unistd.h").read_text()
            old = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
            self.assertEqual(unistd.count(old), 1)
            (path / "unistd.h").write_text(unistd.replace(old, "pid_t fork(void);\npid_t _Fork(void);"))
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"),
                        "-I", str(MUSL / "include")]
            for bits in (32, 64):
                for source in (SOURCE, MUSL / "src/linux/ptrace.c"):
                    with self.subTest(bits=bits, source=source.name):
                        common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                        warnings = ["-Wall", "-Wextra", "-Werror"]
                        if source != SOURCE:
                            # Stock internal syscall.h has an unused socketcall
                            # argument on architectures without socketcall.
                            warnings.append("-Wno-unused-parameter")
                        subprocess.run([*common, "-fsyntax-only", *warnings, str(source)], check=True)
                        result = subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror",
                                                 str(source), "-o", "/dev/null"], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generic_kernel_dispatch_and_no_debug_hardware_state(self):
        arch = pathlib.Path(os.environ.get("WASM_PTRACE_ARCH_SOURCE", ROOT / "sources/linux/arch/wasm"))
        dispatch = (arch / "kernel/ptrace.c").read_text()
        header = (arch / "include/uapi/asm/ptrace.h").read_text()
        self.assertIn("return ptrace_request(child, request, addr, data);", dispatch)
        self.assertIn("void ptrace_disable(struct task_struct *child)", dispatch)
        self.assertNotIn("BUG()", dispatch)
        self.assertNotIn("static inline long arch_ptrace", header)
        self.assertNotIn("static inline void ptrace_disable", header)
        entry = (arch / "kernel/syscall.c").read_text()
        self.assertIn("regs->syscall_nr = nr;\n\t\tnr = syscall_enter_from_user_mode(regs, nr);", entry)


if __name__ == "__main__":
    unittest.main()
