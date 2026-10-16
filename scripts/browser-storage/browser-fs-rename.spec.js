// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("BrowserFS rename preserves pending source writes and open handles", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-fs-rename-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    const source = await directory.getFileHandle("source", { create: true });
    const seed = await source.createWritable();
    await seed.write("before");
    await seed.close();
    const closing = Promise.withResolvers();
    const release = Promise.withResolvers();
    let snapshots = 0;
    const wrapped = {
      kind: "file",
      getFile() {
        snapshots++;
        return source.getFile();
      },
      async createWritable(options) {
        const stream = await source.createWritable(options);
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
    const fs = new BrowserFS({
      kind: "directory",
      getDirectoryHandle: (...args) => directory.getDirectoryHandle(...args),
      getFileHandle: (entry, options) =>
        entry === "source" ? Promise.resolve(wrapped) : directory.getFileHandle(entry, options),
      removeEntry: (...args) => directory.removeEntry(...args),
    });
    try {
      const node = await fs.lookup(fs.root, "source");
      const handle = await fs.open(node, 0);
      const writing = fs.write(node, handle, 0n, new TextEncoder().encode("after!"));
      await closing.promise;
      const moving = fs.rename(fs.root, "source", fs.root, "destination");
      let earlySnapshots;
      try {
        await new Promise((resolve) => setTimeout(resolve, 0));
        earlySnapshots = snapshots;
      } finally {
        release.resolve();
        await writing;
        await moving;
      }
      const destination = await directory.getFileHandle("destination");
      const copied = await (await destination.getFile()).text();
      await fs.write(node, handle, 0n, new TextEncoder().encode("latest"));
      const updated = await (await destination.getFile()).text();
      let sourceMissing = false;
      try {
        await directory.getFileHandle("source");
      } catch (error) {
        sourceMissing = error.name === "NotFoundError";
      }
      return { earlySnapshots, copied, updated, sourceMissing };
    } finally {
      release.resolve();
      await root.removeEntry(name, { recursive: true });
    }
  });
  expect(result).toEqual({
    earlySnapshots: 0,
    copied: "after!",
    updated: "latest",
    sourceMissing: true,
  });
});
