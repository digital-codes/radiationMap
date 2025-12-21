// Dependencies (allowed by your note):
//   npm i date-fns date-fns-tz
//
// What this does (pandas-like):
// - parse timestamps (ISO string / ms / Date), drop invalid
// - optional lookback cutoff (N days)
// - sort
// - resample to fixed interval bins in a *timezone-aware* way (bins aligned in the given timeZone)
// - mean aggregation if multiple points land in a bin
// - numeric coercion; non-numeric -> missing
// - optional: treat 0 as missing (skipZeros)
// - interpolate internal gaps (linear by time)
// - forward-fill + back-fill edges
//
// Input: Array<[timestamp, value]>
// Output: Array<[timestampISO, value]> (timestamp is bin-start)

import { parseISO, isValid as isValidDate, subDays } from "date-fns";
import { toZonedTime, fromZonedTime, formatInTimeZone } from "date-fns-tz";

export type TimestampInput = string | number | Date;
export type SampleInput = readonly [TimestampInput, unknown];
export type SampleOutput = readonly [string, number];

export interface ResampleOptions {
    intervalMinutes?: number; // default 15
    lookbackDays?: number; // default Infinity
    skipZeros?: boolean; // default false
    timeZone?: string; // default "UTC"
    outputInTimeZone?: boolean; // default true (ISO with TZ offset)
    extendToNow?: boolean; // default false
}

function toNumberOrNull(x: unknown): number | null {
    if (x === null || x === undefined) return null;
    if (typeof x === "number") return Number.isFinite(x) ? x : null;
    if (typeof x === "string") {
        const v = Number(x.trim());
        return Number.isFinite(v) ? v : null;
    }
    return null;
}

function hasExplicitOffsetOrZ(s: string): boolean {
    return /[zZ]$/.test(s) || /([+\-]\d{2}:\d{2}|[+\-]\d{4})$/.test(s);
}

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

        // With offset/Z => absolute instant
        if (hasExplicitOffsetOrZ(s)) {
            const d = parseISO(s);
            return isValidDate(d) ? d : null;
        }

        // No offset => interpret as wall-clock in timeZone
        try {
            const utc = fromZonedTime(s, timeZone);
            return isValidDate(utc) ? utc : null;
        } catch {
            return null;
        }
    }
    return null;
}

/**
 * Floor an instant to the start of the interval bin aligned to the given timeZone.
 * Uses: toZonedTime + fromZonedTime (date-fns-tz v3+)
 */
function pad2(n: number): string {
    return n.toString().padStart(2, "0");
}
function pad3(n: number): string {
    return n.toString().padStart(3, "0");
}

/**
 * Floor an instant to the start of the interval bin aligned to the given timeZone.
 * Correctly independent of the machine's local timezone.
 */
function floorToIntervalInTZ(
    utcInstant: Date,
    intervalMinutes: number,
    timeZone: string
): Date {
    const zoned = toZonedTime(utcInstant, timeZone);

    // IMPORTANT: use wall-clock fields (local getters) of the "zoned" Date
    // Do NOT use zoned.getTime() for flooring; it's shifted and depends on system TZ.
    const year = zoned.getFullYear();
    const month = zoned.getMonth() + 1; // 1-12
    const day = zoned.getDate();
    const hour = zoned.getHours();
    const minute = zoned.getMinutes();

    const flooredMinute = Math.floor(minute / intervalMinutes) * intervalMinutes;

    // Build a wall-clock timestamp string (no offset) in the target timeZone, then convert to UTC instant.
    const wall =
        `${year}-${pad2(month)}-${pad2(day)}T` +
        `${pad2(hour)}:${pad2(flooredMinute)}:00.${pad3(0)}`;

    return fromZonedTime(wall, timeZone);
}

function mean(arr: number[]): number | null {
    if (arr.length === 0) return null;
    let sum = 0;
    for (const v of arr) sum += v;
    return sum / arr.length;
}

function interpolateLinearByTime(
    tsMs: number[],
    ys: Array<number | null>
): Array<number | null> {
    const out = ys.slice();

    let i = 0;
    while (i < out.length) {
        if (out[i] !== null) {
            i++;
            continue;
        }

        const left = i - 1;
        let right = i;
        while (right < out.length && out[right] === null) right++;

        if (left >= 0 && right < out.length) {
            const t0 = tsMs[left],
                t1 = tsMs[right];
            const y0 = out[left] as number,
                y1 = out[right] as number;
            const dt = t1 - t0;

            if (dt > 0) {
                for (let k = left + 1; k < right; k++) {
                    const a = (tsMs[k] - t0) / dt;
                    out[k] = y0 + a * (y1 - y0);
                }
            }
        }

        i = right;
    }

    return out;
}

function forwardFill(ys: Array<number | null>): Array<number | null> {
    const out = ys.slice();
    let last: number | null = null;
    for (let i = 0; i < out.length; i++) {
        if (out[i] === null) out[i] = last;
        else last = out[i];
    }
    return out;
}

function backFill(ys: Array<number | null>): Array<number | null> {
    const out = ys.slice();
    let next: number | null = null;
    for (let i = out.length - 1; i >= 0; i--) {
        if (out[i] === null) out[i] = next;
        else next = out[i];
    }
    return out;
}

function formatBinStart(
    binStartUtc: Date,
    timeZone: string,
    outputInTimeZone: boolean
): string {
    if (!outputInTimeZone) return binStartUtc.toISOString();
    return formatInTimeZone(binStartUtc, timeZone, "yyyy-MM-dd'T'HH:mm:ssXXX");
}

export function resampleTimeSeries(
    input: readonly SampleInput[],
    opts: ResampleOptions = {}
): SampleOutput[] {
    const intervalMinutes = opts.intervalMinutes ?? 15;
    const lookbackDays = opts.lookbackDays ?? Infinity;
    const skipZeros = opts.skipZeros ?? false;
    const timeZone = opts.timeZone ?? "UTC";
    const outputInTimeZone = opts.outputInTimeZone ?? true;
    const extendToNow = opts.extendToNow ?? false;

    // 1) Parse + numeric coercion
    const parsed: Array<{ tUtc: Date; v: number | null }> = [];
    for (const [tRaw, vRaw] of input) {
        const tUtc = parseToUtcDate(tRaw, timeZone);
        if (!tUtc) continue;

        let v = toNumberOrNull(vRaw);
        if (v !== null && skipZeros && v === 0) v = null;

        parsed.push({ tUtc, v });
    }
    if (parsed.length === 0) return [];

    // 2) Cutoff
    if (Number.isFinite(lookbackDays)) {
        const nowZoned = toZonedTime(new Date(), timeZone);
        const cutoffZoned = subDays(nowZoned, lookbackDays);

        const cutoffWall = formatInTimeZone(
            cutoffZoned,
            timeZone,
            "yyyy-MM-dd'T'HH:mm:ss.SSS"
        );
        const cutoffUtc = fromZonedTime(cutoffWall, timeZone);

        for (let i = parsed.length - 1; i >= 0; i--) {
            if (parsed[i].tUtc.getTime() < cutoffUtc.getTime()) parsed.splice(i, 1);
        }
        if (parsed.length === 0) return [];
    }

    // 3) Sort
    parsed.sort((a, b) => a.tUtc.getTime() - b.tUtc.getTime());

    // 4) Bin range aligned in TZ
    const intervalMs = intervalMinutes * 60_000;

    const firstBinUtc = floorToIntervalInTZ(
        parsed[0].tUtc,
        intervalMinutes,
        timeZone
    );
    const lastSampleBinUtc = floorToIntervalInTZ(
        parsed[parsed.length - 1].tUtc,
        intervalMinutes,
        timeZone
    );

    let lastBinUtc = lastSampleBinUtc;
    if (extendToNow) {
        const nowBinUtc = floorToIntervalInTZ(new Date(), intervalMinutes, timeZone);
        if (nowBinUtc.getTime() > lastBinUtc.getTime()) lastBinUtc = nowBinUtc;
    }

    const binCount =
        Math.floor((lastBinUtc.getTime() - firstBinUtc.getTime()) / intervalMs) + 1;
    if (binCount <= 0) return [];

    // Collect values per bin (mean aggregation)
    const buckets: number[][] = Array.from({ length: binCount }, () => []);
    for (const p of parsed) {
        const binStartUtc = floorToIntervalInTZ(
            p.tUtc,
            intervalMinutes,
            timeZone
        );
        const idx = Math.floor(
            (binStartUtc.getTime() - firstBinUtc.getTime()) / intervalMs
        );
        if (idx < 0 || idx >= binCount) continue;

        if (p.v !== null && Number.isFinite(p.v)) buckets[idx].push(p.v);
    }

    const tsMs: number[] = new Array(binCount);
    const ys: Array<number | null> = new Array(binCount);

    for (let i = 0; i < binCount; i++) {
        tsMs[i] = firstBinUtc.getTime() + i * intervalMs;
        ys[i] = mean(buckets[i]);
    }

    // Nothing to save?
    let any = false;
    for (const y of ys) {
        if (y !== null) {
            any = true;
            break;
        }
    }
    if (!any) return [];

    // 5) Interpolate + edge fills
    let filled = interpolateLinearByTime(tsMs, ys);
    filled = forwardFill(filled);
    filled = backFill(filled);

    // 6) Output
    const out: SampleOutput[] = [];
    for (let i = 0; i < binCount; i++) {
        const y = filled[i];
        if (typeof y !== "number" || !Number.isFinite(y)) continue;
        out.push([
            formatBinStart(new Date(tsMs[i]), timeZone, outputInTimeZone),
            y,
        ]);
    }
    return out;
}


/* Example
const input: SampleInput[] = [
  ["2025-12-21T10:02:00+01:00", "5"],
  ["2025-12-21T10:09:00+01:00", 7],
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
});
console.log(res);
*/
