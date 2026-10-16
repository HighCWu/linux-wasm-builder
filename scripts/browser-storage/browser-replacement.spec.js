// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("BrowserFS replacement waits for target OPFS mutations before publishing", async ({
  page,
}) => {
  await page.goto("/");
  const outcomes = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-replacement-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    const outcomes = [];
    try {
      for (const operation of ["write", "truncate"]) {
        for (const failed of [false, true]) {
          const sourceName = `source-${operation}-${failed}`;
          const targetName = `target-${operation}-${failed}`;
          for (const [entry, content] of [
            [sourceName, "source"],
            [targetName, "before"],
          ]) {
            const file = await directory.getFileHandle(entry, { create: true });
            const stream = await file.createWritable();
            await stream.write(content);
            await stream.close();
          }
          const closing = Promise.withResolvers();
          const release = Promise.withResolvers();
          let hold = true;
          const removals = [];
          const fs = new BrowserFS({
            kind: "directory",
            getDirectoryHandle: (...args) => directory.getDirectoryHandle(...args),
            async getFileHandle(entry, ...args) {
              const actual = await directory.getFileHandle(entry, ...args);
              if (entry !== targetName) return actual;
              return {
                kind: "file",
                getFile: () => actual.getFile(),
                async createWritable(options) {
                  const stream = await actual.createWritable(options);
                  if (!hold) return stream; // Copy uses the real WritableStream.
                  hold = false;
                  return {
                    seek: (offset) => stream.seek(offset),
                    write: (data) => stream.write(data),
                    truncate: (size) => stream.truncate(size),
                    abort: (reason) => stream.abort(reason),
                    async close() {
                      closing.resolve();
                      await release.promise;
                      if (failed) throw new DOMException("injected quota", "QuotaExceededError");
                      await stream.close();
                    },
                  };
                },
              };
            },
            removeEntry(entry, ...args) {
              removals.push(entry);
              return directory.removeEntry(entry, ...args);
            },
          });
          const source = await fs.lookup(fs.root, sourceName);
          const target = await fs.lookup(fs.root, targetName);
          const sourceHandle = await fs.open(source, 2);
          const targetHandle = await fs.open(target, 2);
          const mutation = (
            operation === "write"
              ? fs.write(target, targetHandle, 0n, new TextEncoder().encode("after!"))
              : fs.setattr(target, { size: 2n })
          ).then(
            () => "success",
            (error) => error.errno,
          );
          await closing.promise;
          const moving = fs.rename(fs.root, sourceName, fs.root, targetName).then(
            () => "success",
            (error) => error.errno,
          );
          let early;
          let before;
          try {
            await new Promise((resolve) => setTimeout(resolve, 0));
            early = removals.length;
            before = await (await (await directory.getFileHandle(targetName)).getFile()).text();
          } finally {
            release.resolve();
          }
          const mutationResult = await mutation;
          const moveResult = await moving;
          const published = await (
            await (await directory.getFileHandle(targetName)).getFile()
          ).text();
          const sameNode = (await fs.lookup(fs.root, targetName)) === source;
          const sourceGone = (await fs.lookup(fs.root, sourceName)) === undefined;
          const stale = await fs.write(target, targetHandle, 0n, Uint8Array.of(1)).then(
            () => "unexpected success",
            (error) => error.errno,
          );
          await fs.write(source, sourceHandle, 0n, new TextEncoder().encode("update"));
          const updated = await (
            await (await directory.getFileHandle(targetName)).getFile()
          ).text();
          outcomes.push({
            operation,
            failed,
            early,
            before,
            mutationResult,
            moveResult,
            published,
            sameNode,
            sourceGone,
            stale,
            updated,
            removals: removals.length,
          });
        }
      }
    } finally {
      await root.removeEntry(name, { recursive: true });
    }
    return outcomes;
  });
  expect(outcomes).toEqual(
    ["write", "truncate"].flatMap((operation) =>
      [false, true].map((failed) => ({
        operation,
        failed,
        early: 0,
        before: "before",
        mutationResult: failed ? 28 : "success",
        moveResult: "success",
        published: "source",
        sameNode: true,
        sourceGone: true,
        stale: 2,
        updated: "update",
        removals: 2,
      })),
    ),
  );
});
