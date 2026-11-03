// SPDX-License-Identifier: MIT
// Executed in a child with RLIMIT_NOFILE=96 by check_nodefs_fd_limit.py.
import assert from "node:assert/strict";
import { closeSync, openSync, readdirSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { NodeFS } from "../../sources/distro/packages/linux-guest/src/node.ts";
import { fileSystemDevice } from "../../sources/distro/packages/kernel/src/virtio/fs.ts";
import {
  close_virtio_device,
  virtio_imports,
} from "../../sources/distro/packages/kernel/src/virtio/core.ts";

const directory = await mkdtemp(path.join(tmpdir(), "nodefs-fd-limit-"));
const held: number[] = [];
let baseline: number | undefined;
const device = fileSystemDevice(new NodeFS(directory), { tag: "fd-limit" });
const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
const bytes = new Uint8Array(memory.buffer);
const view = new DataView(memory.buffer);
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
async function request(op: number, id: bigint, body: Uint8Array, error = 0) {
  complete = Promise.withResolvers<void>();
  bytes.fill(0);
  view.setUint32(128, 40 + body.length, true);
  view.setUint32(132, op, true);
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
  await complete.promise;
  imports.disable_vring(0, 0);
  assert.equal(view.getInt32(1028, true), -error || 0);
}
try {
  await writeFile(path.join(directory, "file"), "readable");
  await request(1, 1n, new TextEncoder().encode("file\0"));
  const inode = view.getBigUint64(1040, true);
  baseline = readdirSync("/proc/self/fd").length;
  for (;;) {
    try {
      held.push(openSync("/dev/null", "r"));
    } catch (error) {
      assert.equal((error as NodeJS.ErrnoException).code, "EMFILE");
      break;
    }
    assert(held.length < 96, "the isolated process must have the configured fd limit");
  }
  // The backend must preserve a real host failure in the signed FUSE reply,
  // without publishing a handle that would leak during machine shutdown.
  await request(14, inode, new Uint8Array(8), 24);
  closeSync(held.pop()!);
  await request(14, inode, new Uint8Array(8));
  const fh = view.getBigUint64(1040, true);
  const read = new Uint8Array(40);
  const input = new DataView(read.buffer);
  input.setBigUint64(0, fh, true);
  input.setUint32(16, 8, true);
  await request(15, inode, read);
  assert.equal(new TextDecoder().decode(bytes.subarray(1040, 1048)), "readable");
  console.log(
    "NodeFS: actual EMFILE reaches FUSE and open/read recovers after freeing one fd pass",
  );
} finally {
  for (const fd of held) closeSync(fd);
  await close_virtio_device(device);
  await rm(directory, { recursive: true, force: true });
}
assert.equal(readdirSync("/proc/self/fd").length, baseline, "device shutdown closes its opened fd");
console.log("NodeFS: exhausted-descriptor device closes without leaked protocol handles pass");
