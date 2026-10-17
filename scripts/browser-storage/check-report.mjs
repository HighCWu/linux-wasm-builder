// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const lifecycleCases = Object.freeze([
  "invalid disk capacity preserves OPFS data and releases its lock",
  "flushes virtio writes through the real OPFS worker",
  "disk startup cancellation releases workers and preserves existing OPFS bytes",
  "cancels pending Fetch response reads on disconnect",
  "releases disconnected Fetch callbacks and cancels late responses",
  "forwards fragmented POST bodies through browser Request",
  "enforces upload budgets only when browser buffering is required",
  "cancels incomplete browser uploads without sending a response",
  "aborts failed BrowserFS mutations and preserves committed OPFS bytes",
  "BrowserFS synchronization waits for the real OPFS write commit",
  "BrowserFS rename preserves pending source writes and open handles",
  "BrowserFS rejects unsafe I/O ranges without changing OPFS data",
  "BrowserFS serializes append writes and honors current open flags",
  "BrowserFS serializes exclusive creates with namespace mutations",
  "BrowserFS rejects invalid timestamps before changing OPFS data or metadata",
  "UDP write failure releases the private network flow and pending read",
  "UDP channel close settles idle writers and pending readers",
  "IPv4 parser validates complete header checksums including options",
  "BrowserFS unlink waits for pending OPFS mutations and detaches old handles",
  "BrowserFS replacement waits for target OPFS mutations before publishing",
  "BrowserFS directory relocation coordinates descendant mutations and queries",
  "virtio-fs shutdown drains current work without publishing or dispatching queued requests",
  "virtio-fs failed CREATE releases unpublished handles and lookup references",
  "virtio-fs DESTROY waits for another queue and releases a late open handle",
]);

export function caseFilter() {
  const escaped = lifecycleCases.map((title) => title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  // Playwright matches the full title (project/file/suite/title), not just title.
  return `(?:${escaped.join("|")})$`;
}

export function checkReport(report) {
  const specs = [];
  function visit(suite) {
    specs.push(...(suite.specs ?? []));
    for (const child of suite.suites ?? []) visit(child);
  }
  for (const suite of report.suites) visit(suite);
  assert.deepEqual(
    specs.map((spec) => spec.title).sort(),
    [...lifecycleCases].sort(),
    "exact lifecycle cases must execute",
  );
  for (const spec of specs) {
    assert.equal(spec.tests.length, 1, "one browser result per case is required");
    const test = spec.tests[0];
    assert.equal(test.status, "expected");
    assert.equal(test.results.length, 1, "retries are not allowed");
    assert.equal(test.results[0].status, "passed");
  }
  assert.equal(
    report.stats.expected,
    lifecycleCases.length,
    "storage and network lifecycle tests must pass",
  );
  assert.equal(report.stats.skipped, 0, "missing OPFS support must not produce a green check");
  assert.equal(report.stats.unexpected, 0, "lifecycle checks must not fail");
  assert.equal(report.stats.flaky, 0, "lifecycle checks must pass without retries");
  assert.deepEqual(report.errors, [], "browser suite must have no global errors");
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  if (process.argv[2] === "--grep") {
    console.log(caseFilter());
  } else {
    checkReport(JSON.parse(readFileSync(process.argv[2], "utf8")));
    console.log(
      `Confirmed ${lifecycleCases.length} executed storage/network lifecycle tests, no skips or retries`,
    );
  }
}
