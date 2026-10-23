#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fetch one pinned kernel test input without checking out all of Linux."""
import os
from pathlib import Path
import re
import sys
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # In particular, never forward an API Authorization header elsewhere.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        return response.read()


def download(revision, *, path="arch/wasm/kernel/semaphore.c", token=None, get=fetch):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("expected an exact 40-character Linux commit ID")
    if (not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*", path) or
            any(part in (".", "..") for part in path.split("/"))):
        raise ValueError("expected a repository-relative kernel source path")
    headers = {"User-Agent": "linux-wasm-builder-source-check"}
    try:
        data = get(f"https://raw.githubusercontent.com/HighCWu/linux/{revision}/{path}", headers)
        if not data:
            raise OSError("empty source response")
        return data
    except OSError:
        print("Raw pinned source unavailable; trying the same commit via GitHub API", file=sys.stderr)
    headers = {
        **headers,
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = get(f"https://api.github.com/repos/HighCWu/linux/contents/{path}?ref={revision}", headers)
    if not data:
        raise OSError("empty API source response")
    return data


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: fetch_pinned_semaphore_source.py COMMIT OUTPUT [SOURCE_PATH]")
    try:
        path = sys.argv[3] if len(sys.argv) == 4 else "arch/wasm/kernel/semaphore.c"
        data = download(sys.argv[1], path=path, token=os.environ.get("GH_TOKEN"))
        Path(sys.argv[2]).write_bytes(data)
    except (OSError, ValueError):
        # Do not expose credentials or fall back to a moving branch/local file.
        raise SystemExit("Unable to fetch the exact pinned kernel test source") from None


if __name__ == "__main__":
    main()
