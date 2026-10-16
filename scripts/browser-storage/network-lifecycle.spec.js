// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

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
