// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("disk startup cancellation releases workers and preserves existing OPFS bytes", async ({
  page,
}) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { openDiskWorker } = await import("/opfs-device.js");
    const { workerDevice } = await import("/network-api.js");
    const directory = await navigator.storage.getDirectory();
    const name = `disk-startup-${crypto.randomUUID()}.img`;
    const handle = await directory.getFileHandle(name, { create: true });
    const file = await handle.createWritable();
    await file.write(new Uint8Array(512).fill(0x5a));
    await file.close();
    const workers = [];
    let blob;
    function owned(url = "/opfs-disk-worker.js") {
      const worker = new Worker(url, { type: "module" });
      const state = { worker, terminated: 0, configured: 0 };
      const terminate = worker.terminate.bind(worker);
      const post = worker.postMessage.bind(worker);
      worker.terminate = () => {
        state.terminated++;
        terminate();
      };
      worker.postMessage = (...args) => {
        state.configured++;
        return post(...args);
      };
      workers.push(state);
      return state;
    }
    async function rejected(pending, reason) {
      try {
        await pending;
      } catch (error) {
        if (reason && error !== reason) throw new Error("abort reason changed");
        return error.name;
      }
      throw new Error("startup unexpectedly succeeded");
    }
    async function reopen() {
      for (let attempt = 0; ; attempt++) {
        try {
          const writable = await handle.createWritable({ keepExistingData: true });
          await writable.close();
          return;
        } catch (error) {
          if (error.name !== "NoModificationAllowedError" || attempt === 7) throw error;
          await new Promise((resolve) => setTimeout(resolve, 10 * 2 ** attempt));
        }
      }
    }
    try {
      const before = owned();
      const controller = new AbortController();
      const reason = new Error("cancelled disk startup");
      controller.abort(reason);
      await rejected(
        openDiskWorker(before.worker, { handle }, workerDevice, { signal: controller.signal }),
        reason,
      );
      if (before.configured !== 0 || before.terminated !== 1)
        throw new Error("pre-abort leaked worker or sent configuration");

      const during = owned();
      const cancellation = new AbortController();
      const pending = openDiskWorker(during.worker, { handle }, workerDevice, {
        signal: cancellation.signal,
      });
      cancellation.abort(reason);
      await rejected(pending, reason);
      if (during.terminated !== 1) throw new Error("pending cancellation leaked worker");
      await reopen();

      const clone = owned();
      const cloneError = await rejected(
        openDiskWorker(clone.worker, { handle, unsupported: () => {} }, workerDevice),
      );
      if (cloneError !== "DataCloneError" || clone.terminated !== 1)
        throw new Error("configuration failure was not cleaned up");

      blob = URL.createObjectURL(
        new Blob(["self.onmessage = () => {};"], { type: "text/javascript" }),
      );
      const silent = owned(blob);
      const timeout = await rejected(
        openDiskWorker(silent.worker, {}, workerDevice, { timeoutMs: 50 }),
      );
      if (timeout !== "TimeoutError" || silent.terminated !== 1)
        throw new Error("silent worker did not time out cleanly");

      const live = owned();
      const after = new AbortController();
      const device = await openDiskWorker(live.worker, { handle }, workerDevice, {
        signal: after.signal,
      });
      after.abort(reason);
      if (live.terminated !== 0) throw new Error("startup abort killed an already ready device");
      live.worker.postMessage({ type: "close" });
      await device.closed;
      if (live.terminated !== 1) throw new Error("device closure did not release its worker");
      await reopen();
      const bytes = new Uint8Array(await (await handle.getFile()).arrayBuffer());
      return {
        bytes: bytes.length,
        unchanged: bytes.every((value) => value === 0x5a),
        workers: workers.length,
      };
    } finally {
      for (const state of workers) if (state.terminated === 0) state.worker.terminate();
      if (blob) URL.revokeObjectURL(blob);
      await directory.removeEntry(name);
    }
  });
  expect(result).toEqual({ bytes: 512, unchanged: true, workers: 5 });
});
