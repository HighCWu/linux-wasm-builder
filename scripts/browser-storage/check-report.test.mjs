// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { caseFilter, checkReport, lifecycleCases } from "./check-report.mjs";

test("browser workflow stages every local spec, including newly added cases", () => {
  const workflow = readFileSync(
    new URL("../../.github/workflows/browser-storage.yml", import.meta.url),
    "utf8",
  );
  assert.match(workflow, /cp scripts\/browser-storage\/\*\.spec\.js "\$suite\/tests\/"/);
  assert.match(
    workflow,
    /case_filter=\$\(node "\$GITHUB_WORKSPACE\/scripts\/browser-storage\/check-report\.mjs" --grep\)/,
  );
  assert.match(workflow, /--grep "\$case_filter"/);
});

test("browser selection is derived from every required report case", () => {
  const filter = new RegExp(caseFilter());
  for (const title of lifecycleCases) {
    assert.ok(filter.test(`chromium tests/example.spec.js ${title}`), title);
    assert.equal(filter.test(`chromium tests/example.spec.js ${title} extra`), false);
  }
  assert.equal(filter.test("persists a virtio block device through an OPFS worker"), false);
});

function fixture() {
  return {
    stats: { expected: 25, skipped: 0, unexpected: 0, flaky: 0 },
    errors: [],
    suites: [
      {
        suites: [
          {
            specs: [
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
              "virtio-fs directory pages stop and close sync and async iterators",
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
test("accepts exactly the twenty-five successful lifecycle cases", () => {
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
