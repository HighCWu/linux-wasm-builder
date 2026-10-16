// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("BrowserFS unlink waits for pending OPFS mutations and detaches old handles", async ({
  page,
}) => {
  await page.goto("/");
  const outcomes = await page.evaluate(async () => {
    const { BrowserFS } = await import("/browser-fs.js");
    const root = await navigator.storage.getDirectory();
    const name = `browser-unlink-${crypto.randomUUID()}`;
    const directory = await root.getDirectoryHandle(name, { create: true });
    const outcomes = [];
    try {
      for (const operation of ["write", "truncate"]) {
        for (const failed of [false, true]) {
          const fileName = `${operation}-${failed}`;
          const file = await directory.getFileHandle(fileName, { create: true });
          const seed = await file.createWritable();
          await seed.write("before");
          await seed.close();
          const closing = Promise.withResolvers();
          const release = Promise.withResolvers();
          let streams = 0;
          let removals = 0;
          const fs = new BrowserFS({
            kind: "directory",
            getDirectoryHandle: (...args) => directory.getDirectoryHandle(...args),
            async getFileHandle(...args) {
              const actual = await directory.getFileHandle(...args);
              return {
                kind: "file",
                getFile: () => actual.getFile(),
                async createWritable(options) {
                  const first = ++streams === 1;
                  const stream = await actual.createWritable(options);
                  return {
                    seek: (offset) => stream.seek(offset),
                    write: (data) => stream.write(data),
                    truncate: (size) => stream.truncate(size),
                    abort: (reason) => stream.abort(reason),
                    async close() {
                      if (first) {
                        closing.resolve();
                        await release.promise;
                        if (failed) throw new DOMException("injected quota", "QuotaExceededError");
                      }
                      await stream.close();
                    },
                  };
                },
              };
            },
            removeEntry(...args) {
              removals++;
              return directory.removeEntry(...args);
            },
          });
          const node = await fs.lookup(fs.root, fileName);
          const handle = await fs.open(node, 2);
          const mutation = (
            operation === "write"
              ? fs.write(node, handle, 0n, new TextEncoder().encode("after!"))
              : fs.setattr(node, { size: 2n })
          ).then(
            () => "success",
            (error) => error.errno,
          );
          await closing.promise;
          const deleting = fs.unlink(fs.root, fileName).then(
            () => "success",
            (error) => error.errno,
          );
          let early;
          let before;
          try {
            await new Promise((resolve) => setTimeout(resolve, 0));
            early = removals;
            before = await (await file.getFile()).text();
          } finally {
            release.resolve();
          }
          const mutationResult = await mutation;
          const deletionResult = await deleting;
          const replacement = await fs.create(fs.root, fileName, 0xc2, {
            mode: 0o600,
            uid: 0,
            gid: 0,
          });
          const stale = await fs.write(node, handle, 0n, Uint8Array.of(1)).then(
            () => "unexpected success",
            (error) => error.errno,
          );
          await fs.write(
            replacement.node,
            replacement.handle,
            0n,
            new TextEncoder().encode("replacement"),
          );
          outcomes.push({
            operation,
            failed,
            early,
            before,
            mutationResult,
            deletionResult,
            removals,
            differentNode: replacement.node !== node,
            stale,
            content: await (
              await directory.getFileHandle(fileName)
            )
              .getFile()
              .then((value) => value.text()),
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
        deletionResult: "success",
        removals: 1,
        differentNode: true,
        stale: 2,
        content: "replacement",
      })),
    ),
  );
});
