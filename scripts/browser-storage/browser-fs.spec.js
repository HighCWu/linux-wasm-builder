// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("aborts failed BrowserFS mutations and preserves committed OPFS bytes", async ({ page }) => {
  await page.goto("/");
  const outcomes = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-fs-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    const file = await directory.getFileHandle("data", { create: true });
    const seed = await file.createWritable();
    await seed.write("original");
    await seed.close();
    const outcomes = [];
    try {
      for (const stage of ["write", "truncate"]) {
        let fail = true;
        let aborted = 0;
        let committed = 0;
        const wrappedFile = {
          kind: "file",
          getFile: () => file.getFile(),
          async createWritable(options) {
            const stream = await file.createWritable(options);
            return {
              seek: (offset) => stream.seek(offset),
              async write(data) {
                await stream.write(data);
                if (fail && stage === "write") throw new DOMException("injected quota", "QuotaExceededError");
              },
              async truncate(size) {
                await stream.truncate(size);
                if (fail && stage === "truncate") throw new DOMException("injected quota", "QuotaExceededError");
              },
              async close() { committed++; await stream.close(); },
              async abort(reason) { aborted++; await stream.abort(reason); },
            };
          },
        };
        const fs = new BrowserFS({
          kind: "directory",
          getDirectoryHandle: (...args) => directory.getDirectoryHandle(...args),
          getFileHandle: async () => wrappedFile,
        });
        const node = await fs.lookup(fs.root, "data");
        const handle = await fs.open(node, 0);
        let errno;
        try {
          if (stage === "write") await fs.write(node, handle, 0n, new TextEncoder().encode("damaged!"));
          else await fs.setattr(node, { size: 2n });
        } catch (error) { errno = error.errno; }
        const preserved = await (await file.getFile()).text();
        const afterFailure = { aborted, committed };
        fail = false;
        await fs.write(node, handle, 0n, new TextEncoder().encode("original"));
        outcomes.push({ stage, errno, preserved, afterFailure,
          retried: await (await file.getFile()).text(), committed });
      }
    } finally {
      await root.removeEntry(name, { recursive: true });
    }
    return outcomes;
  });
  expect(outcomes).toHaveLength(2);
  for (const outcome of outcomes) expect(outcome).toEqual({
    stage: outcome.stage, errno: 28, preserved: "original",
    afterFailure: { aborted: 1, committed: 0 }, retried: "original", committed: 1,
  });
});
