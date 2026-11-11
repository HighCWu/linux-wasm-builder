#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: check-llvm-no-undefined.sh --clang PATH --ld PATH --node PATH
EOF
}

clang_path=
ld_path=
node_path=
while (($#)); do
  case "$1" in
    --clang)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      clang_path=$2
      shift 2
      ;;
    --ld)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      ld_path=$2
      shift 2
      ;;
    --node)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      node_path=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unexpected argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

resolve_tool() {
  local requested=$1
  local label=$2
  local resolved
  if resolved=$(command -v -- "$requested" 2>/dev/null); then
    printf '%s\n' "$resolved"
  elif [[ -x $requested ]]; then
    printf '%s\n' "$requested"
  else
    printf '%s executable not found: %s\n' "$label" "$requested" >&2
    exit 2
  fi
}

[[ -n $clang_path && -n $ld_path && -n $node_path ]] || { usage >&2; exit 2; }
clang_path=$(resolve_tool "$clang_path" Clang)
ld_path=$(resolve_tool "$ld_path" wasm-ld)
node_path=$(resolve_tool "$node_path" Node)

ld_help=$("$ld_path" --help 2>&1 || true)
if ! grep -Fq -- '--no-undefined' <<<"$ld_help"; then
  printf 'candidate wasm-ld does not advertise --no-undefined: %s\n' "$ld_path" >&2
  exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/llvm-no-undefined.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT

cat >"$work_dir/resolved.c" <<'EOF'
int resolved(void) { return 42; }
EOF

cat >"$work_dir/undefined.c" <<'EOF'
extern int undefined_function(void);
int entry(void) { return undefined_function(); }
EOF

cat >"$work_dir/explicit-import.c" <<'EOF'
extern int host_value(void)
    __attribute__((import_module("host_api"), import_name("provided_value")));
int explicit_entry(void) { return host_value(); }
EOF

cat >"$work_dir/run.mjs" <<'EOF'
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const [modulePath, mode] = process.argv.slice(2);
let imports = {};
switch (mode) {
  case 'resolved':
    break;
  case 'allow':
  case 'legacy-allow':
    imports = {env: {undefined_function: () => 37}};
    break;
  case 'explicit':
    imports = {host_api: {provided_value: () => 42}};
    break;
  default:
    throw new Error(`unknown test mode: ${mode}`);
}

const {instance} = await WebAssembly.instantiate(readFileSync(modulePath), imports);
const value = mode === 'resolved'
  ? instance.exports.resolved()
  : mode === 'explicit'
    ? instance.exports.explicit_entry()
    : instance.exports.entry();
assert.equal(value, mode === 'allow' || mode === 'legacy-allow' ? 37 : 42);
EOF

expect_undefined_failure() {
  local label=$1
  shift
  local log_file="$work_dir/${label}.log"
  if "$ld_path" "$@" >"$log_file" 2>&1; then
    printf '%s unexpectedly linked an unresolved function\n' "$label" >&2
    exit 1
  fi
  if ! grep -Fq 'undefined symbol: undefined_function' "$log_file"; then
    printf '%s failed without the expected undefined-symbol diagnostic:\n' "$label" >&2
    cat "$log_file" >&2
    exit 1
  fi
  printf '[wasm%s] %s: strict undefined rejection and diagnostic pass\n' "$bits" "$label"
}

for bits in 32 64; do
  target="wasm${bits}-unknown-unknown"
  wasm_flags=()
  if [[ $bits == 64 ]]; then
    wasm_flags=(-mwasm64)
  fi

  for source in resolved undefined explicit-import; do
    "$clang_path" "--target=$target" -O0 -nostdlib -fno-stack-protector \
      -c "$work_dir/$source.c" -o "$work_dir/$source.wasm${bits}.o"
  done
  printf '[wasm%s] C inputs compiled\n' "$bits"

  "$ld_path" "${wasm_flags[@]}" --no-entry --no-undefined \
    --export=resolved "$work_dir/resolved.wasm${bits}.o" \
    -o "$work_dir/resolved.wasm${bits}.wasm"
  "$node_path" "$work_dir/run.mjs" "$work_dir/resolved.wasm${bits}.wasm" resolved
  printf '[wasm%s] strict resolved link and Node execution pass\n' "$bits"

  expect_undefined_failure "strict-undefined-wasm${bits}" \
    "${wasm_flags[@]}" --no-entry --no-undefined --export=entry \
    "$work_dir/undefined.wasm${bits}.o" -o "$work_dir/strict.wasm${bits}.wasm"

  expect_undefined_failure "allow-then-strict-wasm${bits}" \
    "${wasm_flags[@]}" --no-entry --allow-undefined --no-undefined \
    --export=entry "$work_dir/undefined.wasm${bits}.o" \
    -o "$work_dir/allow-then-strict.wasm${bits}.wasm"

  expect_undefined_failure "strict-allow-then-report-wasm${bits}" \
    "${wasm_flags[@]}" --no-entry --no-undefined --allow-undefined \
    --unresolved-symbols=report-all --export=entry \
    "$work_dir/undefined.wasm${bits}.o" \
    -o "$work_dir/strict-allow-then-report.wasm${bits}.wasm"

  "$ld_path" "${wasm_flags[@]}" --no-entry --no-undefined --allow-undefined \
    --export=entry "$work_dir/undefined.wasm${bits}.o" \
    -o "$work_dir/strict-then-allow.wasm${bits}.wasm"
  "$node_path" "$work_dir/run.mjs" \
    "$work_dir/strict-then-allow.wasm${bits}.wasm" allow
  printf '[wasm%s] strict-then-allow import and Node execution pass\n' "$bits"

  "$ld_path" "${wasm_flags[@]}" --no-entry --allow-undefined \
    --unresolved-symbols=report-all --export=entry \
    "$work_dir/undefined.wasm${bits}.o" \
    -o "$work_dir/legacy-allow.wasm${bits}.wasm"
  "$node_path" "$work_dir/run.mjs" \
    "$work_dir/legacy-allow.wasm${bits}.wasm" legacy-allow
  printf '[wasm%s] legacy allow-undefined plus report-all pass\n' "$bits"

  "$ld_path" "${wasm_flags[@]}" --no-entry --no-undefined \
    --export=explicit_entry "$work_dir/explicit-import.wasm${bits}.o" \
    -o "$work_dir/explicit-import.wasm${bits}.wasm"
  "$node_path" "$work_dir/run.mjs" \
    "$work_dir/explicit-import.wasm${bits}.wasm" explicit
  printf '[wasm%s] explicit import metadata and Node execution pass\n' "$bits"
done

printf 'Candidate wasm-ld strict unresolved-symbol checks passed for wasm32 and wasm64.\n'
