// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

for (const pendingCallback of [false, true]) {
  test(
    pendingCallback
      ? "releases disconnected Fetch callbacks and cancels late responses"
      : "cancels pending Fetch response reads on disconnect",
    async ({ page }) => {
      test.setTimeout(30_000);
      await page.goto("/");
      const result = await page.evaluate(async (pendingCallback) => {
        const { hostFetchNetwork } = await import("/host-http.js");
        const abort = new AbortController();
        const reason = new Error("connection closed");
        let cancelled = 0;
        let sameReason = false;
        let finish;
        const response = new Promise((resolve) => {
          finish = resolve;
        });
        let markCancelled;
        const cancellation = new Promise((resolve) => {
          markCancelled = resolve;
        });
        let resolveReady;
        const ready = new Promise((resolve) => {
          resolveReady = resolve;
        });
        const body = new ReadableStream({
          cancel(value) {
            cancelled++;
            sameReason = value === reason;
            markCancelled();
          },
        });
        const network = hostFetchNetwork({
          fetch: () => {
            if (!pendingCallback) return new Response(body);
            resolveReady();
            return response;
          },
        });
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
        const connectionLocks = [readable.locked, writable.locked];
        if (pendingCallback) finish(new Response(body));
        await cancellation;
        return {
          outcome,
          cancelled,
          sameReason,
          connectionLocks,
          locks: [body.locked, readable.locked, writable.locked],
        };
      }, pendingCallback);
      expect(result).toEqual({
        outcome: "cancelled",
        cancelled: 1,
        sameReason: true,
        connectionLocks: [false, false],
        locks: [false, false, false],
      });
    },
  );
}
