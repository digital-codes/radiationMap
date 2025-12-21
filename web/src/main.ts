import './style.css'

import {resampleTimeSeries} from './resample.ts'

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <div>
    <h1>Resampling</h1>
    <p id="output" class="read-the-docs">
      Click on the Vite and TypeScript logos to learn more
    </p>
  </div>
`

const input: SampleInput[] = [
  ["2025-12-21T10:02:00+01:00", "5"],
  ["2025-12-21T10:09:00+01:00", 7],
  ["2025-12-21T10:07:00+01:00", 3],
  ["2025-12-21T10:31:00+01:00", 17],
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
document.querySelector<HTMLParagraphElement>('#output')!.innerText = JSON.stringify(res, null, 2)
