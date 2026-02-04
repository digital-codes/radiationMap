<script setup lang="ts">
import Map from './components/SimpleMap.vue'
import Chart from './components/SimpleLine.vue'
import { resampleTimeSeries } from './services/resample.ts'
import type { SampleInput, SampleOutput } from './services/resample.ts'
import {ref} from 'vue'
import L from "leaflet";

// map stuff
const mapDataProps = {
  "name":"sensor_id", "date":"timestamp","value":"count_per_minute"
}; 

const sensorUrl = ref("/data/radiationLatest.geojson");
const plantUrl = ref("/data/nuclear_facilities_clean.geojson");
const windUrl = ref("/data/wind.geojson");

const chartTitle = ref("Multi-Geiger Sensor Data");
const dataUrl = ref("/data/sensor/series_month_57613.json");

const sensorClicked = (sensorId: string) => {
  console.log("Sensor clicked in parent:", sensorId);
  chartTitle.value = `Sensor ${sensorId}`;
  const filename = `/data/sensor/series_month_${sensorId}.json`;
  console.log("Loading data from:", filename);
  dataUrl.value = filename;
};

const plantClicked = (plantName: string) => {
  console.log("Plant clicked in parent:", plantName);
};

const dataLoaded = (payload: { content: any; id: HTMLElement | null; L: typeof L | null; map: any | null }) => {
  console.log("Data loaded in parent:", payload);
};

// sampling test stuff
const output = ref<SampleOutput[]>([])

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
  <div class="app">
    <div class="hdr">
    <h2>Geiger Map</h2>
    <p>Use layer controls to toggle map layers. Wind only for zoom levels 1-6. Click on sensor to show timeseries</p>
    </div>
    <div class="map">
    <Map title="Multi-Geiger2"
    :sensorUrl="sensorUrl" 
    :plantUrl="plantUrl" 
    :windUrl="windUrl" 
    :tileIdx="5"
    :dataProps="mapDataProps"
    @sensor_click="sensorClicked"
    @plant_click="plantClicked"
    @data="dataLoaded"
    />
  </div>
    <div class="chart">
    <Chart 
    :title="chartTitle"
    :dataUrl="dataUrl" 
    />
  </div>
    <div class="ftr">
    <p>Imprint: bla bla</p>
    <p><a href="https://github.com/digital-codes/radiationMap/" target="_blank" rel="noopener noreferrer">GitHub Repository</a></p>
    </div>
  </div>
  <!--  
  <HelloWorld msg="Empty template" />
  -->
</template>

<style scoped>

.app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 0px;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  max-width:1200px;
  margin-left: auto;
  margin-right: auto;
  box-sizing: border-box;
  padding:0;
  padding-left:1rem;
  padding-right:1rem;
  box-sizing: border-box;
}

.map {
  min-height: 300px;
  width:100%;
  height: 50%;
  box-sizing: border-box;
}

.chart {
  min-height: 200px;
  width:100%;
  height: 30%;
  box-sizing: border-box;
}

.hdr, .ftr {
  line-height: 1.15em;
  margin: 0;
  padding: .2em;
  background-color: #f0f0f0;
  height:10%;
  overflow: hidden;
  box-sizing: border-box;
}

.hdr p, .ftr p {
  margin: 0;
  padding: 0;
  font-size: 1rem;
}

.hdr h2 {
  margin: 0;
  padding: 0;
  font-size: 1.2rem;
}

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
</style>
