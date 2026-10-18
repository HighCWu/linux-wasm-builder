#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

probe_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
probe_build=$(mktemp -d)
trap 'rm -f -- "$probe_build/probe.raw.wasm" "$probe_build/probe.wasm"; rmdir -- "$probe_build"' EXIT
: "${CLANG:=clang-22}"
: "${WASM_OPT:=wasm-opt}"

"$CLANG" --version
"$WASM_OPT" --version
for width in 32 64; do
  for optimization in 0 2; do
    "$CLANG" --target="wasm${width}-unknown-unknown" -O"$optimization" \
      -nostdlib -fno-builtin -matomics -mbulk-memory -Wall -Wextra -Werror \
      -Wl,--no-entry -Wl,--import-memory -Wl,--shared-memory \
      -Wl,--initial-memory=1048576 -Wl,--max-memory=1048576 \
      -Wl,--export=__stack_pointer \
      "$probe_root/probe.c" -o "$probe_build/probe.raw.wasm"
    "$WASM_OPT" "$probe_build/probe.raw.wasm" --enable-threads --enable-bulk-memory \
      --enable-mutable-globals --enable-sign-ext --enable-nontrapping-float-to-int \
      --enable-memory64 --asyncify \
      --pass-arg=asyncify-imports@continuation_probe_v1.checkpoint \
      --pass-arg=asyncify-asserts -o "$probe_build/probe.wasm"
    timeout 45s node "$probe_root/runner.mjs" "$probe_build/probe.wasm" "$width" "$optimization"
    # Untransformed programs must fail admission, not masquerade as fork support.
    node --input-type=module - "$probe_root/runner.mjs" "$probe_build/probe.raw.wasm" "$width" <<'JS'
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const { probe } = await import(pathToFileURL(process.argv[2]));
await assert.rejects(probe(readFileSync(process.argv[3]), { width: Number(process.argv[4]) }),
  /missing asyncify_start_unwind/);
JS
  done
done
