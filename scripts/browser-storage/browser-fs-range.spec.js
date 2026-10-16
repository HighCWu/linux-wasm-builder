// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("BrowserFS serializes append writes and honors current open flags", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-fs-append-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    try {
      const fs = new BrowserFS(directory);
      const { node, handle } = await fs.create(fs.root, "data", 0x402, {
        mode: 0o600,
        uid: 0,
        gid: 0,
      });
      const second = await fs.open(node, 0x402);
      const encode = (text) => new TextEncoder().encode(text);
      await fs.write(node, handle, 0n, encode("base"));
      const sizes = await Promise.all([
        fs.write(node, handle, 0n, encode("A")),
        fs.write(node, second, 0n, encode("B")),
      ]);
      const file = await directory.getFileHandle("data");
      const appended = await (await file.getFile()).text();
      await fs.write(node, handle, 0n, encode("X"), 2);
      const disabled = await (await file.getFile()).text();
      const positioned = await fs.open(node, 2);
      await fs.write(node, positioned, 0n, encode("C"), 0x402);
      await fs.write(node, positioned, 1n, encode("Z"), 2);
      return { sizes, appended, disabled, final: await (await file.getFile()).text() };
    } finally {
      await root.removeEntry(name, { recursive: true });
    }
  });
  expect(result).toEqual({
    sizes: [1, 1],
    appended: "baseAB",
    disabled: "XaseAB",
    final: "XZseABC",
  });
});

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
