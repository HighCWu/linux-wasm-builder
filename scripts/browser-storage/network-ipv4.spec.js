// SPDX-License-Identifier: MIT
import { expect, test } from "@playwright/test";

test("IPv4 parser validates complete header checksums including options", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const { parseIpv4Frame } = await import("/network-api.js");
    const frame = new Uint8Array(14 + 115);
    frame[12] = 8;
    frame.set(
      Uint8Array.from("45000073000040004011b861c0a80001c0a800c7".match(/../g), (s) =>
        parseInt(s, 16),
      ),
      14,
    );
    const valid = parseIpv4Frame(frame);
    frame[26] ^= 1;
    const corrupt = parseIpv4Frame(frame);
    // An IHL=6 packet, four NOP options, and an independently computed checksum.
    const options = new Uint8Array(14 + 24 + 3 + 10);
    options[12] = 8;
    options.set(
      [0x46, 0, 0, 27, 0, 1, 0, 0, 64, 17, 0, 0, 192, 0, 2, 2, 192, 0, 2, 1, 1, 1, 1, 1],
      14,
    );
    options.set([0, 255, 42], 38);
    let sum = 0;
    for (let i = 14; i < 38; i += 2) sum += options[i] * 256 + options[i + 1];
    while (sum > 65535) sum = (sum % 65536) + Math.floor(sum / 65536);
    options[24] = (65535 - sum) >>> 8;
    options[25] = (65535 - sum) & 255;
    const withOptions = parseIpv4Frame(options);
    options[34] ^= 1;
    return {
      valid: valid && {
        source: valid.source,
        destination: valid.destination,
        length: valid.payload.length,
      },
      corruptRejected: corrupt === undefined,
      options: withOptions && {
        headerLength: withOptions.header_length,
        payload: [...withOptions.payload],
      },
      corruptOptionRejected: parseIpv4Frame(options) === undefined,
    };
  });
  expect(result).toEqual({
    valid: { source: 0xc0a80001, destination: 0xc0a800c7, length: 95 },
    corruptRejected: true,
    options: { headerLength: 24, payload: [0, 255, 42] },
    corruptOptionRejected: true,
  });
});
