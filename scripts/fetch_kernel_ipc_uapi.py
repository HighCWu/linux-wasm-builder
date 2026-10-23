#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fetch exact IPC UAPI and the native message-control dispatcher, not a full checkout."""
import os
import pathlib
import re
import sys

from fetch_pinned_semaphore_source import download_with_retry


FILES = {name: f"include/uapi/asm-generic/{name}"
         for name in ("ipcbuf.h", "msgbuf.h", "sembuf.h", "shmbuf.h")}
FILES.update({"ipc.h": "include/uapi/linux/ipc.h", "msg.h": "include/uapi/linux/msg.h", "msg.c": "ipc/msg.c"})


def fetch_all(revision, target, *, token=None, download=download_with_retry):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("expected an exact Linux revision")
    # Every input must succeed before replacing any previous fixture bytes.
    # The common downloader keeps both endpoints pinned to this commit,
    # bounds transient retries and never sends credentials to the raw host.
    contents = {name: download(revision, path=source, token=token) for name, source in FILES.items()}
    target = pathlib.Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in contents.items():
        (target / name).write_bytes(data)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: fetch_kernel_ipc_uapi.py FULL_LINUX_REVISION OUTPUT_DIRECTORY")
    try:
        fetch_all(sys.argv[1], sys.argv[2], token=os.environ.get("GH_TOKEN"))
    except (OSError, ValueError):
        raise SystemExit("Unable to fetch the exact pinned IPC test inputs") from None


if __name__ == "__main__":
    main()
