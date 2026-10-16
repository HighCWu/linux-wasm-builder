// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const report = JSON.parse(readFileSync(process.argv[2], "utf8"));
assert.equal(report.stats.expected, 3, "storage and HTTP lifecycle tests must pass");
assert.equal(report.stats.skipped, 0, "missing OPFS support must not produce a green check");
assert.equal(report.stats.unexpected, 0, "lifecycle checks must not fail");
assert.equal(report.stats.flaky, 0, "lifecycle checks must pass without retries");
assert.deepEqual(report.errors, [], "browser suite must have no global errors");
console.log("Confirmed three executed storage/HTTP lifecycle tests, no skips or retries");
