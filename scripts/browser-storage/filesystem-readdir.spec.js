// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("virtio-fs directory pages stop and close sync and async iterators", async ({ page }) => {
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const { fileSystemDevice, FSError, close_virtio_device, virtio_imports } =
      await import("/filesystem-api.js");
    const results = [];
    for (const asynchronous of [false, true]) {
      const root = {},
        child = {};
      let opened = 0,
        yielded = 0,
        closed = 0,
        fail = false;
      function* entries() {
        opened++;
        try {
          for (const name of ["a", "b", "c"]) {
            yielded++;
            yield { name, node: child };
          }
          throw new Error("traversed beyond the requested page");
        } finally {
          closed++;
        }
      }
      const device = fileSystemDevice(
        {
          root,
          lookup() {
            return undefined;
          },
          getattr(node) {
            if (fail && node === child) throw new FSError("EACCES");
            return { mode: node === root ? 0o040700 : 0o100600, size: 0n };
          },
          opendir() {
            return {};
          },
          readdir() {
            return asynchronous
              ? (async function* () {
                  yield* entries();
                })()
              : entries();
          },
        },
        { tag: "stream" },
      );
      const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
      const bytes = new Uint8Array(memory.buffer),
        view = new DataView(memory.buffer);
      let complete = Promise.withResolvers();
      const imports = virtio_imports({
        memory,
        devices: [device],
        trigger_irq() {
          complete.resolve();
        },
        on_error(error) {
          complete.reject(error);
        },
      });
      async function request(opcode, body) {
        complete = Promise.withResolvers();
        bytes.fill(0);
        view.setUint32(128, 40 + body.length, true);
        view.setUint32(132, opcode, true);
        view.setBigUint64(136, 1n, true);
        view.setBigUint64(144, 1n, true);
        bytes.set(body, 168);
        view.setBigUint64(0, 128n, true);
        view.setUint32(8, 40 + body.length, true);
        view.setUint16(14, 129, true);
        view.setBigUint64(16, 1024n, true);
        view.setUint32(24, 512, true);
        view.setUint16(30, 130, true);
        imports.enable_vring(0, 0, 4, 0, 1);
        imports.notify(0, 0);
        await complete.promise;
        imports.disable_vring(0, 0);
        return view.getInt32(1028, true);
      }
      try {
        const openError = await request(27, new Uint8Array(8));
        const fh = view.getBigUint64(1040, true);
        const pages = [];
        for (const [offset, size, failure] of [
          [0, 64, false],
          [2, 32, false],
          [3, 64, false],
          [2, 32, true],
        ]) {
          fail = failure;
          const body = new Uint8Array(40),
            input = new DataView(body.buffer);
          input.setBigUint64(0, fh, true);
          input.setBigUint64(8, BigInt(offset), true);
          input.setUint32(16, size, true);
          const error = await request(28, body);
          const entries = [];
          if (!error)
            for (let cursor = 1040; cursor < 1024 + view.getUint32(1024, true);) {
              const length = view.getUint32(cursor + 16, true);
              entries.push([
                new TextDecoder().decode(bytes.subarray(cursor + 24, cursor + 24 + length)),
                Number(view.getBigUint64(cursor + 8, true)),
              ]);
              cursor += (24 + length + 7) & ~7;
            }
          pages.push({ error, entries, opened, yielded, closed });
        }
        results.push({ openError, pages });
      } finally {
        await close_virtio_device(device);
      }
    }
    return results;
  });
  expect(results).toEqual(
    [false, true].map(() => ({
      openError: 0,
      pages: [
        {
          error: 0,
          entries: [
            [".", 1],
            ["..", 2],
          ],
          opened: 0,
          yielded: 0,
          closed: 0,
        },
        { error: 0, entries: [["a", 3]], opened: 1, yielded: 1, closed: 1 },
        {
          error: 0,
          entries: [
            ["b", 4],
            ["c", 5],
          ],
          opened: 2,
          yielded: 4,
          closed: 2,
        },
        { error: -13, entries: [], opened: 3, yielded: 5, closed: 3 },
      ],
    })),
  );
});
