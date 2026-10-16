// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("forwards fragmented POST bodies through browser Request", async ({ page }) => {
  test.setTimeout(30_000);
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const { hostFetchNetwork } = await import("/host-http.js");
    const outcomes = [];
    for (const [framing, payload] of [
      ["Content-Length: 5", "hello"],
      ["Transfer-Encoding: chunked", "2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n"],
    ]) {
      let received;
      const network = hostFetchNetwork({
        async fetch(request) {
          received = { method: request.method, url: request.url, body: await request.text() };
          return new Response("accepted", { status: 201 });
        },
      });
      const bytes = new TextEncoder().encode(
        `POST /submit HTTP/1.1\r\nHost: example.test\r\n${framing}\r\n\r\n${payload}`,
      );
      const readable = new ReadableStream({
        start(controller) {
          for (let i = 0; i < bytes.length; i += 3) controller.enqueue(bytes.slice(i, i + 3));
          controller.close();
        },
      });
      let output = "";
      const decoder = new TextDecoder();
      const writable = new WritableStream({
        write(chunk) {
          output += decoder.decode(chunk, { stream: true });
        },
      });
      await network.connectTcp({
        target: { hostname: "198.18.0.1", port: 80 },
        signal: new AbortController().signal,
        readable,
        writable,
      });
      outcomes.push({ received, output, locks: [readable.locked, writable.locked] });
    }
    return outcomes;
  });
  expect(results).toHaveLength(2);
  for (const result of results) {
    expect(result.received).toEqual({
      method: "POST",
      url: "https://example.test/submit",
      body: "hello",
    });
    expect(result.output).toMatch(/^HTTP\/1\.1 201 /);
    expect(result.output.split("\r\n\r\n")[1]).toBe("accepted");
    expect(result.locks).toEqual([false, false]);
  }
});

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
