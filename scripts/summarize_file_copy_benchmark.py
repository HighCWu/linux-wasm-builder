#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate one fresh target run and summarize warm paired file-copy batches."""
import argparse
import statistics
import sys


COMPONENT_ORDER = [("pread", "mmap", "anon-pread"), ("mmap", "anon-pread", "pread"),
                   ("anon-pread", "pread", "mmap"), ("anon-pread", "mmap", "pread"),
                   ("mmap", "pread", "anon-pread"), ("pread", "anon-pread", "mmap")]


def summarize(lines, bits, components=False):
    if bits not in (32, 64):
        raise ValueError("expected target bits 32 or 64")
    rows = {}
    trials = 6 if components else 5
    marker_name = "file-copy-components," if components else "file-copy-bench,"
    other_marker = "file-copy-bench," if components else "file-copy-components,"
    completion = ("file mmap: warm three-path diagnostic completed; no speed threshold"
                  if components else "file mmap: warm paired copy benchmark completed; no speed threshold")
    order = [
        (length, trial, mode)
        for length in (65536, 131072)
        for trial in range(1, trials + 1)
        for mode in (COMPONENT_ORDER[trial - 1] if components else
                     (("mmap", "pread") if trial % 2 else ("pread", "mmap")))
    ]
    completed = passed = False
    for line in lines:
        if "host-workload-only" in line or "::vm-test::fail" in line:
            raise ValueError("host-only or failed run is not target performance evidence")
        if other_marker in line or ("file mmap: warm" in line and "completed;" in line and completion not in line):
            raise ValueError("mixed benchmark profiles")
        if completion in line:
            if completed:
                raise ValueError("duplicate completion marker")
            completed = True
        if "::vm-test::pass" in line:
            if not completed or passed:
                raise ValueError("misplaced or duplicate pass marker")
            passed = True
        _, marker, data = line.partition(marker_name)
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
        if row_bits != bits or mode not in (("pread", "mmap", "anon-pread") if components else ("pread", "mmap")):
            raise ValueError("wrong target bits or backend")
        if length not in (65536, 131072) or trial not in range(1, trials + 1) or iterations != 64:
            raise ValueError("unexpected benchmark dimensions")
        if elapsed <= 0 or checksum != (length // 4096 * 11 + 230) * iterations:
            raise ValueError("invalid elapsed time or checksum")
        key = length, trial, mode
        if key in rows:
            raise ValueError("duplicate benchmark batch")
        if len(rows) >= len(order) or key != order[len(rows)]:
            raise ValueError("non-alternating or unpaired benchmark order")
        rows[key] = elapsed / iterations
    if len(rows) != len(order) or not completed or not passed:
        raise ValueError(f"incomplete target run; require {len(order)} batches, completion and pass")
    if components:
        output = [
            f"Warm single-CPU wasm{bits} three-path diagnostic; allocation + read/copy + sparse consumption + release.",
            "",
            "| Bytes | pread µs/op | anon-pread µs/op | mmap µs/op | Paired anon/pread | Paired mmap/anon | Paired mmap/pread |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for length in (65536, 131072):
            values = {mode: [rows[length, trial, mode] for trial in range(1, trials + 1)]
                      for mode in ("pread", "anon-pread", "mmap")}
            medians = [statistics.median(values[mode]) / 1000 for mode in ("pread", "anon-pread", "mmap")]
            ratios = [statistics.median(a / b for a, b in zip(values[numerator], values[denominator]))
                      for numerator, denominator in (("anon-pread", "pread"), ("mmap", "anon-pread"), ("mmap", "pread"))]
            output.append(f"| {length} | " + " | ".join(f"{value:.3f}" for value in medians + ratios) + " |")
        output += ["", "Ratios compare complete paths, not additive allocator, memset, bridge or kernel timings.",
                   "Not cold-cache, zero-copy, browser, RSS or whole-application performance evidence."]
        return "\n".join(output)
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
    parser.add_argument("--components", action="store_true", help="validate the separate three-path diagnostic")
    args = parser.parse_args()
    try:
        print(summarize(sys.stdin, args.bits, args.components))
    except ValueError as error:
        print(f"file-copy benchmark: {error}", file=sys.stderr)
        sys.exit(2)
