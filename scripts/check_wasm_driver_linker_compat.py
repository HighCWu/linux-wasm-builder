#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the candidate's focused Wasm driver and linker regression tests."""

import argparse
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--tools-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.source_root.resolve()
    tools = args.tools_dir.resolve()
    lit = source / "llvm/utils/lit/lit.py"
    tests = [
        source / "clang/test/Driver/wasm-export-dynamic.c",
        source / "lld/test/wasm/as-needed.s",
    ]
    for path in [lit, *tests]:
        if not path.is_file():
            parser.error(f"required candidate source file is missing: {path}")
    for name in ["clang", "wasm-ld", "llvm-mc", "llvm-as", "obj2yaml", "split-file", "FileCheck", "not"]:
        if not (tools / name).is_file():
            parser.error(f"required candidate tool is missing: {tools / name}")

    with tempfile.TemporaryDirectory(prefix="wasm-linker-compat-") as directory:
        root = Path(directory)
        for test in tests:
            shutil.copyfile(test, root / test.name)
        config = "\n".join([
            "import os",
            "import lit.formats",
            "config.name = 'Wasm driver and linker compatibility'",
            "config.test_format = lit.formats.ShTest(execute_external=True)",
            "config.suffixes = ['.c', '.s']",
            f"config.test_source_root = {str(root)!r}",
            f"config.test_exec_root = {str(root / 'output')!r}",
            f"config.environment['PATH'] = {str(tools)!r} + os.pathsep + os.environ.get('PATH', '')",
            f"config.substitutions.append(('%clang', {shlex.quote(str(tools / 'clang'))!r}))",
            "",
        ])
        (root / "lit.cfg.py").write_text(config)
        subprocess.run([sys.executable, str(lit), "-v", str(root)], check=True)


if __name__ == "__main__":
    main()
