// SPDX-License-Identifier: MIT
// Isolated continuation mechanics only: no Linux process, libc, fd or signal ABI.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";

export async function probe(bytes, options = {}) {
  const {
    width = 32,
    failCreation = false,
    smallStack = false,
    workerChildren = false,
    inherited = null,
    omitSnapshot = false,
  } = options;
  assert.ok(width === 32 || width === 64);
  const module = inherited?.module ?? new WebAssembly.Module(bytes);
  for (const name of [
    "run",
    "prepare",
    "__stack_pointer",
    "asyncify_start_unwind",
    "asyncify_stop_unwind",
    "asyncify_start_rewind",
    "asyncify_stop_rewind",
    "asyncify_get_state",
  ]) {
    assert.ok(
      WebAssembly.Module.exports(module).some((e) => e.name === name),
      `missing ${name}`,
    );
  }
  const pointer = (value) => (width === 64 ? BigInt(value) : value);
  const ids = inherited?.ids ?? new Int32Array(new SharedArrayBuffer(4));
  if (!inherited) ids[0] = 100;
  const events = [];
  const completed = [];

  function create() {
    const memory = new WebAssembly.Memory({
      initial: pointer(16),
      maximum: pointer(16),
      shared: true,
      ...(width === 64 ? { address: "i64" } : {}),
    });
    const state = {
      id: Atomics.add(ids, 0, 1) + 1,
      memory,
      exports: null,
      resume: null,
      descriptor: null,
    };
    const instance = new WebAssembly.Instance(module, {
      env: { memory },
      continuation_probe_v1: {
        checkpoint() {
          const e = state.exports;
          if (e.asyncify_get_state() === 2) {
            assert.notEqual(state.resume, null, "rewind without checkpoint result");
            e.asyncify_stop_rewind();
            const result = state.resume;
            state.resume = null;
            return result;
          }
          assert.equal(e.asyncify_get_state(), 0);
          assert.equal(state.resume, null);
          e.asyncify_start_unwind(state.descriptor);
          return 0; // discarded by the transformed unwind path
        },
        event(value) {
          events.push({ id: state.id, value });
        },
      },
    });
    state.exports = instance.exports;
    state.descriptor = instance.exports.prepare();
    if (smallStack) {
      const view = new DataView(memory.buffer);
      const offset = Number(state.descriptor);
      if (width === 64) view.setBigUint64(offset + 8, view.getBigUint64(offset, true) + 8n, true);
      else view.setUint32(offset + 4, view.getUint32(offset, true) + 8, true);
    }
    return state;
  }

  // Run each child before its parent resumes. This deliberately exercises that
  // child writes cannot change the parent's saved frames or ordinary memory.
  async function execute(state, rewind) {
    const e = state.exports;
    if (rewind) e.asyncify_start_rewind(state.descriptor);
    const result = e.run(failCreation ? 1 : 0);
    if (e.asyncify_get_state() === 0) {
      assert.equal(state.resume, null);
      completed.push({ id: state.id, result });
      return;
    }
    assert.equal(e.asyncify_get_state(), 1);
    e.asyncify_stop_unwind();
    if (failCreation) {
      state.resume = -12;
    } else {
      // Instantiate BEFORE copying: active data segments must not overwrite the
      // inherited snapshot. The child is not exposed until initialization ends.
      if (workerChildren) {
        const snapshot = new Uint8Array(state.memory.buffer).slice().buffer;
        const child = new Worker(new URL(import.meta.url), {
          workerData: {
            width,
            workerChildren,
            inherited: {
              module,
              ids,
              snapshot,
              stackPointer: e.__stack_pointer.value,
              descriptor: state.descriptor,
            },
          },
          transferList: [snapshot],
        });
        const outcome = await new Promise((resolve, reject) => {
          let message = null;
          child.once("message", (value) => {
            message = value;
          });
          child.once("error", reject);
          child.once("exit", (code) => {
            if (code !== 0 || !message) reject(new Error(`child worker failed: ${code}`));
            else resolve(message);
          });
        });
        state.resume = outcome.rootId;
        events.push(...outcome.events);
        completed.push(...outcome.completed);
      } else {
        const child = create();
        if (!omitSnapshot) {
          new Uint8Array(child.memory.buffer).set(new Uint8Array(state.memory.buffer));
        }
        child.exports.__stack_pointer.value = e.__stack_pointer.value;
        child.descriptor = state.descriptor;
        child.resume = 0;
        state.resume = child.id;
        await execute(child, true);
      }
    }
    await execute(state, true);
  }

  const root = create();
  if (inherited) {
    new Uint8Array(root.memory.buffer).set(new Uint8Array(inherited.snapshot));
    root.exports.__stack_pointer.value = inherited.stackPointer;
    root.descriptor = inherited.descriptor;
    root.resume = 0;
  }
  await execute(root, Boolean(inherited));
  if (inherited) return { rootId: root.id, completed, events };
  assert.deepEqual(
    completed.map((x) => x.result).sort((a, b) => a - b),
    failCreation ? [77] : [0, 1, 2, 3],
  );
  assert.equal(events.filter((x) => x.value === 1).length, 1, "pre-fork effects replayed");
  assert.equal(events.filter((x) => x.value === 2).length, failCreation ? 0 : 2);
  assert.equal(events.filter((x) => x.value === 3).length, failCreation ? 0 : 4);
  return { completed, events };
}

if (!isMainThread) {
  parentPort.postMessage(await probe(null, workerData));
} else if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [path, bits, optimization] = process.argv.slice(2);
  const bytes = readFileSync(path);
  const width = Number(bits);
  const result = await probe(bytes, { width });
  await probe(bytes, { width, workerChildren: true });
  await probe(bytes, { width, failCreation: true });
  await assert.rejects(probe(bytes, { width, smallStack: true }), WebAssembly.RuntimeError);
  await assert.rejects(probe(bytes, { width, omitSnapshot: true }));
  console.log(
    JSON.stringify({
      width,
      optimization,
      branches: result.completed.length,
      workerChildren: "pass",
      creationFailure: "pass",
      stackOverflow: "pass",
      missingSnapshot: "rejected",
      status: "pass",
    }),
  );
}
