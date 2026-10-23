#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native stopped-frame reference and test-only interposition, not target nesting evidence."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/fork-continuation/syscall-reentry.c"
CORRUPT_PROC = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
FILE *__real_fopen(const char *,const char *);
FILE *__wrap_fopen(const char *path,const char *mode) {
    FILE *file = __real_fopen(path,mode);
    if (!file || !strstr(path,"/syscall")) return file;
    char line[256];
    if (!fgets(line,sizeof line,file)) { fclose(file); return NULL; }
    fclose(file);
    long number;
    unsigned long args[6],sp;
    if (sscanf(line,"%ld %lx %lx %lx %lx %lx %lx %lx",&number,
        &args[0],&args[1],&args[2],&args[3],&args[4],&args[5],&sp) != 8) return NULL;
#if BAD_FIELD == 0
    number ^= 8;
#elif BAD_FIELD == 1
    sp ^= 16;
#else
    args[2] ^= 1;
#endif
    static char changed[256];
    int length = snprintf(changed,sizeof changed,"%ld %lx %lx %lx %lx %lx %lx %lx\n",
        number,args[0],args[1],args[2],args[3],args[4],args[5],sp);
    if (length <= 0 || length >= (int)sizeof changed) return NULL;
    return fmemopen(changed,(size_t)length,"r");
}
'''


class SyscallReentry(unittest.TestCase):
    def test_native_metadata_and_independent_field_corruption_controls(self):
        with tempfile.TemporaryDirectory(prefix="syscall-reentry-native-") as tmp:
            binary, shim = Path(tmp) / "test", Path(tmp) / "corrupt.c"
            shim.write_text(CORRUPT_PROC)
            for cc in ("gcc", "clang"):
                flags = [cc, "-O2", "-pthread", "-Wall", "-Wextra", "-Werror", str(SOURCE),
                         "-Wl,--wrap=pthread_mutex_lock"]
                for field in (-1, 0, 1, 2):
                    extra = [str(shim), f"-DBAD_FIELD={field}", "-Wl,--wrap=fopen"] if field >= 0 else []
                    subprocess.run([*flags, *extra, "-o", str(binary)], check=True)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                    if field < 0:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertEqual(result.stdout.count(" pass\n"), 2)
                        self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("keeps entered syscall arguments" if field == 2 else "keeps outer syscall number and C stack", result.stdout)
                        self.assertNotIn("::vm-test::pass", result.stdout)

    def test_both_frontends_and_static_analysis(self):
        with tempfile.TemporaryDirectory(prefix="syscall-reentry-abi-") as tmp:
            path = Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            unistd = (MUSL / "include/unistd.h").read_text()
            gate = "#ifndef __wasm__\npid_t fork(void);\npid_t _Fork(void);\n#endif"
            self.assertIn(gate, unistd)
            (path / "unistd.h").write_text(unistd.replace(gate, "pid_t fork(void);\npid_t _Fork(void);"))
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "include")]
            for bits in (32, 64):
                common = [os.environ.get("WASM_CC", "clang"), f"--target=wasm{bits}", "-nostdinc", *includes]
                subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
                subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(SOURCE),
                                "-o", "/dev/null"], check=True)


if __name__ == "__main__":
    unittest.main()
