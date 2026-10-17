// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("virtio-fs failed CREATE releases unpublished handles and lookup references", async ({
  page,
}) => {
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const { fileSystemDevice, FSError, close_virtio_device, virtio_imports } =
      await import("/filesystem-api.js");
    const results = [];
    for (const releaseFails of [false, true]) {
      const root = {},
        node = {},
        handle = {};
      let fail = true,
        exists = false,
        releases = 0;
      const device = fileSystemDevice(
        {
          root,
          lookup() {
            return exists ? node : undefined;
          },
          getattr() {
            if (fail) throw new FSError("EACCES");
            return { mode: 0o100600, size: 0n };
          },
          create() {
            exists = true;
            return { node, handle };
          },
          flush() {},
          fsync() {},
          release(actualNode, actualHandle) {
            if (actualNode !== node || actualHandle !== handle)
              throw new Error("wrong cleanup target");
            releases++;
            if (releaseFails) throw new FSError("EIO");
          },
        },
        { tag: "create-errors" },
      );
      const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
      const bytes = new Uint8Array(memory.buffer),
        view = new DataView(memory.buffer);
      let completed = Promise.withResolvers();
      const imports = virtio_imports({
        memory,
        devices: [device],
        trigger_irq() {
          completed.resolve();
        },
        on_error(error) {
          completed.reject(error);
        },
      });
      async function request(opcode, id, body) {
        completed = Promise.withResolvers();
        bytes.fill(0);
        view.setUint32(128, 40 + body.length, true);
        view.setUint32(132, opcode, true);
        view.setBigUint64(136, 1n, true);
        view.setBigUint64(144, id, true);
        bytes.set(body, 168);
        view.setBigUint64(0, 128n, true);
        view.setUint32(8, 40 + body.length, true);
        view.setUint16(14, 129, true);
        view.setBigUint64(16, 1024n, true);
        view.setUint32(24, 512, true);
        view.setUint16(30, 130, true);
        imports.enable_vring(0, 0, 4, 0, 1);
        imports.notify(0, 0);
        await completed.promise;
        imports.disable_vring(0, 0);
        return view.getInt32(1028, true);
      }
      const name = new TextEncoder().encode("file\0");
      const create = new Uint8Array(16 + name.length);
      create.set(name, 16);
      try {
        const failed = await request(35, 1n, create);
        const immediateReleases = releases;
        fail = false;
        const absent = await request(3, 2n, new Uint8Array(16));
        const found = await request(1, 1n, name);
        const inode = Number(view.getBigUint64(1040, true));
        const forget = new Uint8Array(8);
        new DataView(forget.buffer).setBigUint64(0, 1n, true);
        await request(2, 2n, forget);
        const collected = await request(3, 2n, new Uint8Array(16));
        results.push({
          releaseFails,
          failed,
          immediateReleases,
          absent,
          found,
          inode,
          collected,
          exists,
        });
      } finally {
        await close_virtio_device(device);
      }
      results.at(-1).finalReleases = releases;
    }
    return results;
  });
  expect(results).toEqual(
    [false, true].map((releaseFails) => ({
      releaseFails,
      failed: -13,
      immediateReleases: 1,
      absent: -2,
      found: 0,
      inode: 2,
      collected: -2,
      exists: true,
      finalReleases: 1,
    })),
  );
});

test("virtio-fs shutdown drains current work without publishing or dispatching queued requests", async ({
  page,
}) => {
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const { fileSystemDevice, close_virtio_device, virtio_imports } =
      await import("/filesystem-api.js");
    const outcomes = [];
    for (const reject of [false, true]) {
      const events = [];
      const entered = Promise.withResolvers();
      const pending = Promise.withResolvers();
      const root = {};
      const device = fileSystemDevice(
        {
          root,
          async lookup() {
            events.push("lookup");
            entered.resolve();
            await pending.promise;
            return {};
          },
          getattr() {
            return { mode: 0o100600, size: 0n };
          },
          stop() {
            events.push("stop");
          },
          destroy() {
            events.push("destroy");
          },
        },
        { tag: "shutdown" },
      );
      const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
      const bytes = new Uint8Array(memory.buffer);
      const view = new DataView(memory.buffer);
      let interrupts = 0;
      const errors = [];
      const imports = virtio_imports({
        memory,
        devices: [device],
        trigger_irq() {
          interrupts++;
        },
        on_error(error) {
          errors.push(String(error));
        },
      });
      for (let slot = 0; slot < 2; slot++) {
        const address = 128 + slot * 128;
        const body = new TextEncoder().encode(`file${slot}\0`);
        view.setUint32(address, 40 + body.length, true);
        view.setUint32(address + 4, 1, true);
        view.setBigUint64(address + 8, BigInt(slot + 1), true);
        view.setBigUint64(address + 16, 1n, true);
        bytes.set(body, address + 40);
        const descriptor = slot * 32;
        view.setBigUint64(descriptor, BigInt(address), true);
        view.setUint32(descriptor + 8, 40 + body.length, true);
        view.setUint16(descriptor + 14, 129, true);
        view.setBigUint64(descriptor + 16, BigInt(1024 + slot * 1024), true);
        view.setUint32(descriptor + 24, 512, true);
        view.setUint16(descriptor + 30, 130, true);
      }
      imports.enable_vring(0, 0, 8, 0, 1);
      imports.notify(0, 0);
      await entered.promise;
      let closed = false;
      const closing = close_virtio_device(device).then(() => {
        closed = true;
      });
      await Promise.resolve();
      const early = { closed, events: [...events] };
      const snapshot = bytes.slice();
      if (reject) pending.reject(new Error("cancelled backend"));
      else pending.resolve();
      await closing;
      await close_virtio_device(device);
      outcomes.push({
        reject,
        early,
        events,
        interrupts,
        errors,
        unchanged: bytes.every((value, index) => value === snapshot[index]),
        closed,
      });
    }
    return outcomes;
  });
  expect(results).toEqual(
    [false, true].map((reject) => ({
      reject,
      early: { closed: false, events: ["lookup", "stop"] },
      events: ["lookup", "stop", "destroy"],
      interrupts: 0,
      errors: [],
      unchanged: true,
      closed: true,
    })),
  );
});
