// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import test from "node:test";
import { checkReport } from "./check-report.mjs";

function fixture() {
  return {
    stats: { expected: 7, skipped: 0, unexpected: 0, flaky: 0 },
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
test("accepts exactly the seven successful lifecycle cases", () => {
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
