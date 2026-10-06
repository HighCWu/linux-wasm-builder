#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare three alternating off/on fresh-boot trials from a CI artifact."""

from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

from summarize_mmap_benchmark import summarize


def load(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    summarize(lines)  # Reuse sample, timing and duplicate validation.
    rows = csv.DictReader(line for line in lines if not line.startswith("#"))
    cases = {}
    for row in rows:
        key = row["scenario"], int(row["resident"]), int(row["holes_percent"]), int(row["threads"])
        samples = cases.setdefault(key, {})
        samples[int(row["sample"])] = tuple(
            int(row[field]) for field in ("operations_per_kind", "mmap_ns", "munmap_ns", "elapsed_ns")
        )
    if len(cases) != 15 or sum(map(len, cases.values())) != 45:
        raise ValueError(f"{path}: expected 15 cases and 45 samples")
    return cases


def compare(directory: Path) -> str:
    trials = [
        {mode: load(directory / f"trial-{trial}-{mode}.csv") for mode in ("off", "on")}
        for trial in (1, 2, 3)
    ]
    reference = trials[0]["off"]
    for trial in trials:
        for cases in trial.values():
            if set(cases) != set(reference):
                raise ValueError("case dimensions differ between trials or modes")
            for key, samples in cases.items():
                if {s: value[0] for s, value in samples.items()} != {
                    s: value[0] for s, value in reference[key].items()
                }:
                    raise ValueError("operation counts differ between trials or modes")
    output = [
        "| Scenario | Mappings | Holes % | Threads | off mmap µs/op | on mmap µs/op | off/on ratio median [min–max] |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key in reference:
        scenario, mappings, holes, threads = key
        values = {mode: [] for mode in ("off", "on")}
        for trial in trials:
            for mode in values:
                samples = trial[mode][key].values()
                values[mode].append(
                    statistics.median(mmap_ns / ops / 1000 for ops, mmap_ns, _, _ in samples)
                    if reference[key][1][0] else 0
                )
        if not reference[key][1][0]:
            metrics = "— | — | —"
        else:
            if min(values["on"]) <= 0 or min(values["off"]) <= 0:
                raise ValueError("non-positive measured mmap latency cannot yield a ratio")
            ratios = [off / on for off, on in zip(values["off"], values["on"], strict=True)]
            metrics = (
                f"{statistics.median(values['off']):.3f} | {statistics.median(values['on']):.3f} | "
                f"{statistics.median(ratios):.2f} [{min(ratios):.2f}–{max(ratios):.2f}]"
            )
        output.append(f"| {scenario} | {mappings} | {holes} | {threads} | {metrics} |")
    return "\n".join(output)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: compare_mmap_benchmarks.py ARTIFACT_DIRECTORY")
        print(compare(Path(sys.argv[1])))
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"mmap comparison: {error}")
