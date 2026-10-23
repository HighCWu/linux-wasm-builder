#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact NOMMU copy model and native workload, not a Wasm kernel acceptance."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/distro/distro/fork-continuation/process-vm.c"
ENV = {**os.environ, "ASAN_OPTIONS": "symbolize=0:halt_on_error=1:abort_on_error=1:disable_coredump=1"}


class ProcessVm(unittest.TestCase):
    def test_wasm_frontends_and_unchanged_libc(self):
        musl = ROOT / "sources/musl"
        with tempfile.TemporaryDirectory(prefix="process-vm-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (musl / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (musl / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            unistd = (musl / "include/unistd.h").read_text()
            old = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
            self.assertEqual(unistd.count(old), 1)
            (path / "unistd.h").write_text(unistd.replace(old, "pid_t fork(void);\npid_t _Fork(void);"))
            includes = ["-I", tmp, "-I", str(musl / "arch/wasm32"), "-I", str(musl / "arch/generic"),
                        "-I", str(musl / "src/include"), "-I", str(musl / "src/internal"), "-I", str(musl / "include")]
            for bits in (32, 64):
                for source in (SOURCE, musl / "src/linux/process_vm.c"):
                    common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                    subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror",
                                    "-Wno-unused-parameter", str(source)], check=True)
                    subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(source),
                                    "-o", "/dev/null"], check=True)

    def test_exact_nommu_copy_and_missing_rollback_control(self):
        source = pathlib.Path(os.environ.get("WASM_PROCESS_VM_SOURCE", ROOT / "sources/linux/mm/process_vm_access.c")).read_text()
        body = source.split("#else /* CONFIG_MMU */\n", 1)[1].split("#endif /* CONFIG_MMU */", 1)[0]
        harness = (ROOT / "scripts/fixtures/process_vm_nommu.c").read_text()
        marker = "/* Insert the actual NOMMU helper here, unchanged. */"
        guard = "iov_iter_revert(iter, copied - remote);"
        self.assertEqual(body.count(guard), 1)
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="process-vm-model-") as tmp:
                path = pathlib.Path(tmp)
                unit, binary = path / "main.c", path / "test"
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                         "-fsanitize=address,undefined", "-fno-sanitize-recover=all", str(unit), "-o", str(binary)]
                for fault in ("none", "rollback", "scheduling"):
                    changed = body
                    if fault == "rollback":
                        changed = body.replace(guard, "(void)iov_iter_revert;")
                    if fault == "scheduling":
                        self.assertEqual(body.count("cond_resched();"), 1)
                        changed = body.replace("cond_resched();", "(void)cond_resched;")
                    unit.write_text(harness.replace(marker, changed))
                    subprocess.run(flags, check=True)
                    run = subprocess.run([str(binary)], capture_output=True, text=True, env=ENV, timeout=15)
                    if fault != "none":
                        self.assertNotEqual(run.returncode, 0)
                        self.assertIn("iter.done == 777" if fault == "rollback" else
                                      "schedule_checks == timer_polls", run.stderr)
                        self.assertNotIn("cleanup pass", run.stdout)
                    else:
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                        subprocess.run(["clang", "--analyze", "-Xanalyzer", "-analyzer-werror", str(unit),
                                        "-o", "/dev/null"], check=True)

    def test_native_and_fake_remote_write_control(self):
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="process-vm-native-") as tmp:
                path = pathlib.Path(tmp)
                binary, fixture = path / "test", path / "no-write.c"
                fixture.write_text("#define _GNU_SOURCE\n#include <sys/uio.h>\nextern ssize_t __real_process_vm_writev"
                                   "(pid_t, const struct iovec *, unsigned long, const struct iovec *, unsigned long, unsigned long);\n"
                                   "ssize_t __wrap_process_vm_writev"
                                   "(pid_t p, const struct iovec *l, unsigned long n, const struct iovec *r, "
                                   "unsigned long m, unsigned long f) { static int calls; "
                                   "if (!calls++) return __real_process_vm_writev(p,l,n,r,m,f); "
                                   "size_t total=0; for(unsigned long i=0;i<n;++i)total+=l[i].iov_len; return total; }\n")
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                         "-fno-sanitize-recover=all", str(SOURCE)]
                for old in (False, True):
                    subprocess.run([*flags, *([str(fixture), "-Wl,--wrap=process_vm_writev"] if old else []),
                                    "-o", str(binary)], check=True)
                    run = subprocess.run([str(binary)], capture_output=True, text=True, env=ENV, timeout=20)
                    if old:
                        self.assertNotEqual(run.returncode, 0)
                        self.assertIn("remote write followed by full readback", run.stdout)
                        self.assertNotIn("::vm-test::pass", run.stdout)
                    else:
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                        self.assertEqual(run.stdout.count(" pass\n"), 3)
                        self.assertEqual(run.stdout.count("::vm-test::pass"), 1)


if __name__ == "__main__":
    unittest.main()
