#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the actual named build inputs, not resolved Kconfig or a kernel boot."""
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = Path(os.environ.get("WASM_DEFCONFIG_ROOT", ROOT / "sources/linux/arch/wasm/configs"))
recipe = (ROOT / "sources/distro/distro/linux/package.nix").read_text()
assert 'make wasm${toString wasmBits}_defconfig' in recipe, "review selected Kbuild targets if build recipe changes"
required = ("KEYS", "BINFMT_MISC", "FANOTIFY", "FANOTIFY_ACCESS_PERMISSIONS", "EROFS_FS_XATTR", "EROFS_FS_BACKED_BY_FILE", "PACKET")


def check(text, name):
    for option in required:
        assert re.search(r"^CONFIG_" + option + r"=y$", text, re.M), name + ": missing CONFIG_" + option


for name in ("defconfig", "wasm32_defconfig", "wasm64_defconfig"):
    text = (CONFIGS / name).read_text()
    check(text, name)
    for option in required:
        broken = text.replace("CONFIG_" + option + "=y", "# CONFIG_" + option + " is not set")
        try:
            check(broken, name)
        except AssertionError:
            pass
        else:
            raise AssertionError("disabled input escaped validation: " + name + ":" + option)
print("Selected wasm32/wasm64 defconfigs and common input have required features; disabled controls rejected")
