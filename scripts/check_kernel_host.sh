#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test_root=$(mktemp -d "${TMPDIR:-/tmp}/linux-wasm-kernel-host.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT
source_root="$repo_root/sources/distro"

# Isolate generated JS and package links from the developer's checkout. Only
# the small bytes library needs compilation; Node executes the kernel TS tests.
mkdir -p "$test_root/packages/bytes" "$test_root/packages/kernel/node_modules/@lowland"
cp "$source_root/tsconfig.base.json" "$test_root/tsconfig.base.json"
cp -R "$source_root/packages/bytes/src" "$test_root/packages/bytes/src"
cp "$source_root/packages/bytes/package.json" "$source_root/packages/bytes/tsconfig.json" \
  "$test_root/packages/bytes/"
cp -R "$source_root/packages/kernel/src" "$source_root/packages/kernel/test" \
  "$test_root/packages/kernel/"
cp "$source_root/packages/kernel/package.json" "$test_root/packages/kernel/package.json"
ln -s "$test_root/packages/bytes" "$test_root/packages/kernel/node_modules/@lowland/bytes"
"${KERNEL_HOST_TSC:-tsc}" -p "$test_root/packages/bytes/tsconfig.json"
node --test "$test_root"/packages/kernel/test/*.test.ts
