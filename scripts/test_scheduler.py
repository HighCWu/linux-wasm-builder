#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Existing musl dispatch and bounded scheduler workload, not target acceptance."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
SOURCE = ROOT / "sources/distro/distro/toolchain-smoke/scheduler.c"
FUNCTIONS = ["sched_getscheduler", "sched_getparam", "sched_setparam", "sched_setscheduler"]


class Scheduler(unittest.TestCase):
    def test_native_workload_and_fake_change_control(self):
        env = {**os.environ, "ASAN_OPTIONS": "symbolize=0:halt_on_error=1:disable_coredump=1"}
        for cc in ("gcc", "clang"):
            with self.subTest(cc=cc), tempfile.TemporaryDirectory(prefix="scheduler-native-") as tmp:
                path = pathlib.Path(tmp)
                binary = path / "test"
                flags = [cc, "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                         "-fno-sanitize-recover=all", str(SOURCE)]
                subprocess.run([*flags, "-o", str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True, env=env, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(" pass\n"), 3)
                self.assertEqual(result.stdout.count("::vm-test::pass"), 1)
                control = path / "control.c"
                control.write_text("#include <sched.h>\nint __wrap_sched_setscheduler(int p, int s, "
                                   "const struct sched_param *v) { (void)p; (void)s; (void)v; return 0; }\n")
                subprocess.run([*flags, str(control), "-Wl,--wrap=sched_setscheduler", "-o", str(binary)], check=True)
                negative = subprocess.run([str(binary)], capture_output=True, text=True, env=env, timeout=15)
                self.assertNotEqual(negative.returncode, 0)
                self.assertIn("batch policy and parameter change is real", negative.stdout)
                self.assertNotIn("::vm-test::pass", negative.stdout)

    def test_real_musl_machine_words_and_errno(self):
        with tempfile.TemporaryDirectory(prefix="scheduler-abi-") as tmp:
            path = pathlib.Path(tmp)
            (path / "bits").mkdir()
            templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (MUSL / "include/alltypes.h.in").read_text()
            generated = subprocess.run(["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates,
                                       capture_output=True, text=True, check=True)
            (path / "bits/alltypes.h").write_text(generated.stdout)
            numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
            (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
            includes = ["-I", tmp, "-I", str(MUSL / "arch/wasm32"), "-I", str(MUSL / "arch/generic"),
                        "-I", str(MUSL / "src/include"), "-I", str(MUSL / "src/internal"), "-I", str(MUSL / "include")]
            for bits in (32, 64):
                common = ["clang", f"--target=wasm{bits}", "-nostdinc", *includes]
                subprocess.run([*common, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", str(SOURCE)], check=True)
                subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", str(SOURCE), "-o", "/dev/null"], check=True)
                for old in (False, True):
                    sources = []
                    for name in FUNCTIONS:
                        original = MUSL / f"src/sched/{name}.c"
                        copy = path / f"{name}.c"
                        # Force the retained direct-upstream stub for a negative control.
                        copy.write_text(original.read_text().replace("#ifdef __wasm__", "#if 0") if old else original.read_text())
                        sources.append(str(copy))
                    for unit in sources:
                        subprocess.run([*common, "--analyze", "-Xanalyzer", "-analyzer-werror", unit,
                                        "-o", "/dev/null"], check=True)
                    binary = path / "test.wasm"
                    subprocess.run([*common, "-O2", "-nostdlib", "-ffreestanding", "-Wl,--no-entry",
                                    "-Wl,--export=run", "-Wl,--export=last_error", *sources,
                                    str(MUSL / "src/internal/syscall_ret.c"),
                                    str(ROOT / "scripts/fixtures/scheduler_calls.c"), "-o", str(binary)], check=True)
                    subprocess.run(["node", "--input-type=module", "-e", """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const wide = process.argv[2] === '64', old = process.argv[3] === 'true';
const word = n => wide ? BigInt(n) : n;
const pointer = wide ? 0x123456789n : 0x76543210;
let phase = 0, calls = 0, result = 0;
const {instance} = await WebAssembly.instantiate(readFileSync(process.argv[1]), {linux: {
  syscall(n, ...args) {
    ++calls;
    assert.equal(n, word([120, 121, 118, 119][phase]));
    assert.deepEqual(args, [word(-7), phase === 0 ? word(0) : phase === 3 ? word(3) : pointer,
      phase === 3 ? pointer : word(0), word(0), word(0), word(0)]);
    return word(result);
  }
}});
for (phase = 0; phase < 4; ++phase) {
  for (result of [0, 3, -22, -3, -14, -38]) {
    assert.equal(instance.exports.run(phase, pointer), old || result < 0 ? -1 : result);
    assert.equal(instance.exports.last_error(), old ? 38 : result < 0 ? -result : 0);
  }
}
assert.equal(calls, old ? 0 : 24);
""", str(binary), str(bits), str(old).lower()], check=True)


if __name__ == "__main__":
    unittest.main()
