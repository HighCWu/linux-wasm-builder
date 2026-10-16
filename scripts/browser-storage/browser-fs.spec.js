// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("BrowserFS synchronization waits for the real OPFS write commit", async ({ page }) => {
  await page.goto("/");
  const outcomes = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-fs-sync-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    const outcomes = [];
    try {
      for (const operation of ["flush", "fsync"]) {
        const file = await directory.getFileHandle(operation, { create: true });
        const seed = await file.createWritable();
        await seed.write("before");
        await seed.close();
        const closing = Promise.withResolvers();
        const release = Promise.withResolvers();
        const fs = new BrowserFS({
          kind: "directory",
          getDirectoryHandle: (...args) => directory.getDirectoryHandle(...args),
          async getFileHandle() {
            return {
              kind: "file",
              async createWritable(options) {
                const stream = await file.createWritable(options);
                return {
                  seek: (offset) => stream.seek(offset),
                  write: (data) => stream.write(data),
                  abort: (reason) => stream.abort(reason),
                  async close() {
                    closing.resolve();
                    await release.promise;
                    await stream.close();
                  },
                };
              },
            };
          },
        });
        const node = await fs.lookup(fs.root, operation);
        const handle = await fs.open(node, 0);
        const writing = fs.write(node, handle, 0n, new TextEncoder().encode("after!"));
        await closing.promise;
        let synchronized = false;
        const syncing = (
          operation === "flush" ? fs.flush(node, handle) : fs.fsync(node, handle, false)
        ).then(() => {
          synchronized = true;
        });
        let early;
        let before;
        try {
          await new Promise((resolve) => setTimeout(resolve, 0));
          early = synchronized;
          before = await (await file.getFile()).text();
        } finally {
          release.resolve();
          await writing;
          await syncing;
        }
        outcomes.push({
          operation,
          early,
          before,
          synchronized,
          after: await (await file.getFile()).text(),
        });
      }
    } finally {
      await root.removeEntry(name, { recursive: true });
    }
    return outcomes;
  });
  expect(outcomes).toEqual(
    ["flush", "fsync"].map((operation) => ({
      operation,
      early: false,
      before: "before",
      synchronized: true,
      after: "after!",
    })),
  );
});

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
                if (fail && stage === "write")
                  throw new DOMException("injected quota", "QuotaExceededError");
              },
              async truncate(size) {
                await stream.truncate(size);
                if (fail && stage === "truncate")
                  throw new DOMException("injected quota", "QuotaExceededError");
              },
              async close() {
                committed++;
                await stream.close();
              },
              async abort(reason) {
                aborted++;
                await stream.abort(reason);
              },
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
          if (stage === "write")
            await fs.write(node, handle, 0n, new TextEncoder().encode("damaged!"));
          else await fs.setattr(node, { size: 2n });
        } catch (error) {
          errno = error.errno;
        }
        const preserved = await (await file.getFile()).text();
        const afterFailure = { aborted, committed };
        fail = false;
        await fs.write(node, handle, 0n, new TextEncoder().encode("original"));
        outcomes.push({
          stage,
          errno,
          preserved,
          afterFailure,
          retried: await (await file.getFile()).text(),
          committed,
        });
      }
    } finally {
      await root.removeEntry(name, { recursive: true });
    }
    return outcomes;
  });
  expect(outcomes).toHaveLength(2);
  for (const outcome of outcomes)
    expect(outcome).toEqual({
      stage: outcome.stage,
      errno: 28,
      preserved: "original",
      afterFailure: { aborted: 1, committed: 0 },
      retried: "original",
      committed: 1,
    });
});
