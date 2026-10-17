#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate one fresh target run and summarize warm paired file-copy batches."""
import argparse
import statistics
import sys


def summarize(lines, bits):
    if bits not in (32, 64):
        raise ValueError("expected target bits 32 or 64")
    rows = {}
    order = [
        (length, trial, mode)
        for length in (65536, 131072)
        for trial in range(1, 6)
        for mode in (("mmap", "pread") if trial % 2 else ("pread", "mmap"))
    ]
    completed = passed = False
    for line in lines:
        if "host-workload-only" in line or "::vm-test::fail" in line:
            raise ValueError("host-only or failed run is not target performance evidence")
        if "file mmap: warm paired copy benchmark completed; no speed threshold" in line:
            if completed:
                raise ValueError("duplicate completion marker")
            completed = True
        if "::vm-test::pass" in line:
            if not completed or passed:
                raise ValueError("misplaced or duplicate pass marker")
            passed = True
        _, marker, data = line.partition("file-copy-bench,")
        if not marker:
            continue
        if completed or passed:
            raise ValueError("data after completion")
        fields = data.strip().split(",")
        if len(fields) != 7:
            raise ValueError("expected seven benchmark fields")
        row_bits, mode, length, trial, iterations, elapsed, checksum = fields
        row_bits, length, trial, iterations, elapsed, checksum = map(
            int, (row_bits, length, trial, iterations, elapsed, checksum)
        )
        if row_bits != bits or mode not in ("pread", "mmap"):
            raise ValueError("wrong target bits or backend")
        if length not in (65536, 131072) or trial not in range(1, 6) or iterations != 64:
            raise ValueError("unexpected benchmark dimensions")
        if elapsed <= 0 or checksum != (length // 4096 * 11 + 230) * iterations:
            raise ValueError("invalid elapsed time or checksum")
        key = length, trial, mode
        if key in rows:
            raise ValueError("duplicate benchmark batch")
        if len(rows) >= len(order) or key != order[len(rows)]:
            raise ValueError("non-alternating or unpaired benchmark order")
        rows[key] = elapsed / iterations
    if len(rows) != 20 or not completed or not passed:
        raise ValueError("incomplete target run; require 20 batches, completion and pass")
    output = [
        f"Warm single-CPU wasm{bits} batches; allocation + read/copy + sparse consumption + release.",
        "",
        "| Bytes | pread median µs/op | mmap median µs/op | Median paired mmap/pread ratio |",
        "|---:|---:|---:|---:|",
    ]
    for length in (65536, 131072):
        pread = [rows[length, trial, "pread"] for trial in range(1, 6)]
        mmap = [rows[length, trial, "mmap"] for trial in range(1, 6)]
        ratio = statistics.median(m / p for m, p in zip(mmap, pread))
        output.append(
            f"| {length} | {statistics.median(pread) / 1000:.3f} | "
            f"{statistics.median(mmap) / 1000:.3f} | {ratio:.3f} |"
        )
    output += ["", "Not cold-cache, zero-copy, browser, RSS or whole-application performance evidence."]
    return "\n".join(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bits", type=int, choices=(32, 64), required=True)
    args = parser.parse_args()
    try:
        print(summarize(sys.stdin, args.bits))
    except ValueError as error:
        print(f"file-copy benchmark: {error}", file=sys.stderr)
        sys.exit(2)
