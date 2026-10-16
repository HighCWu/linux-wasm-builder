# SPDX-License-Identifier: MIT
"""Keep SDK spawn preflight bounds aligned with the native v3/v4 parser."""

import math
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def integer(source, name):
    match = re.search(r"\b" + re.escape(name) + r"\s*=\s*([0-9\s*]+)[,;]", source)
    if not match:
        raise AssertionError(f"missing literal integer contract: {name}")
    return math.prod(int(part.strip()) for part in match[1].split("*"))


class SpawnContract(unittest.TestCase):
    def setUp(self):
        self.agent = (ROOT / "sources/distro/distro/guest-agent/agent.c").read_text()
        self.sdk = (ROOT / "sources/distro/packages/linux-guest/src/syscalls.ts").read_text()

    def test_sdk_bounds_match_native_parser(self):
        for native, sdk in [
            ("max_string", "MAX_SPAWN_STRING"),
            ("max_arguments", "MAX_SPAWN_ARGUMENTS"),
            ("max_environment", "MAX_SPAWN_ENVIRONMENT"),
        ]:
            with self.subTest(native=native):
                self.assertEqual(integer(self.agent, native), integer(self.sdk, sdk))

    def test_largest_preflight_valid_body_fits_native_frame(self):
        # argc + argv strings + cwd string + envc + environment strings.
        strings = 1 + integer(self.sdk, "MAX_SPAWN_ARGUMENTS") + integer(self.sdk, "MAX_SPAWN_ENVIRONMENT")
        largest = 8 + strings * (4 + integer(self.sdk, "MAX_SPAWN_STRING"))
        self.assertLessEqual(largest, integer(self.agent, "max_spawn_payload"))


if __name__ == "__main__":
    unittest.main()
