// SPDX-License-Identifier: MIT
// The launcher inserts a test-only pause immediately before the real host open.
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
const { NodeFS } = await import(pathToFileURL(process.argv[2]).href);
const directory = await mkdtemp(path.join(tmpdir(), "nodefs-open-race-"));
try {
  if (process.argv[3] === "directory") {
    const target = path.join(directory, "directory"),
      moved = path.join(directory, "moved");
    await mkdir(target);
    await writeFile(path.join(target, "old-entry"), "old");
    const fs = new NodeFS(directory);
    const old = await fs.lookup(fs.root, "directory");
    const before = readdirSync("/proc/self/fd").length;
    let raced = false;
    globalThis.nodefsOpenRace = async (actual) => {
      assert.equal(actual, target);
      globalThis.nodefsOpenRace = undefined;
      await rename(target, moved);
      await mkdir(target);
      await writeFile(path.join(target, "new-entry"), "replacement");
      raced = true;
    };
    await assert.rejects(fs.opendir(old), { errno: 2 }, "directory identity mismatch must reject");
    assert.equal(raced, true);
    assert.equal(readdirSync("/proc/self/fd").length, before, "unpublished directory fd is closed");
    const fresh = await fs.lookup(fs.root, "directory");
    assert.notEqual(fresh, old);
    const handle = await fs.opendir(fresh);
    try {
      assert.deepEqual(
        (await fs.readdir(fresh, handle)).map((entry) => entry.name),
        ["new-entry"],
      );
    } finally {
      await fs.releasedir(fresh, handle);
    }
    assert.equal(readdirSync("/proc/self/fd").length, before, "recovery directory fd is closed");
    assert.equal(await readFile(path.join(moved, "old-entry"), "utf8"), "old");
    console.log(
      "NodeFS: directory open rejects a replaced inode, closes unpublished fd and recovers pass",
    );
  } else {
    for (const flags of [0, 0x200, 0x201]) {
      const target = path.join(directory, "file"),
        staging = path.join(directory, "staging");
      await writeFile(target, "old");
      await writeFile(staging, "replacement");
      const fs = new NodeFS(directory);
      const old = await fs.lookup(fs.root, "file");
      const before = readdirSync("/proc/self/fd").length;
      let raced = false;
      globalThis.nodefsOpenRace = async (actual) => {
        assert.equal(actual, target);
        globalThis.nodefsOpenRace = undefined;
        await rename(staging, target);
        raced = true;
      };
      await assert.rejects(fs.open(old, flags), { errno: 2 });
      assert.equal(raced, true, "replacement occurs after preflight, before host open");
      assert.equal(await readFile(target, "utf8"), "replacement", "replacement stays intact");
      assert.equal(readdirSync("/proc/self/fd").length, before, "unpublished fd is closed");
      const fresh = await fs.lookup(fs.root, "file");
      assert.notEqual(fresh, old);
      const handle = await fs.open(fresh, 0);
      try {
        assert.equal(new TextDecoder().decode(await fs.read(fresh, handle, 0n, 11)), "replacement");
      } finally {
        await fs.release(fresh, handle);
      }
    }
  }
} finally {
  globalThis.nodefsOpenRace = undefined;
  await rm(directory, { recursive: true, force: true });
}
if (process.argv[3] !== "directory")
  console.log(
    "NodeFS: actual rename between preflight and open preserves replacement, rejects stale binding, closes fd and recovers pass",
  );
