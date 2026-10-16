// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("BrowserFS rejects unsafe I/O ranges without changing OPFS data", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-fs-range-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    try {
      const file = await directory.getFileHandle("data", { create: true });
      const seed = await file.createWritable();
      await seed.write("original");
      await seed.close();
      let reads = 0;
      let writes = 0;
      const fs = new BrowserFS({
        kind: "directory",
        getDirectoryHandle: (...args) => directory.getDirectoryHandle(...args),
        async getFileHandle(...args) {
          const handle = await directory.getFileHandle(...args);
          return {
            kind: "file",
            getFile() {
              reads++;
              return handle.getFile();
            },
            createWritable(options) {
              writes++;
              return handle.createWritable(options);
            },
          };
        },
      });
      const node = await fs.lookup(fs.root, "data");
      const handle = await fs.open(node, 0);
      const max = BigInt(Number.MAX_SAFE_INTEGER);
      const errors = [];
      for (const operation of [
        () => fs.read(node, handle, -1n, 1),
        () => fs.read(node, handle, 0n, -1),
        () => fs.read(node, handle, 0n, 0.5),
        () => fs.read(node, handle, max, 1),
        () => fs.write(node, handle, max, Uint8Array.of(42)),
        () => fs.write(node, handle, -1n, Uint8Array.of(42)),
      ]) {
        try {
          await operation();
          errors.push("accepted");
        } catch (error) {
          errors.push(error.errno);
        }
      }
      const beforeRead = { reads, writes };
      const valid = new TextDecoder().decode(await fs.read(node, handle, 1n, 3));
      const empty = (await fs.read(node, handle, 100n, 4)).byteLength;
      return { errors, beforeRead, valid, empty, contents: await (await file.getFile()).text() };
    } finally {
      await root.removeEntry(name, { recursive: true });
    }
  });
  expect(result).toEqual({
    errors: [22, 22, 22, 22, 22, 22],
    beforeRead: { reads: 0, writes: 0 },
    valid: "rig",
    empty: 0,
    contents: "original",
  });
});
