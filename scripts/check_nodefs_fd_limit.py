#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bound a separate Node process; never change the builder's descriptor limit."""

import resource
import subprocess
import sys


def limit():
    resource.setrlimit(resource.RLIMIT_NOFILE, (96, 96))


subprocess.run(["node", sys.argv[1]], preexec_fn=limit, check=True, timeout=30)
