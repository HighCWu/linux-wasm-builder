#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

"""Summarize mmap-bench CSV rows from raw output or GitHub Actions logs on stdin."""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable


def summarize(lines: Iterable[str]) -> str:
    groups: dict[tuple[str, int, int, int], dict[int, tuple[int, int, int, int]]] = defaultdict(dict)
    for line in lines:
        _, marker, row = line.partition("mmap-bench,")
        if not marker:
            continue
        fields = row.strip().split(",")
        if fields[0] == "scenario":
            continue
        if len(fields) != 9:
            raise ValueError("mmap-bench row must have nine fields after its prefix")
        scenario = fields[0]
        mappings, holes, threads, sample, operations, mmap_ns, munmap_ns, elapsed_ns = map(int, fields[1:])
        if scenario not in {"scale", "fragment", "concurrent"}:
            raise ValueError(f"unknown scenario: {scenario}")
        if mappings <= 0 or not 0 <= holes <= 100 or threads <= 0 or not 1 <= sample <= 3:
            raise ValueError("invalid benchmark dimensions")
        if min(operations, mmap_ns, munmap_ns) < 0 or elapsed_ns <= 0:
            raise ValueError("invalid benchmark counters")
        if operations == 0 and (scenario != "fragment" or holes != 0 or mmap_ns or munmap_ns):
            raise ValueError("only the zero-hole control may have no measured operations")
        key = scenario, mappings, holes, threads
        if sample in groups[key]:
            raise ValueError(f"duplicate sample {sample} for {key}")
        groups[key][sample] = operations, mmap_ns, munmap_ns, elapsed_ns

    if not groups:
        raise ValueError("no mmap-bench data rows found")
    output = [
        "| Scenario | Mappings | Holes % | Threads | mmap µs/op | munmap µs/op | Operations/s |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for (scenario, mappings, holes, threads), samples in groups.items():
        if set(samples) != {1, 2, 3}:
            raise ValueError(f"missing samples for {(scenario, mappings, holes, threads)}")
        values = list(samples.values())
        if len({value[0] for value in values}) != 1:
            raise ValueError("operation counts differ between samples")
        if values[0][0]:
            mmap_us = statistics.median(mmap_ns / operations / 1000 for operations, mmap_ns, _, _ in values)
            munmap_us = statistics.median(munmap_ns / operations / 1000 for operations, _, munmap_ns, _ in values)
            throughput = statistics.median(2 * operations * 1e9 / elapsed for operations, _, _, elapsed in values)
            metrics = f"{mmap_us:.3f} | {munmap_us:.3f} | {throughput:.0f}"
        else:
            metrics = "— | — | —"
        output.append(f"| {scenario} | {mappings} | {holes} | {threads} | {metrics} |")
    return "\n".join(output)


if __name__ == "__main__":
    try:
        print(summarize(sys.stdin))
    except ValueError as error:
        print(f"mmap benchmark: {error}", file=sys.stderr)
        sys.exit(2)
