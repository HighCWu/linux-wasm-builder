// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("virtio-fs DESTROY waits for another queue and releases a late open handle", async ({
  page,
}) => {
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const { fileSystemDevice, FSError, close_virtio_device, virtio_imports } =
      await import("/filesystem-api.js");
    const results = [];
    for (const openFails of [false, true]) {
      const root = {},
        node = {},
        handle = {};
      const pending = Promise.withResolvers(),
        entered = Promise.withResolvers();
      const events = [];
      const device = fileSystemDevice(
        {
          root,
          lookup() {
            events.push("lookup");
            return node;
          },
          getattr() {
            return { mode: 0o100600, size: 0n };
          },
          async open() {
            events.push("open");
            entered.resolve();
            await pending.promise;
            if (openFails) throw new FSError("EACCES");
            events.push("opened");
            return handle;
          },
          release(actualNode, actualHandle) {
            if (actualNode !== node || actualHandle !== handle)
              throw new Error("wrong release target");
            events.push("release");
          },
          destroy() {
            events.push("destroy");
          },
        },
        { tag: "destroy" },
      );
      const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
      const bytes = new Uint8Array(memory.buffer),
        view = new DataView(memory.buffer);
      const complete = [Promise.withResolvers(), Promise.withResolvers()];
      const imports = virtio_imports({
        memory,
        devices: [device],
        trigger_irq(irq) {
          complete[irq - 1].resolve();
        },
        on_error(error) {
          for (const one of complete) one.reject(error);
        },
      });
      async function request(queue, opcode, id, body) {
        const descriptors = queue * 64,
          address = 512 + queue * 512,
          response = 2048 + queue * 1024;
        complete[queue] = Promise.withResolvers();
        bytes.fill(0, descriptors, descriptors + 64);
        bytes.fill(0, address, address + 256);
        bytes.fill(0, response, response + 512);
        view.setUint32(address, 40 + body.length, true);
        view.setUint32(address + 4, opcode, true);
        view.setBigUint64(address + 8, BigInt(queue + 1), true);
        view.setBigUint64(address + 16, id, true);
        bytes.set(body, address + 40);
        view.setBigUint64(descriptors, BigInt(address), true);
        view.setUint32(descriptors + 8, 40 + body.length, true);
        view.setUint16(descriptors + 14, 129, true);
        view.setBigUint64(descriptors + 16, BigInt(response), true);
        view.setUint32(descriptors + 24, 512, true);
        view.setUint16(descriptors + 30, 130, true);
        imports.enable_vring(0, queue, 4, descriptors, queue + 1);
        imports.notify(0, queue);
        await complete[queue].promise;
        imports.disable_vring(0, queue);
        return view.getInt32(response + 4, true);
      }
      const name = new TextEncoder().encode("file\0");
      try {
        await request(0, 1, 1n, name);
        const id = view.getBigUint64(2064, true);
        events.length = 0;
        const opening = request(0, 14, id, new Uint8Array(8));
        await entered.promise;
        let destroyed = false;
        const destroying = request(1, 38, 0n, new Uint8Array()).then((error) => {
          destroyed = true;
          return error;
        });
        await new Promise((resolve) => setTimeout(resolve, 0));
        const early = { destroyed, events: [...events] };
        pending.resolve();
        const errors = await Promise.all([opening, destroying]);
        const after = await request(0, 1, 1n, name);
        await close_virtio_device(device);
        results.push({ openFails, early, errors, after, events: [...events] });
      } finally {
        pending.resolve();
        await close_virtio_device(device);
      }
    }
    return results;
  });
  expect(results).toEqual(
    [false, true].map((openFails) => ({
      openFails,
      early: { destroyed: false, events: ["open"] },
      errors: [openFails ? -13 : 0, 0],
      after: -5,
      events: openFails ? ["open", "destroy"] : ["open", "opened", "release", "destroy"],
    })),
  );
});
