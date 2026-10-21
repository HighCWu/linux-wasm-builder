#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fetch exact IPC UAPI and the native message-control dispatcher, not a full checkout."""
import base64
import json
import pathlib
import re
import subprocess
import sys

if len(sys.argv) != 3 or not re.fullmatch(r"[0-9a-f]{40}", sys.argv[1]):
    raise SystemExit("usage: fetch_kernel_ipc_uapi.py FULL_LINUX_REVISION OUTPUT_DIRECTORY")
target = pathlib.Path(sys.argv[2])
target.mkdir(parents=True, exist_ok=True)
files = {name: f"include/uapi/asm-generic/{name}"
         for name in ("ipcbuf.h", "msgbuf.h", "sembuf.h", "shmbuf.h")}
files.update({"ipc.h": "include/uapi/linux/ipc.h", "msg.h": "include/uapi/linux/msg.h", "msg.c": "ipc/msg.c"})
for name, source in files.items():
    metadata = subprocess.check_output([
        "gh", "api", f"repos/HighCWu/linux/contents/{source}?ref={sys.argv[1]}"
    ], text=True)
    (target / name).write_bytes(base64.b64decode(json.loads(metadata)["content"]))
