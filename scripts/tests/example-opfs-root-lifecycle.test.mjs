// SPDX-License-Identifier: MIT
// Real root/handshake/kernel code with host file/lock adapters, not actual OPFS.
import assert from "node:assert/strict";
import { MessageChannel } from "node:worker_threads";
import test from "node:test";
import { openRoot } from "../../sources/distro/apps/wasm64-example/root.js";
import { deleteRootDisk } from "../../sources/distro/apps/wasm64-example/root-storage.js";
import { openDiskWorker } from "../../sources/distro/apps/site/opfs-device.js";
import {
  blockDevice,
  closeDevice,
  serveDevice,
  workerDevice,
} from "../../sources/distro/packages/kernel/src/index.ts";

for (const failure of [false, true]) {
  test(
    `example root waits for a real remote backend close, failure=${failure}`,
    { timeout: 5000 },
    async () => {
      const entered = Promise.withResolvers();
      const finish = Promise.withResolvers();
      const channels = [];
      let locked = false;
      let terminations = 0;
      let closes = 0;
      let removals = 0;
      const reason = new Error("injected backend flush failure");
      const storage = {
        async getDirectory() {
          return {
            async getFileHandle(name, options) {
              assert.equal(name, "linux-wasm64-integration.ext4");
              assert.equal(options, undefined);
              return {
                async getFile() {
                  return { size: 512 };
                },
              };
            },
            async removeEntry(name, options) {
              assert.equal(name, "linux-wasm64-integration.ext4");
              assert.equal(options, undefined);
              removals++;
            },
          };
        },
      };
      const locks = {
        async request(name, options, body) {
          assert.equal(name, "linux-wasm64-disk:linux-wasm64-integration.ext4");
          assert.equal(options.ifAvailable, true);
          if (locked) return body(null);
          locked = true;
          try {
            return await body({});
          } finally {
            locked = false;
          }
        },
      };
      const removeDisk = () =>
        deleteRootDisk({ name: "integration", confirmation: "integration" }, { storage, locks });
      let root;
      try {
        root = await openRoot(
          { mode: "open", name: "integration" },
          {
            loadImage() {
              assert.fail("reopen must not load a template");
            },
            blockDevice,
            closeDevice,
            workerDevice,
            openWorker: openDiskWorker,
            storage,
            locks,
            Worker: class {
              constructor() {
                const channel = new MessageChannel();
                channels.push(channel);
                const endpoint = channel.port1;
                const post = endpoint.postMessage.bind(endpoint);
                endpoint.postMessage = (message, ...args) => {
                  // File/lock adapters stay on the host. All device protocol and
                  // close acknowledgements cross actual MessagePorts unchanged.
                  if (message.handle) {
                    assert.deepEqual(Object.keys(message), ["handle"]);
                    serveDevice(
                      channel.port2,
                      blockDevice({
                        capacity: 512,
                        read() {
                          return 0;
                        },
                        write() {
                          return 0;
                        },
                        async close() {
                          closes++;
                          entered.resolve();
                          await finish.promise;
                        },
                      }),
                    );
                  } else post(message, ...args);
                };
                endpoint.terminate = () => {
                  terminations++;
                  channel.port1.close();
                  channel.port2.close();
                };
                return endpoint;
              }
            },
          },
        );
        assert.equal("close" in root.device, false);
        assert.equal(locked, true);
        const closing = root.close();
        void closing.catch(() => {});
        await Promise.race([
          entered.promise,
          closing.then(() => assert.fail("cleanup cannot finish before backend close")),
        ]);
        assert.equal(locked, true);
        assert.equal(terminations, 0);
        await assert.rejects(removeDisk(), /already open in another page/);
        assert.equal(removals, 0);
        if (failure) {
          finish.reject(reason);
          await assert.rejects(closing, { message: reason.message });
          await assert.rejects(root.close(), { message: reason.message });
        } else {
          finish.resolve();
          await closing;
          await root.close();
        }
        assert.equal(closes, 1);
        assert.equal(locked, false);
        assert.equal(terminations, 1);
        await removeDisk();
        assert.equal(removals, 1);
        assert.equal(locked, false);
      } finally {
        finish.resolve();
        await root?.close().catch(() => {});
        for (const channel of channels) {
          channel.port1.close();
          channel.port2.close();
        }
      }
    },
  );
}
