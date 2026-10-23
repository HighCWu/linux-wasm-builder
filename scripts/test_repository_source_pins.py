# SPDX-License-Identifier: MIT
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_repository


class SourcePinParserTests(unittest.TestCase):
    def test_kernel_fetch_retry_keeps_mandatory_hash_and_pinned_mirrors(self):
        recipe = (check_repository.ROOT / "sources/distro/distro/linux/fetch-source.nix").read_text()
        self.assertIn("inherit hash;", recipe)
        self.assertIn('assert builtins.match "[0-9a-f]{40}" rev != null;', recipe)
        for option, value in (("--retry", "5"), ("--retry-delay", "15"), ("--retry-max-time", "180")):
            self.assertRegex(recipe, '"' + option + '"\\s+"' + value + '"')
        self.assertIn("https://codeload.github.com/${owner}/${repo}/tar.gz/${rev}", recipe)
        self.assertIn("https://github.com/${owner}/${repo}/archive/${rev}.tar.gz", recipe)

    def parse(self, fetcher, fields):
        with tempfile.TemporaryDirectory(prefix="source-pin-") as directory:
            path = Path(directory) / "package.nix"
            path.write_text("{ src ? " + fetcher + " {\n" + fields + "\n  },\n}: null\n")
            with patch.object(check_repository, "ROOT", Path(directory)):
                return check_repository.fetch_github_fields(path)

    def test_original_and_codeload_fetcher_keep_identical_pins(self):
        expected = {"owner": "HighCWu", "repo": "linux", "rev": "a" * 40}
        fields = '\n'.join(f'    {key} = "{value}";' for key, value in expected.items())
        for fetcher in ["pkgs.fetchFromGitHub", "import ./fetch-source.nix"]:
            with self.subTest(fetcher=fetcher):
                self.assertEqual(self.parse(fetcher, "    inherit pkgs;\n" + fields), expected)

    def test_dynamic_revision_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, "missing rev"):
            self.parse("import ./fetch-source.nix", 'owner = "HighCWu"; repo = "linux"; rev = version;')

    def test_unrecognized_fetcher_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "cannot find pinned GitHub src"):
            self.parse("import ./other.nix", 'owner = "HighCWu"; repo = "linux"; rev = "main";')


if __name__ == "__main__":
    unittest.main()
