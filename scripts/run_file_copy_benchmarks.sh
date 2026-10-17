#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build artifacts may be cached; these three Node/Linux boots must not be.
set -euo pipefail

if [[ $# != 3 || ("$2" != 32 && "$2" != 64) ]]; then
  echo 'usage: run_file_copy_benchmarks.sh <assets> <32|64> <new-output-directory>' >&2
  exit 2
fi
assets=$(realpath "$1")
bits=$2
output=$3
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for file in initramfs.cpio disk.img kernel/dist/index.js runner/run-test.js; do
  test -f "$assets/$file"
done
# Refuse an existing directory, including results from a previous execution.
mkdir -- "$output"
node -e 'console.log(JSON.stringify({versions:process.versions,execArgv:process.execArgv,platform:process.platform,arch:process.arch},null,2))' \
  >"$output/runtime.json"
for trial in 1 2 3; do
  timeout --kill-after=5 300 node "$assets/runner/run-test.js" \
    --cpus 1 --snapshot-first-disk --readonly-disks \
    "$assets/kernel/dist/index.js" "$assets/initramfs.cpio" "$assets/disk.img" \
    2>&1 | tee "$output/boot-$trial.log"
  python3 -B "$script_dir/summarize_file_copy_benchmark.py" --bits "$bits" \
    <"$output/boot-$trial.log" >"$output/boot-$trial.md"
done
