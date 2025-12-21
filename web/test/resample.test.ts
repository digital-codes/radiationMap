// resampleTimeSeries.test.ts
// Adjust the import path to where your function lives.
import { describe, it, expect } from "vitest";
import { resampleTimeSeries } from "../src/resample.ts";


type Out = Array<[string, number]>;

function parseIsoStrict(iso: string): number {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) throw new Error(`Output timestamp is not valid ISO: "${iso}"`);
  return ms;
}

function normalizeIso(iso: string): string {
  return new Date(parseIsoStrict(iso)).toISOString();
}

/**
 * Assert that two timestamps represent the same instant, but report in ISO.
 * (We normalize both to ISO Z to avoid ".000Z" formatting differences.)
 */
function expectIsoInstant(receivedIso: string, expectedIso: string) {
  const rNorm = normalizeIso(receivedIso);
  const eNorm = normalizeIso(expectedIso);

  if (rNorm !== eNorm) {
    const rMs = Date.parse(rNorm);
    const eMs = Date.parse(eNorm);
    throw new Error(
      [
        "Timestamp mismatch",
        `expected: ${expectedIso}  (normalized: ${eNorm})`,
        `received: ${receivedIso}  (normalized: ${rNorm})`,
        `delta: ${(rMs - eMs) / 60000} minutes`,
      ].join("\n")
    );
  }

  expect(rNorm).toBe(eNorm);
}

function expectSeries(
  out: Out,
  expected: Array<[string, number]>,
  valueDp = 6
) {
  expect(out.length).toBe(expected.length);

  for (let i = 0; i < expected.length; i++) {
    const [gotT, gotV] = out[i];
    const [expT, expV] = expected[i];

    expectIsoInstant(gotT, expT);
    expect(gotV).toBeCloseTo(expV, valueDp);
  }
}

describe("resampleTimeSeries", () => {
  it("missing data: middle interpolated, end forward-filled", () => {
    const input: SampleInput[] = [
      ["2025-01-01T10:07:00Z", 10],      // -> 10:00 bin
      ["2025-01-01T10:37:00Z", 40],      // -> 10:30 bin
      ["2025-01-01T10:52:00Z", "oops"],  // -> 10:45 bin exists but missing value
    ];

    const out = resampleTimeSeries(input, {
      intervalMinutes: 15,
      timeZone: "UTC",
      outputInTimeZone: false,
      extendToNow: false,
    });

    expectSeries(out, [
      ["2025-01-01T10:00:00Z", 10],
      ["2025-01-01T10:15:00Z", 25],
      ["2025-01-01T10:30:00Z", 40],
      ["2025-01-01T10:45:00Z", 40],
    ]);
  });

  it("missing data at front: back-filled from first known bin", () => {
    const input: SampleInput[] = [
      ["2025-01-01T10:01:00Z", "bad"], // 10:00 bin missing
      ["2025-01-01T10:31:00Z", 50],    // 10:30 bin
    ];

    const out = resampleTimeSeries(input, {
      intervalMinutes: 15,
      timeZone: "UTC",
      outputInTimeZone: false,
    });

    expectSeries(out, [
      ["2025-01-01T10:00:00Z", 50],
      ["2025-01-01T10:15:00Z", 50],
      ["2025-01-01T10:30:00Z", 50],
    ]);
  });

  it("missing data in middle only: interpolates between neighbors", () => {
    const input: SampleInput[] = [
      ["2025-01-01T10:01:00Z", 0],
      ["2025-01-01T10:31:00Z", 30],
    ];

    const out = resampleTimeSeries(input, {
      intervalMinutes: 15,
      timeZone: "UTC",
      outputInTimeZone: false,
      skipZeros: false,
    });

    expectSeries(out, [
      ["2025-01-01T10:00:00Z", 0],
      ["2025-01-01T10:15:00Z", 15],
      ["2025-01-01T10:30:00Z", 30],
    ]);
  });

  it("0-values: skipZeros=true treats 0 as missing and fills", () => {
    const input: SampleInput[] = [
      ["2025-01-01T10:02:00Z", 0],   // 10:00 bin becomes missing
      ["2025-01-01T10:32:00Z", 40],  // 10:30 bin
    ];

    const out = resampleTimeSeries(input, {
      intervalMinutes: 15,
      timeZone: "UTC",
      outputInTimeZone: false,
      skipZeros: true,
    });

    expectSeries(out, [
      ["2025-01-01T10:00:00Z", 40],
      ["2025-01-01T10:15:00Z", 40],
      ["2025-01-01T10:30:00Z", 40],
    ]);
  });

  it("0-values: skipZeros=false keeps 0 and interpolates", () => {
    const input: SampleInput[] = [
      ["2025-01-01T10:02:00Z", 0],
      ["2025-01-01T10:32:00Z", 40],
    ];

    const out = resampleTimeSeries(input, {
      intervalMinutes: 15,
      timeZone: "UTC",
      outputInTimeZone: false,
      skipZeros: false,
    });

    expectSeries(out, [
      ["2025-01-01T10:00:00Z", 0],
      ["2025-01-01T10:15:00Z", 20],
      ["2025-01-01T10:30:00Z", 40],
    ]);
  });

  it("truncation: timestamps floor into bin-starts", () => {
    const input: SampleInput[] = [
      ["2025-01-01T10:14:59Z", 5],  // -> 10:00
      ["2025-01-01T10:15:01Z", 15], // -> 10:15
    ];

    const out = resampleTimeSeries(input, {
      intervalMinutes: 15,
      timeZone: "UTC",
      outputInTimeZone: false,
    });

    expectSeries(out, [
      ["2025-01-01T10:00:00Z", 5],
      ["2025-01-01T10:15:00Z", 15],
    ]);
  });

  it("mean aggregation: multiple points in same bin average", () => {
    const input: SampleInput[] = [
      ["2025-01-01T10:01:00Z", 10],
      ["2025-01-01T10:10:00Z", 20], // same 10:00 bin
      ["2025-01-01T10:16:00Z", 30], // 10:15 bin
    ];

    const out = resampleTimeSeries(input, {
      intervalMinutes: 15,
      timeZone: "UTC",
      outputInTimeZone: false,
    });

    expectSeries(out, [
      ["2025-01-01T10:00:00Z", 15],
      ["2025-01-01T10:15:00Z", 30],
    ]);
  });
});
