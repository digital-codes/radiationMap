/**
 * Time-series resampling with timezone-aware bin alignment.
 *
 * Goals
 * - Accept mixed timestamp inputs (ISO string / ms / Date)
 * - Interpret "naive" strings (no Z/offset) as wall-clock time in `timeZone`
 * - Resample into fixed bins aligned to the wall-clock of `timeZone`
 * - Mean aggregation per bin, then gap handling:
 *    - optional treat 0 as missing (`skipZeros`)
 *    - linear interpolation of internal gaps
 *    - forward-fill and back-fill at the edges
 *
 * Input
 *   Array<[timestamp, value]>
 *
 * Output
 *   Array<[binStartISO, value]>
 *   - binStartISO is bin start, formatted in `timeZone` (default) or UTC
 *   - value is number | null
 *
 * Notes on date-fns-tz compatibility
 * - date-fns-tz v2: utcToZonedTime / zonedTimeToUtc
 * - date-fns-tz v3+: toZonedTime / fromZonedTime
 */

import { parseISO, formatISO, isValid } from "date-fns";
import * as tz from "date-fns-tz";

// -----------------------------
// date-fns-tz compatibility layer
// -----------------------------
type ToZonedTimeFn = (date: Date | number, timeZone: string) => Date;
type FromZonedTimeFn = (date: Date | string | number, timeZone: string) => Date;
type FormatInTimeZoneFn = (date: Date | number, timeZone: string, formatStr: string) => string;

const toZonedTime = (
  (tz as unknown as { toZonedTime?: ToZonedTimeFn; utcToZonedTime?: ToZonedTimeFn }).toZonedTime ??
  (tz as unknown as { utcToZonedTime: ToZonedTimeFn }).utcToZonedTime
) as ToZonedTimeFn;

const fromZonedTime = (
  (tz as unknown as { fromZonedTime?: FromZonedTimeFn; zonedTimeToUtc?: FromZonedTimeFn }).fromZonedTime ??
  (tz as unknown as { zonedTimeToUtc: FromZonedTimeFn }).zonedTimeToUtc
) as FromZonedTimeFn;

const formatInTimeZone =
  (tz as unknown as { formatInTimeZone: FormatInTimeZoneFn }).formatInTimeZone as FormatInTimeZoneFn;

// -----------------------------
// Types
// -----------------------------
export type TimestampInput = string | number | Date;

export type SampleInput = readonly [TimestampInput, unknown];
export type SampleOutput =  [string, number | null];


export interface ResampleOptions {
  /** Bin size in minutes. Default: 15 */
  intervalMinutes?: number;

  /**
   * Lookback window in days, counted backwards from the effective `end` (or latest sample).
   * Default: Infinity (no cutoff)
   */
  lookbackDays?: number;

  /** If true, treat numeric 0 as missing (null). Default: false */
  skipZeros?: boolean;

  /** Timezone for bin alignment + formatting. Default: "UTC" */
  timeZone?: string;

  /** If true, output timestamps in `timeZone` offset. If false, output UTC ISO. Default: true */
  outputInTimeZone?: boolean;

  /** If true, extend bins to "now" (floored to the interval) in `timeZone`. Default: false */
  extendToNow?: boolean;

  /**
   * Optional explicit start bound for bins (inclusive).
   * - If a string has no offset/Z, it's interpreted as wall-clock in `timeZone`.
   */
  start?: TimestampInput;

  /**
   * Optional explicit end bound for bins (inclusive).
   * - If a string has no offset/Z, it's interpreted as wall-clock in `timeZone`.
   */
  end?: TimestampInput;
}

// -----------------------------
// Public API
// -----------------------------

/**
 * Resample an irregular time series to fixed bins aligned in a given time zone.
 */
export function resampleTimeSeries(
  data: readonly SampleInput[],
  opts: ResampleOptions = {}
): SampleOutput[] {
  const intervalMinutes = opts.intervalMinutes ?? 15;
  const timeZone = opts.timeZone ?? "UTC";
  const lookbackDays = opts.lookbackDays ?? Infinity;
  const skipZeros = opts.skipZeros ?? false;
  const outputInTimeZone = opts.outputInTimeZone ?? true;
  const extendToNow = opts.extendToNow ?? false;

  if (!Number.isFinite(intervalMinutes) || intervalMinutes <= 0) return [];

  // 1) Parse + coerce inputs to {tUtc, v}
  const parsed: ParsedPoint[] = [];
  for (const row of data) {
    const tUtc = parseToUtcDate(row[0], timeZone);
    if (!tUtc) continue;

    const v = coerceValue(row[1], { skipZeros });
    parsed.push({ tUtc, v });
  }
  if (parsed.length === 0) return [];

  // 2) Sort by time
  parsed.sort((a, b) => a.tUtc.getTime() - b.tUtc.getTime());

  // 3) Determine effective [start, end] bounds (UTC instants)
  const explicitStart = opts.start ? parseToUtcDate(opts.start, timeZone) : null;
  const explicitEnd = opts.end ? parseToUtcDate(opts.end, timeZone) : null;

  // End bound preference: explicit end -> extendToNow -> latest sample's bin
  const intervalMs = intervalMinutes * 60_000;

  const latestSample = parsed[parsed.length - 1]!;
  const latestSampleBinUtc = floorToIntervalInTZ(latestSample.tUtc, intervalMinutes, timeZone);

  let endBinUtc = explicitEnd
    ? floorToIntervalInTZ(explicitEnd, intervalMinutes, timeZone)
    : latestSampleBinUtc;

  if (extendToNow) {
    const nowBinUtc = floorToIntervalInTZ(new Date(), intervalMinutes, timeZone);
    if (nowBinUtc.getTime() > endBinUtc.getTime()) endBinUtc = nowBinUtc;
  }

  // Start bound preference: explicit start -> lookback -> earliest sample's bin
  const earliestSample = parsed[0]!;
  const earliestSampleBinUtc = floorToIntervalInTZ(earliestSample.tUtc, intervalMinutes, timeZone);

  let startBinUtc = explicitStart
    ? floorToIntervalInTZ(explicitStart, intervalMinutes, timeZone)
    : earliestSampleBinUtc;

  if (Number.isFinite(lookbackDays) && lookbackDays !== Infinity) {
    const cutoffUtc = new Date(endBinUtc.getTime() - lookbackDays * 24 * 60 * 60_000);

    // Drop points before cutoff (in-place, backwards for splice safety + TS)
    for (let i = parsed.length - 1; i >= 0; i--) {
      const p = parsed[i];
      if (!p) continue;
      if (p.tUtc.getTime() < cutoffUtc.getTime()) parsed.splice(i, 1);
    }
    if (parsed.length === 0) return [];

    // Recompute from remaining data unless explicitStart provided
    if (!explicitStart) {
      const newEarliest = parsed[0]!;
      startBinUtc = floorToIntervalInTZ(newEarliest.tUtc, intervalMinutes, timeZone);
    }
  }

  // Ensure start <= end
  if (startBinUtc.getTime() > endBinUtc.getTime()) return [];

  // 4) Create bins
  const binCount = Math.floor((endBinUtc.getTime() - startBinUtc.getTime()) / intervalMs) + 1;
  if (binCount <= 0) return [];

  const binStartsUtcMs: number[] = new Array(binCount);
  for (let i = 0; i < binCount; i++) {
    binStartsUtcMs[i] = startBinUtc.getTime() + i * intervalMs;
  }

  // 5) Aggregate samples into bins (mean)
  const buckets: number[][] = Array.from({ length: binCount }, () => []);
  for (const p of parsed) {
    const binStartUtc = floorToIntervalInTZ(p.tUtc, intervalMinutes, timeZone);
    const idx = Math.floor((binStartUtc.getTime() - startBinUtc.getTime()) / intervalMs);
    if (idx < 0 || idx >= binCount) continue;
    
    const v = p.v;
    if (v !== null && Number.isFinite(v)) {
      const bucket = buckets[idx];
      if (bucket) bucket.push(v);
    }
  }

  const ys: Array<number | null> = new Array(binCount).fill(null);
  for (let i = 0; i < binCount; i++) {
    const arr = buckets[i] ?? [];
    ys[i] = arr.length ? mean(arr) : null;
  }

  // 6) Interpolate internal gaps + fill edges
  const tsMs = binStartsUtcMs;
  const interpolated = linearInterpolateNulls(tsMs, ys);
  const filled = backFill(forwardFill(interpolated));

  // 7) Format output
  const out: SampleOutput[] = new Array(binCount);
  for (let i = 0; i < binCount; i++) {
    const t = tsMs[i];
    if (t === undefined) continue; // defensive for noUncheckedIndexedAccess
    out[i] = [formatBinStart(new Date(t), timeZone, outputInTimeZone), filled[i] ?? null];
  }

  // Filter out any holes (shouldn't happen, but TS allows it due to continue)
  return out.filter((x): x is SampleOutput => Array.isArray(x));
}

// -----------------------------
// Internals
// -----------------------------
type ParsedPoint = { tUtc: Date; v: number | null };

function isValidDate(d: Date): boolean {
  return isValid(d) && !Number.isNaN(d.getTime());
}

function hasExplicitOffsetOrZ(s: string): boolean {
  return /[zZ]$/.test(s) || /([+\-]\d{2}:\d{2}|[+\-]\d{4})$/.test(s);
}

/**
 * Parse a timestamp into a UTC Date.
 * - Date: cloned
 * - number: ms since epoch
 * - string:
 *    - with Z/offset => parsed as absolute instant
 *    - without Z/offset => interpreted as wall-clock in `timeZone`
 */
function parseToUtcDate(t: TimestampInput, timeZone: string): Date | null {
  if (t instanceof Date) {
    const d = new Date(t.getTime());
    return isValidDate(d) ? d : null;
  }
  if (typeof t === "number") {
    const d = new Date(t);
    return isValidDate(d) ? d : null;
  }
  if (typeof t === "string") {
    const s = t.trim();
    if (!s) return null;

    if (hasExplicitOffsetOrZ(s)) {
      const d = parseISO(s);
      return isValidDate(d) ? d : null;
    }

    // naive timestamp -> wall-clock in timeZone
    try {
      const utc = fromZonedTime(s, timeZone);
      return isValidDate(utc) ? utc : null;
    } catch {
      return null;
    }
  }
  return null;
}

function coerceValue(v: unknown, { skipZeros }: { skipZeros: boolean }): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return null;
    if (skipZeros && v === 0) return null;
    return v;
  }
  if (typeof v === "string") {
    const s = v.trim();
    if (!s) return null;
    const n = Number(s);
    if (!Number.isFinite(n)) return null;
    if (skipZeros && n === 0) return null;
    return n;
  }
  return null;
}

/**
 * Floor a UTC instant to the interval boundary *in the target time zone*.
 * This aligns bins to the wall-clock of `timeZone` (including DST transitions).
 */
function floorToIntervalInTZ(dUtc: Date, intervalMinutes: number, timeZone: string): Date {
  // Convert UTC instant to zoned wall-clock
  const zoned = toZonedTime(dUtc, timeZone);

  const ms = zoned.getTime();
  const intervalMs = intervalMinutes * 60_000;
  const flooredMs = Math.floor(ms / intervalMs) * intervalMs;
  const zonedFloored = new Date(flooredMs);

  // Convert zoned wall-clock back to UTC instant
  return fromZonedTime(zonedFloored, timeZone);
}

function mean(xs: number[]): number {
  let sum = 0;
  for (const x of xs) sum += x;
  return sum / xs.length;
}

/**
 * Linear interpolation of internal null-runs.
 * - Only interpolates between two known values.
 * - Does not extrapolate beyond edges (edges are handled by fills).
 */
function linearInterpolateNulls(tsMs: number[], ys: Array<number | null>): Array<number | null> {
  const out = ys.slice();

  // Find segments of nulls between two known values
  let i = 0;
  while (i < out.length) {
    if (out[i] !== null) {
      i++;
      continue;
    }

    // left boundary
    const left = i - 1;
    // find right boundary
    let right = i;
    while (right < out.length && out[right] === null) right++;

    // Interpolate only if bounded on both sides
    if (left >= 0 && right < out.length) {
      const y0 = out[left];
      const y1 = out[right];
      const t0 = tsMs[left];
      const t1 = tsMs[right];

      if (y0 !== null && y0 !== undefined && y1 !== null && y1 !== undefined && t0 !== undefined && t1 !== undefined) {
        const dt = t1 - t0;
        if (dt > 0) {
          for (let k = left + 1; k < right; k++) {
            const tk = tsMs[k];
            if (tk === undefined) continue;
            const a = (tk - t0) / dt;
            out[k] = y0 + a * (y1 - y0);
          }
        }
      }
    }

    i = right;
  }

  return out;
}

/** Forward-fill: replace nulls with the last non-null value (no extrapolation for leading nulls). */
function forwardFill(ys: Array<number | null>): Array<number | null> {
  const out = ys.slice();
  let last: number | null = null;
  for (let i = 0; i < out.length; i++) {
    const v = out[i] ?? null; // defensive for noUncheckedIndexedAccess
    if (v === null) out[i] = last;
    else last = v;
  }
  return out;
}

/** Back-fill: replace nulls with the next non-null value (no extrapolation for trailing nulls). */
function backFill(ys: Array<number | null>): Array<number | null> {
  const out = ys.slice();
  let next: number | null = null;
  for (let i = out.length - 1; i >= 0; i--) {
    const v = out[i] ?? null; // defensive for noUncheckedIndexedAccess
    if (v === null) out[i] = next;
    else next = v;
  }
  return out;
}

/**
 * Format bin start:
 * - outputInTimeZone=true: ISO string with `timeZone` offset (no milliseconds)
 * - outputInTimeZone=false: UTC ISO string
 */
function formatBinStart(dUtc: Date, timeZone: string, outputInTimeZone: boolean): string {
  if (!outputInTimeZone) return formatISO(dUtc);
  // yyyy-MM-dd'T'HH:mm:ssXXX
  return formatInTimeZone(dUtc, timeZone, "yyyy-MM-dd'T'HH:mm:ssXXX");
}

/*
Example:

const input: Array<[string, number | string | null]> = [
  ["2025-12-21T10:02:00+01:00", 1],
  ["2025-12-21T10:06:00+01:00", 2],
  ["2025-12-21 10:20:00", "3.5"], // naive -> interpreted in timeZone
  ["2025-12-21T10:40:00+01:00", 0],
  ["bad", 1],
];

// 15-min bins aligned in Europe/Berlin wall-clock, interpolate missing, treat zeros as missing:
const res = resampleTimeSeries(input, {
  intervalMinutes: 15,
  lookbackDays: 7,
  skipZeros: true,
  timeZone: "Europe/Berlin",
  outputInTimeZone: true,

  // optional explicit bounds:
  // start: "2025-12-21 10:00:00",
  // end:   "2025-12-21 12:00:00",
});
console.log(res);
*/
