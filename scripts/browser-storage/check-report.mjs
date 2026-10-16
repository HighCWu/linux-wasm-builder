// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const report = JSON.parse(readFileSync(process.argv[2], "utf8"));
assert.equal(report.stats.expected, 1, "exactly one storage recovery test must pass");
assert.equal(report.stats.skipped, 0, "missing OPFS support must not produce a green check");
assert.equal(report.stats.unexpected, 0, "storage recovery must not fail");
assert.equal(report.stats.flaky, 0, "storage recovery must pass without retries");
assert.deepEqual(report.errors, [], "browser suite must have no global errors");
console.log("Confirmed one executed storage recovery test, no skips or retries");
