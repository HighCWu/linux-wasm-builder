// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { checkReport } from "./check-report.mjs";

test("browser workflow stages every local spec, including newly added cases", () => {
  const workflow = readFileSync(
    new URL("../../.github/workflows/browser-storage.yml", import.meta.url),
    "utf8",
  );
  assert.match(workflow, /cp scripts\/browser-storage\/\*\.spec\.js "\$suite\/tests\/"/);
});

function fixture() {
  return {
    stats: { expected: 17, skipped: 0, unexpected: 0, flaky: 0 },
    errors: [],
    suites: [
      {
        suites: [
          {
            specs: [
              "invalid disk capacity preserves OPFS data and releases its lock",
              "flushes virtio writes through the real OPFS worker",
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
            ].map((title) => ({
              title,
              tests: [{ status: "expected", results: [{ status: "passed" }] }],
            })),
          },
        ],
      },
    ],
  };
}
test("accepts exactly the seventeen successful lifecycle cases", () => {
  checkReport(fixture());
});
for (const kind of ["wrong case", "duplicate", "skipped", "retry", "missing result"]) {
  test(`rejects ${kind} even with successful aggregate statistics`, () => {
    const report = fixture();
    const specs = report.suites[0].suites[0].specs;
    if (kind === "wrong case") specs[0].title = "unrelated test";
    if (kind === "duplicate") specs[0].title = specs[1].title;
    if (kind === "skipped") specs[0].tests[0].results[0].status = "skipped";
    if (kind === "retry") specs[0].tests[0].results.push({ status: "passed" });
    if (kind === "missing result") specs[0].tests = [];
    assert.throws(() => checkReport(report));
  });
}
