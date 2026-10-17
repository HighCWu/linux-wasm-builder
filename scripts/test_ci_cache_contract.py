# SPDX-License-Identifier: MIT
"""Guard the targeted cache's restore/save key contract without a Nix build."""
import re
import unittest
from pathlib import Path

WIDTH_SELECTOR = "(contains(matrix.check, 'wasm64') || contains(matrix.check, 'memory64'))"


def classify_width(selector, check):
    """Evaluate only the small OR predicate used by the workflow, not arbitrary code."""
    match = re.fullmatch(
        r"\(contains\(matrix.check, '([a-z0-9]+)'\) \|\| contains\(matrix.check, '([a-z0-9]+)'\)\)",
        selector,
    )
    if not match:
        raise ValueError("width selection must be an explicit two-name OR predicate")
    return "wasm64" if any(name in check for name in match.groups()) else "wasm32"


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
    expressions = re.findall(r"\$\{\{\s*(.*?)\s*\}\}", heavy)
    width_decisions = [expression for expression in expressions
                       if "contains(matrix.check, 'wasm64')" in expression
                       or "contains(matrix.check, 'memory64')" in expression]
    if len(width_decisions) != 7 or any(WIDTH_SELECTOR not in item for item in width_decisions):
        raise ValueError("all seven cache/artifact/retention selectors must recognize memory64 and wasm64")


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

    def test_actual_check_names_select_matching_width(self):
        selector = re.search(
            r"WASM64_CHECK: \$\{\{ (.*?) \}\}", self.workflow
        ).group(1)
        cases = {
            "browser-tests-check-memory64-chromium": "wasm64",
            "browser-tests-check-memory64-firefox": "wasm64",
            "browser-tests-check-runtime-wasm32-chromium": "wasm32",
            "browser-tests-check-runtime-wasm32-firefox": "wasm32",
            "curl-wasm64-check-development": "wasm64",
            "curl-check-development": "wasm32",
            "browser-tests-check-agent-production-wasm64-chromium": "wasm64",
            "kernel-wasm64-check-source-bundle": "wasm64",
            "kernel-check-source-bundle": "wasm32",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify_width(selector, name), expected)

    def test_old_consistent_but_wrong_memory64_selection_rejected(self):
        old = self.workflow.replace(WIDTH_SELECTOR, "contains(matrix.check, 'wasm64')")
        with self.assertRaises(ValueError):
            check_keys(old)

    def test_artifact_selector_cannot_disagree_with_cache(self):
        broken = self.workflow.replace(
            f"WASM64_CHECK: ${{{{ {WIDTH_SELECTOR} }}}}",
            "WASM64_CHECK: ${{ contains(matrix.check, 'wasm64') }}",
            1,
        )
        with self.assertRaises(ValueError):
            check_keys(broken)


if __name__ == "__main__":
    unittest.main()
