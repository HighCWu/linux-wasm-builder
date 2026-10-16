// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("cancels pending Fetch response reads on disconnect", async ({ page }) => {
  test.setTimeout(30_000);
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { hostFetchNetwork } = await import("/host-http.js");
    const abort = new AbortController();
    const reason = new Error("connection closed");
    let cancelled = 0;
    let sameReason = false;
    let resolveReady;
    const ready = new Promise((resolve) => {
      resolveReady = resolve;
    });
    const body = new ReadableStream({
      cancel(value) {
        cancelled++;
        sameReason = value === reason;
      },
    });
    const network = hostFetchNetwork({ fetch: () => new Response(body) });
    const readable = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode("GET / HTTP/1.1\r\nHost: example.test\r\n\r\n"),
        );
        controller.close();
      },
    });
    const writable = new WritableStream({
      write() {
        resolveReady();
      },
    });
    const handled = Promise.resolve(
      network.connectTcp({
        target: { hostname: "198.18.0.1", port: 80 },
        signal: abort.signal,
        readable,
        writable,
      }),
    ).then(
      () => "unexpected success",
      (error) => (error === reason ? "cancelled" : String(error)),
    );
    await ready;
    abort.abort(reason);
    const outcome = await handled;
    return {
      outcome,
      cancelled,
      sameReason,
      locks: [body.locked, readable.locked, writable.locked],
    };
  });
  expect(result).toEqual({
    outcome: "cancelled",
    cancelled: 1,
    sameReason: true,
    locks: [false, false, false],
  });
});
