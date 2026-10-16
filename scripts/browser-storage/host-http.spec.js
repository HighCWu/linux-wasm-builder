// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("forwards fragmented POST bodies through browser Request", async ({ page }) => {
  test.setTimeout(30_000);
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const { hostFetchNetwork } = await import("/host-http.js");
    const outcomes = [];
    for (const [framing, payload, reused] of [
      ["Content-Length: 5", "hello", false],
      ["Transfer-Encoding: chunked", "2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n", false],
      ["Content-Length: 5", "hello", true],
      ["Transfer-Encoding: chunked", "2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n", true],
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
      let offset = 0;
      const slab = new Uint8Array(3);
      const readable = new ReadableStream(
        {
          pull(controller) {
            if (offset === bytes.length) {
              controller.close();
              return;
            }
            const piece = bytes.subarray(offset, offset + 3);
            offset += piece.length;
            if (reused) {
              slab.set(piece);
              controller.enqueue(slab.subarray(0, piece.length));
            } else controller.enqueue(piece.slice());
          },
        },
        { highWaterMark: 0 },
      );
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
  expect(results).toHaveLength(4);
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

test("enforces upload budgets only when browser buffering is required", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    // Observe actual body conversion independently of the adapter's probe.
    let streaming = false;
    try {
      const probe = new Request("https://example.test/", {
        method: "POST",
        duplex: "half",
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode("hello"));
            controller.close();
          },
        }),
      });
      streaming = (await probe.text()) === "hello";
    } catch {}
    const { hostFetchNetwork } = await import("/host-http.js");
    const outcomes = [];
    for (const chunked of [false, true]) {
      for (const limit of [0, 4, 5]) {
        let calls = 0;
        let received;
        let cancelled = 0;
        const network = hostFetchNetwork({
          maxBufferedRequestBytes: limit,
          async fetch(request) {
            calls++;
            received = await request.text();
            return new Response("accepted", { status: 201 });
          },
        });
        const rejectBeforeUpload = !streaming && !chunked && limit < 5;
        const wire = new TextEncoder().encode(
          "POST / HTTP/1.1\r\nHost: example.test\r\n" +
            (chunked
              ? "Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n"
              : rejectBeforeUpload
                ? "Content-Length: 5\r\nExpect: 100-continue\r\n\r\n"
                : "Content-Length: 5\r\n\r\nhello"),
        );
        let offset = 0;
        const readable = new ReadableStream({
          pull(controller) {
            if (offset < wire.length) controller.enqueue(wire.slice(offset, ++offset));
            // Leave the connection open: body framing, not EOF, must finish it.
          },
          cancel() {
            cancelled++;
          },
        });
        let output = "";
        const writable = new WritableStream({
          write(chunk) {
            output += new TextDecoder().decode(chunk);
          },
        });
        await network.connectTcp({
          target: { hostname: "198.18.0.1", port: 80 },
          signal: new AbortController().signal,
          readable,
          writable,
        });
        outcomes.push({
          limit,
          calls,
          received,
          output,
          cancelled,
          locks: [readable.locked, writable.locked],
        });
      }
    }
    return { streaming, outcomes };
  });
  expect(result.outcomes).toHaveLength(6);
  for (const outcome of result.outcomes) {
    const accepted = result.streaming || outcome.limit === 5;
    expect(outcome.calls).toBe(accepted ? 1 : 0);
    expect(outcome.received).toBe(accepted ? "hello" : undefined);
    expect(outcome.output).toMatch(accepted ? /^HTTP\/1\.1 201 / : /^HTTP\/1\.1 413 /);
    expect(outcome.cancelled).toBe(1);
    expect(outcome.locks).toEqual([false, false]);
  }
});

test("cancels incomplete browser uploads without sending a response", async ({ page }) => {
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const { hostFetchNetwork } = await import("/host-http.js");
    const outcomes = [];
    for (const chunked of [false, true]) {
      const abort = new AbortController();
      const reason = new Error("upload disconnected");
      let waiting;
      const ready = new Promise((resolve) => {
        waiting = resolve;
      });
      let sent = false;
      let cancelled = 0;
      let sameReason = false;
      const readable = new ReadableStream(
        {
          pull(controller) {
            if (sent) {
              waiting();
              return;
            }
            sent = true;
            controller.enqueue(
              new TextEncoder().encode(
                "POST / HTTP/1.1\r\nHost: example.test\r\n" +
                  (chunked
                    ? "Transfer-Encoding: chunked\r\n\r\n5\r\nhe"
                    : "Content-Length: 5\r\n\r\nhe"),
              ),
            );
          },
          cancel(value) {
            cancelled++;
            sameReason = value === reason;
          },
        },
        { highWaterMark: 0 },
      );
      let writes = 0;
      let completedUploads = 0;
      const writable = new WritableStream({
        write() {
          writes++;
        },
      });
      const network = hostFetchNetwork({
        async fetch(request) {
          await request.text();
          completedUploads++;
          return new Response("unexpected");
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
        () => false,
        (error) => error === reason,
      );
      await ready;
      abort.abort(reason);
      const rejectedWithReason = await handled;
      outcomes.push({
        rejectedWithReason,
        cancelled,
        sameReason,
        writes,
        completedUploads,
        locks: [readable.locked, writable.locked],
      });
    }
    return outcomes;
  });
  expect(results).toHaveLength(2);
  for (const result of results)
    expect(result).toEqual({
      rejectedWithReason: true,
      cancelled: 1,
      sameReason: true,
      writes: 0,
      completedUploads: 0,
      locks: [false, false],
    });
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
