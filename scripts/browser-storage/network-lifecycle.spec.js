// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("UDP channel close settles idle writers and pending readers", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { createNetwork, guestAgent } = await import("/network-api.js");
    const outcomes = [];
    for (const mode of ["connection", "network", "cancel", "writer close", "writer abort"]) {
      const network = createNetwork({
        connectTcp() {
          throw new Error("test must not open external TCP");
        },
        async resolveDns() {
          throw new Error("test must not resolve names");
        },
      });
      const attachment = network.attach(guestAgent());
      const connection = await attachment.connect({ port: 12345, transport: "udp" });
      const writer = connection.writable.getWriter();
      const reader = connection.readable.getReader();
      const read = reader.read();
      const reason = new Error("application abort");
      const closed = writer.closed.then(
        () => "closed",
        (error) => (error === reason ? "application abort" : error.message),
      );
      let timer;
      try {
        if (mode === "connection") connection.close();
        if (mode === "network") network.close();
        if (mode === "cancel") await reader.cancel();
        if (mode === "writer close") await writer.close();
        if (mode === "writer abort") await writer.abort(reason);
        const state = await Promise.race([
          closed,
          new Promise((resolve) => {
            timer = setTimeout(() => resolve("pending"), 1000);
          }),
        ]);
        outcomes.push({ mode, state, readEnded: (await read).done });
        connection.close();
        connection.close();
      } finally {
        clearTimeout(timer);
        connection.close();
        await writer.abort().catch(() => {});
        await read;
        reader.releaseLock();
        writer.releaseLock();
        network.close();
      }
    }
    return outcomes;
  });
  expect(result).toEqual([
    { mode: "connection", state: "UDP connection is closed", readEnded: true },
    { mode: "network", state: "UDP connection is closed", readEnded: true },
    { mode: "cancel", state: "UDP connection is closed", readEnded: true },
    { mode: "writer close", state: "closed", readEnded: true },
    { mode: "writer abort", state: "application abort", readEnded: true },
  ]);
});

test("UDP write failure releases the private network flow and pending read", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { createNetwork, guestAgent } = await import("/network-api.js");
    const network = createNetwork({
      connectTcp() {
        throw new Error("test must not open external TCP");
      },
      async resolveDns() {
        throw new Error("test must not resolve names");
      },
    });
    const attachment = network.attach(guestAgent());
    const outcomes = [];
    try {
      for (const length of [0, 65507, 65508, 131072]) {
        const connection = await attachment.connect({ port: 12345, transport: "udp" });
        const writer = connection.writable.getWriter();
        const reader = connection.readable.getReader();
        const pending = reader.read();
        let timer;
        try {
          let error = null;
          try {
            await writer.write(new Uint8Array(length));
            await writer.close();
          } catch (caught) {
            error = caught.name;
            await writer.closed.catch(() => {});
          }
          const closed = await Promise.race([
            pending.then(({ done }) => done),
            new Promise((resolve) => {
              timer = setTimeout(() => resolve(false), 1000);
            }),
          ]);
          outcomes.push({ length, error, closed });
        } finally {
          clearTimeout(timer);
          connection.close();
          await pending;
          reader.releaseLock();
          writer.releaseLock();
        }
      }
      return outcomes;
    } finally {
      network.close();
    }
  });
  expect(result).toEqual([
    { length: 0, error: null, closed: true },
    { length: 65507, error: null, closed: true },
    { length: 65508, error: "RangeError", closed: true },
    { length: 131072, error: "RangeError", closed: true },
  ]);
});
