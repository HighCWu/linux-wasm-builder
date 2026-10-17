// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileSystemDevice } from "../../sources/distro/packages/kernel/src/virtio/fs.ts";
import {
  close_virtio_device,
  virtio_imports,
} from "../../sources/distro/packages/kernel/src/virtio/core.ts";
import { NodeFS } from "../../sources/distro/packages/linux-guest/src/node.ts";

const shared = await mkdtemp(path.join(tmpdir(), "linux-wasm-directory-device-"));
after(() => rm(shared, { recursive: true, force: true }));

for (const closeFails of [false, true]) {
  test(`node virtio-fs device shutdown closes real directory descriptors, first close fails=${closeFails}`, async () => {
    const fs = new NodeFS(shared);
    const opened: Awaited<ReturnType<typeof fs.opendir>>[] = [];
    const openDirectory = fs.opendir.bind(fs);
    let closes = 0;
    fs.opendir = async (node) => {
      const handle = await openDirectory(node);
      assert.ok(handle.file);
      const close = handle.file.close.bind(handle.file);
      handle.file.close = async () => {
        closes++;
        await close();
        if (closeFails && closes === 1) {
          throw Object.assign(new Error("injected first close failure"), { code: "EIO" });
        }
      };
      opened.push(handle);
      return handle;
    };
    const device = fileSystemDevice(fs, { tag: "node-directories" });
    const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
    const bytes = new Uint8Array(memory.buffer),
      view = new DataView(memory.buffer);
    let complete = Promise.withResolvers<void>();
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
    let closed = false;
    try {
      for (let index = 0; index < 2; index++) {
        complete = Promise.withResolvers<void>();
        bytes.fill(0);
        view.setUint32(128, 48, true);
        view.setUint32(132, 27, true); // OPENDIR for the root node.
        view.setBigUint64(136, BigInt(index + 1), true);
        view.setBigUint64(144, 1n, true);
        view.setBigUint64(0, 128n, true);
        view.setUint32(8, 48, true);
        view.setUint16(14, 129, true);
        view.setBigUint64(16, 1024n, true);
        view.setUint32(24, 512, true);
        view.setUint16(30, 130, true);
        imports.enable_vring(0, 0, 4, 0, 1);
        imports.notify(0, 0);
        await complete.promise;
        imports.disable_vring(0, 0);
        assert.equal(view.getInt32(1028, true), 0);
      }
      assert.equal(opened.length, 2);
      for (const handle of opened) await handle.file!.stat();
      const closing = close_virtio_device(device);
      closed = true;
      if (closeFails) await assert.rejects(closing, { errno: 5 });
      else await closing;
      assert.equal(closes, 2, "a failed release must not skip later descriptors");
      for (const handle of opened) {
        await assert.rejects(handle.file!.stat(), { code: "EBADF" });
        await assert.rejects(fs.readdir(fs.root, handle), { errno: 9 });
      }
    } finally {
      if (!closed) await close_virtio_device(device);
    }
  });
}
