// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("BrowserFS directory relocation coordinates descendant mutations and queries", async ({
  page,
}) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-directory-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    const sourceDirectory = await directory.getDirectoryHandle("source", { create: true });
    for (const [parent, entry, content] of [
      [sourceDirectory, "known", "before"],
      [sourceDirectory, "late", "late"],
      [directory, "other", "xxxx"],
    ]) {
      const file = await parent.getFileHandle(entry, { create: true });
      const stream = await file.createWritable();
      await stream.write(content);
      await stream.close();
    }
    const closing = Promise.withResolvers();
    const releaseWrite = Promise.withResolvers();
    const copying = Promise.withResolvers();
    const releaseCopy = Promise.withResolvers();
    let holdWrite = true;
    let holdCopy = true;
    let copyReads = 0;
    const sourceWrapper = {
      kind: "directory",
      getDirectoryHandle: (...args) => sourceDirectory.getDirectoryHandle(...args),
      async getFileHandle(entry, ...args) {
        const actual = await sourceDirectory.getFileHandle(entry, ...args);
        if (entry !== "known") return actual;
        return {
          kind: "file",
          async getFile() {
            if (holdCopy) {
              holdCopy = false;
              copyReads++;
              copying.resolve();
              await releaseCopy.promise;
            }
            return actual.getFile();
          },
          async createWritable(options) {
            const stream = await actual.createWritable(options);
            if (!holdWrite) return stream;
            holdWrite = false;
            return {
              seek: (offset) => stream.seek(offset),
              write: (data) => stream.write(data),
              abort: (reason) => stream.abort(reason),
              async close() {
                closing.resolve();
                await releaseWrite.promise;
                await stream.close();
              },
            };
          },
        };
      },
      async *entries() {
        for await (const [entry, handle] of sourceDirectory.entries()) {
          yield [entry, handle.kind === "file" ? await sourceWrapper.getFileHandle(entry) : handle];
        }
      },
    };
    try {
      const fs = new BrowserFS({
        kind: "directory",
        async getDirectoryHandle(entry, ...args) {
          const actual = await directory.getDirectoryHandle(entry, ...args);
          return entry === "source" ? sourceWrapper : actual;
        },
        getFileHandle: (...args) => directory.getFileHandle(...args),
        removeEntry: (...args) => directory.removeEntry(...args),
      });
      const source = await fs.lookup(fs.root, "source");
      const known = await fs.lookup(source, "known");
      const handle = await fs.open(known, 2);
      const other = await fs.lookup(fs.root, "other");
      const otherHandle = await fs.open(other, 2);
      const writing = fs.write(known, handle, 0n, new TextEncoder().encode("after!"));
      await closing.promise;
      const moving = fs.rename(fs.root, "source", fs.root, "destination");
      await new Promise((resolve) => setTimeout(resolve, 0));
      const copiedEarly = copyReads;
      releaseWrite.resolve();
      await writing;
      await copying.promise;
      let lookedUp = false;
      let listed = false;
      let rewritten = false;
      let destinationSeen = false;
      const lookup = fs.lookup(source, "late").then((node) => {
        lookedUp = true;
        return node;
      });
      const listing = fs.readdir(source, await fs.opendir(source)).then((entries) => {
        listed = true;
        return entries;
      });
      const rewrite = fs.write(known, handle, 0n, new TextEncoder().encode("latest")).then(() => {
        rewritten = true;
      });
      const destination = fs.lookup(fs.root, "destination").then((node) => {
        destinationSeen = true;
        return node;
      });
      await fs.write(other, otherHandle, 0n, new TextEncoder().encode("free"));
      const early = { lookedUp, listed, rewritten, destinationSeen };
      releaseCopy.resolve();
      await moving;
      const late = await lookup;
      const entries = await listing;
      await rewrite;
      await fs.write(late, await fs.open(late, 2), 0n, new TextEncoder().encode("late updated"));
      const target = await directory.getDirectoryHandle("destination");
      const text = async (parent, entry) =>
        (await (await parent.getFileHandle(entry)).getFile()).text();
      return {
        copiedEarly,
        early,
        sameNode: (await destination) === source,
        entries: entries.map((entry) => entry.name).sort(),
        known: await text(target, "known"),
        late: await text(target, "late"),
        other: await text(directory, "other"),
        sourceGone: (await fs.lookup(fs.root, "source")) === undefined,
      };
    } finally {
      releaseWrite.resolve();
      releaseCopy.resolve();
      await root.removeEntry(name, { recursive: true });
    }
  });
  expect(result).toEqual({
    copiedEarly: 0,
    early: { lookedUp: false, listed: false, rewritten: false, destinationSeen: false },
    sameNode: true,
    entries: ["known", "late"],
    known: "latest",
    late: "late updated",
    other: "free",
    sourceGone: true,
  });
});
