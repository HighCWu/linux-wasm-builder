# SPDX-License-Identifier: MIT
"""Guard the targeted cache's restore/save key contract without a Nix build."""
import re
import unittest
from pathlib import Path


def check_keys(workflow):
    heavy = re.split(r"^  heavy-check:\n", workflow, maxsplit=1, flags=re.MULTILINE)[1]
    heavy = re.split(r"^  deploy-site:\n", heavy, maxsplit=1, flags=re.MULTILINE)[0]
    keys = re.findall(r"^          primary-key: (.*)$", heavy, re.MULTILINE)
    if len(keys) != 2 or not keys[0] or keys[0] != keys[1]:
        raise ValueError("targeted restore and save must use the same nonempty key")
    if not keys[0].startswith("nix-targeted-") or "outputs.primary-key" in keys[0]:
        raise ValueError("targeted keys must not rely on the restore action's empty output")
    for component in ("runner.os", "wasm64", "hashFiles(", "flake.lock"):
        if component not in keys[0]:
            raise ValueError(f"cache key is missing {component}")


class CacheContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (Path(__file__).resolve().parents[1] /
                        "sources/distro/.github/workflows/ci.yml").read_text()

    def test_current_configuration(self):
        check_keys(self.workflow)

    def test_mismatched_keys_rejected(self):
        with self.assertRaises(ValueError):
            check_keys(self.workflow.replace("nix-targeted-v1-", "nix-targeted-v2-", 1))

    def test_action_output_rejected(self):
        broken = re.sub(r"primary-key: nix-targeted-.*", "primary-key: ${{ steps.heavy-cache.outputs.primary-key }}", self.workflow)
        with self.assertRaises(ValueError):
            check_keys(broken)


if __name__ == "__main__":
    unittest.main()
