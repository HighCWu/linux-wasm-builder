#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import unittest
import urllib.error
import urllib.request

from fetch_pinned_semaphore_source import NoRedirect, download, download_with_retry


REVISION = "ab" * 20


class FetchTest(unittest.TestCase):
    def test_raw_success_does_not_send_token_or_call_api(self):
        calls = []

        def get(url, headers):
            calls.append((url, headers))
            return b"exact source\n"

        self.assertEqual(download(REVISION, token="test-only-token", get=get), b"exact source\n")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0],
                         f"https://raw.githubusercontent.com/HighCWu/linux/{REVISION}/arch/wasm/kernel/semaphore.c")
        self.assertNotIn("Authorization", calls[0][1])

    def test_http_429_falls_back_to_same_commit_as_raw_bytes(self):
        calls = []

        def get(url, headers):
            calls.append((url, dict(headers)))
            if len(calls) == 1:
                raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)
            return b"same pinned function\n"

        self.assertEqual(download(REVISION, token="test-only-token", get=get), b"same pinned function\n")
        self.assertEqual(len(calls), 2)
        url, headers = calls[1]
        self.assertEqual(url,
                         f"https://api.github.com/repos/HighCWu/linux/contents/arch/wasm/kernel/semaphore.c?ref={REVISION}")
        self.assertEqual(headers["Accept"], "application/vnd.github.raw+json")
        self.assertEqual(headers["Authorization"], "Bearer test-only-token")
        self.assertNotIn("Authorization", calls[0][1])

    def test_uncredentialed_public_fallback_does_not_add_authorization(self):
        calls = []

        def get(url, headers):
            calls.append(headers)
            if len(calls) == 1:
                raise urllib.error.URLError("network unavailable")
            return b"source"

        self.assertEqual(download(REVISION, get=get), b"source")
        self.assertNotIn("Authorization", calls[1])

    def test_both_sources_failing_propagates_failure(self):
        calls = []

        def get(url, headers):
            calls.append(url)
            raise urllib.error.URLError("unavailable")

        with self.assertRaises(OSError):
            download(REVISION, get=get)
        self.assertEqual(len(calls), 2)

    def test_empty_responses_cannot_pass(self):
        with self.assertRaises(OSError):
            download(REVISION, get=lambda *_: b"")

    def test_moving_or_invalid_revision_never_downloads(self):
        def get(*_):
            self.fail("invalid pin must not trigger a download")

        for revision in ["main", "ab12345", "f" * 39, "f" * 41, "../main", "F" * 40]:
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                download(revision, get=get)

    def test_api_redirect_cannot_forward_credentials(self):
        request = urllib.request.Request("https://api.github.com/test",
                                         headers={"Authorization": "Bearer test-only-token"})
        self.assertIsNone(NoRedirect().redirect_request(
            request, None, 302, "redirect", {}, "https://other.invalid/"))

    def test_other_kernel_paths_keep_identical_commit_on_fallback(self):
        for path in ("arch/wasm/kernel/remote_vm.c", "kernel/futex/core.c", "fs/splice.c"):
            calls = []

            def get(url, headers):
                calls.append((url, dict(headers)))
                if len(calls) == 1:
                    raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)
                return b"pinned C source\n"

            self.assertEqual(download(REVISION, path=path, token="test-only-token", get=get), b"pinned C source\n")
            self.assertEqual(calls[0][0], f"https://raw.githubusercontent.com/HighCWu/linux/{REVISION}/{path}")
            self.assertEqual(calls[1][0], f"https://api.github.com/repos/HighCWu/linux/contents/{path}?ref={REVISION}")
            self.assertNotIn("Authorization", calls[0][1])
            self.assertEqual(calls[1][1]["Authorization"], "Bearer test-only-token")

    def test_invalid_paths_never_download(self):
        def get(*_):
            self.fail("invalid path must not trigger a download")

        for path in ("", "/etc/passwd", "../kernel/core.c", "kernel/../secret", "kernel/./core.c",
                     "kernel//core.c", "kernel/core.c?ref=main", "https://other.invalid/source", "kernel/core.c\n"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                download(REVISION, path=path, get=get)

    def test_retry_remains_pinned_and_never_authenticates_raw_host(self):
        calls, waits = [], []

        def get(url, headers):
            calls.append((url, dict(headers)))
            if len(calls) <= 2:
                raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)
            return b"exact source after retry"

        self.assertEqual(download_with_retry(REVISION, get=get, wait=waits.append, token="test-only-token"),
                         b"exact source after retry")
        self.assertEqual(waits, [5])
        self.assertEqual(calls[0][0], calls[2][0])
        self.assertNotIn("Authorization", calls[2][1])

    def test_retry_is_bounded_and_permanent_http_errors_fail_immediately(self):
        for code, attempts, expected_waits in ((429, 6, [5, 15]), (503, 6, [5, 15]), (404, 2, [])):
            calls, waits = [], []

            def get(url, headers):
                calls.append(url)
                raise urllib.error.HTTPError(url, code, "unavailable", {}, None)

            with self.subTest(code=code), self.assertRaises(OSError):
                download_with_retry(REVISION, get=get, wait=waits.append)
            self.assertEqual(len(calls), attempts)
            self.assertEqual(waits, expected_waits)


if __name__ == "__main__":
    unittest.main()
