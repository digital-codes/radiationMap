<script setup lang="ts">
import HelloWorld from './components/HelloWorld.vue'
import Map from './components/GeoMapSimple.vue'
import Map2 from './components/SimpleMap.vue'
import {resampleTimeSeries} from './resample.ts'
import {ref} from 'vue'
const output = ref<[string, number][]>([])

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

output.value = res;

</script>

<template>
  <div>
    <h2>Multi-Geiger Followup Test</h2>
    <p>{{ output }}</p>
    <!--
    <Map title="Multi-Geiger"/>
    -->
    <div class="card">
    <Map2 title="Multi-Geiger2"
    dataUrl="/data/radiationLatest.geojson" 
    tileIdx="5"
    />
  </div>
  </div>
  <!--  
  <HelloWorld msg="Empty template" />
  -->
</template>

<style scoped>
.logo {
  height: 6em;
  padding: 1.5em;
  will-change: filter;
  transition: filter 300ms;
}
.logo:hover {
  filter: drop-shadow(0 0 2em #646cffaa);
}
.logo.vue:hover {
  filter: drop-shadow(0 0 2em #42b883aa);
}
.card {
  height: 400px;
}
</style>
