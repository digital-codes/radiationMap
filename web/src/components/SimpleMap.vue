<template>
  <div class="container">
    <div class="map" ref="theMap"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue";
import L from "leaflet";
import type { Map as LeafletMap, TileLayer as LeafletTileLayer, GeoJSON as LeafletGeoJSON, ImageOverlay as LeafletImageOverlay } from "leaflet";
import "leaflet/dist/leaflet.css";

// coordinate conversion
import proj4 from "proj4";

import { attachUWindOverlay } from "../services/WindOverlay";
//import { addUWindOverlay } from "../services/uWindOverlay"; // adjust path
// let removeWind: (() => void) | null = null;

//import { attachVelocityOverlay } from "../services/VelocityOverlay";

import type { FeatureCollection } from "geojson";

const emit = defineEmits<{
  data: [payload: { content: FeatureCollection | null; id: HTMLElement | null; L: typeof L | null; map: LeafletMap | null }];
  sensor_click: [sensorId: string];
}>();

const props = defineProps<{
  tileIdx?: number;
  dataUrl: string;
  dataName?: string;
  ariaLabel?: string;
  dataX?: string;
  dataY?: string;
  labelX?: string;
  labelY?: string;
  dataFormat?: string;
  dataDelimiter?: string;
  dataProps?: Record<string, string>;
  locale?: string;
}>();


const mapInstance = ref<LeafletMap | null>(null);
const theMap = ref<HTMLElement | null>(null);
const Lref = ref<typeof L | null>(null);
const tileLayer = ref<LeafletTileLayer | null>(null);
const geoLayer = ref<LeafletGeoJSON | null>(null);
const windLayer = ref<LeafletImageOverlay | null>(null);

// Helper function to safely cast map instance
//const safeMap = () => mapInstance.value as LeafletMap;


// EPSG is frequently used in Germany
const EPSG25832 = "+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs";
// EPSG4326 is WGS84, default for Leaflet
const EPSG4326 = "+proj=longlat +datum=WGS84 +no_defs";

// Import Leaflet marker images
/*
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
*/


const geojsonData = ref<FeatureCollection | null>(null);

const tileSource = [
  {
    name: "osm",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr: "© OpenStreetMap contributors",
  },
  {
    name: "stadiaOsm",
    url: "https://tiles-eu.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}@2x.png",
    attr:
      '\
      &copy; <a href="https://stadiamaps.com/" target="_blank">Stadia Maps</a>|\
      &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a>|\
      &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>\
      ',
  },
  {
    name: "BaseMapDE",
    url: "https://sgx.geodatenzentrum.de/wmts_basemapde/tile/1.0.0/de_basemapde_web_raster_farbe/default/GLOBAL_WEBMERCATOR/{z}/{y}/{x}.png",
    attr:
      '\
&copy; <a href="https://www.bkg.bund.de" target="_blank">GeoBasis-DE/BKG (' +
      new Date().getFullYear() +
      ')</a>|\
<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank">CC BY 4.0</a>\
',
  },
  {
    name: "GeoPortal KA Raster",
    url: "https://geoportal.karlsruhe.de/ags04/rest/services/Hosted/Regiokarte_farbig_Raster/MapServer/tile/{z}/{y}/{x}",
    attr:
      "Esri Community Maps Contributors, LVermGeo RP, Esri, TomTom, Garmin, GeoTechnologies, Inc, METI/NASA, USGS | © Stadt Karlsruhe | Liegenschaftsamt",
  },
  {
    name: "GeoPortal KA Luftbilder",
    url: "https://geoportal.karlsruhe.de/ags04/rest/services/Luftbilder2024_Cache/MapServer/tile/{z}/{y}/{x}",
    attr:
      "Esri Community Maps Contributors, LVermGeo RP, Esri, TomTom, Garmin, GeoTechnologies, Inc, METI/NASA, USGS | © Stadt Karlsruhe | Liegenschaftsamt",
  },
  {
    name: "BKG World",
    url: "https://sgx.geodatenzentrum.de/wmts_topplus_open/tile/1.0.0/web/default/WEBMERCATOR/{z}/{y}/{x}.png",
    attr:
      '\
&copy; <a href="https://www.bkg.bund.de" target="_blank">GeoBasis-DE/BKG (' +
      new Date().getFullYear() +
      ')</a>| \
<a href="https://www.govdata.de/dl-de/by-2-0" target="_blank">Datenlizenz Deutschland - Namensnennung - Version 2.0</a>\
',
  },
];

// default values for props are handled by defineProps defaults in SFC usage, but ensure local fallbacks if needed
const tileIdx = (() => {
  const defaultIdx = 2;
  const raw = typeof props.tileIdx === "number" && Number.isFinite(props.tileIdx) ? Math.floor(props.tileIdx) : defaultIdx;
  return Math.max(0, Math.min(raw, tileSource.length - 1));
})();


watch(
  () => props.dataUrl,
  async (newVal, oldVal) => {
    console.log("Data URL changed", newVal, oldVal);
    await loadData(newVal);
  }
);

const loadData = async (dataUrl: string): Promise<void> => {
  console.log("Fetching data from", dataUrl);
  const response = await fetch(dataUrl);
  if (!response.ok) {
    throw new Error("Network response was not ok from " + dataUrl);
  }
  geojsonData.value = (await response.json()) as FeatureCollection;
  // limit number of features
  const features = geojsonData.value.features;
  const maxFeatures = 100;
  if (features.length > maxFeatures) {
    geojsonData.value.features = features.slice(0, maxFeatures);
    console.log(`Only first ${maxFeatures} features are loaded.`);
  }

  // check crs: if not WGS84, transform to WGS84
  // note: many GeoJSON files do not include `crs`; this code keeps compatibility
  const crs = (geojsonData.value as any).crs;
  console.log("CRS:", crs);
  if (crs && crs.properties) {
    const crsName = crs.properties.name as string | undefined;
    console.log("CRS:", crsName, crs);
    if (crsName && crsName.toLowerCase().includes("epsg") && crsName.includes("25832")) {
      console.log("Transforming from", crsName);
      // make sure to update crs else will be transformed again on reload
      crs.properties.name = "WGS84";
      const featuresLocal = geojsonData.value.features;

      for (const f of featuresLocal) {
        const geom = f.geometry;
        if (!geom) continue;
        if (geom.type === "Point") {
          const coords = geom.coordinates as [number, number];
          const transformed = proj4(EPSG25832, EPSG4326, coords) as [number, number];
          geom.coordinates = transformed;
        }
        if (geom.type === "LineString") {
          const coords = geom.coordinates as [number, number][];
          for (let i = 0; i < coords.length; i++) {
            if (coords[i]) {
              const transformed = proj4(EPSG25832, EPSG4326, coords[i]!) as [number, number];
              coords[i] = transformed;
            }
          }
        }
        if (geom.type === "Polygon") {
          const coords = geom.coordinates as [number, number][][]; // rings
          if (Array.isArray(coords)) {
            for (let j = 0; j < coords.length; j++) {
              const ring = coords[j];
              if (!Array.isArray(ring)) continue;
              for (let i = 0; i < ring.length; i++) {
                const pt = ring[i];
                if (!pt || typeof pt[0] !== "number" || typeof pt[1] !== "number") continue;
                const transformed = proj4(EPSG25832, EPSG4326, pt) as [number, number];
                ring[i] = transformed;
              }
            }
          }
        }
      }
    }
  }

  if (geoLayer.value && mapInstance.value as any) {
    geoLayer.value.removeFrom(mapInstance.value as any);
  }

  // create geojson layer
  geoLayer.value = Lref.value!.geoJSON(geojsonData.value, {
    onEachFeature: (feature, layer) => {
      if (feature.properties && feature.properties[(props.dataProps && props.dataProps["name"]) || "name"]) {
        let popupContent = "<b>" + feature.properties[(props.dataProps && props.dataProps["name"]) || "name"] + "</b><br>";
        if (feature.properties[(props.dataProps && props.dataProps["description"]) || "description"])
          popupContent += feature.properties[(props.dataProps && props.dataProps["description"]) || "description"] + "<br>";
        if (feature.properties[(props.dataProps && props.dataProps["date"]) || "date"] && feature.properties[(props.dataProps && props.dataProps["value"]) || "value"])
          popupContent += "Date: " + feature.properties[(props.dataProps && props.dataProps["date"]) || "date"] + ", CPM: " + feature.properties[(props.dataProps && props.dataProps["value"]) || "value"] + "<br>";
        if (feature.properties[(props.dataProps && props.dataProps["img"]) || "img"])
          popupContent += "<img src='" + feature.properties[(props.dataProps && props.dataProps["img"]) || "img"] + "' width='160'><br>" + "<em>" + feature.properties[(props.dataProps && props.dataProps["attribution"]) || "attribution"] + "</em><br>";
        if (feature.properties[(props.dataProps && props.dataProps["url"]) || "url"])
          popupContent += "<a href='" + feature.properties[(props.dataProps && props.dataProps["url"]) || "url"] + "' target=_blank>More</a><br>";
        layer.bindPopup(popupContent);

        if (feature.properties && feature.properties[(props.dataProps && props.dataProps["value"]) || "value"] != null && feature.properties[(props.dataProps && props.dataProps["value"]) || "value"] > 0) {
          const raw = feature.properties[(props.dataProps && props.dataProps["value"]) || "value"];
          const val = parseFloat(String(raw));
          if (!Number.isNaN(val) && layer && typeof (layer as any).setIcon === "function") {
            const color = val > 65 ? "red" : "green"; // >65 => red, else green
            const icon = Lref.value!.icon({
              iconRetinaUrl: `/icons/radiationIcon-${color}.svg`,
              iconUrl: `/icons/radiationIcon-${color}.svg`,
              iconSize: [28, 28],
              iconAnchor: [14, 14],
              popupAnchor: [0, -14],
              tooltipAnchor: [14, 0],
              shadowUrl: "/icons/radiationIcon-shadow.svg",
              shadowSize: [31, 33],
            });
            (layer as any).setIcon(icon);
          }
        }
      }

      layer.on("click", () => {
        const sensor = (feature.properties && (feature.properties as any).sensor_id) || "unknown";
        const value = (feature.properties && (feature.properties as any)[(props.dataProps && props.dataProps["value"]) || "value"]) || "N/A";
        console.log("Clicked feature:", sensor, value);
        emit("sensor_click", String(sensor));
      });
    },
  }) as LeafletGeoJSON;

  if (geoLayer.value && mapInstance.value as any) {
    geoLayer.value.addTo(mapInstance.value as any);
  }

  emit("data", { content: geojsonData.value, id: theMap.value, L: Lref.value, map: mapInstance.value as any });

};

onMounted(async () => {
  console.log("Map mounted");
  console.log("Props", props);
  if (!mapInstance.value as any) {
    Lref.value = L;
    // Fix Leaflet's default icon paths
    delete (Lref.value!.Icon.Default.prototype as any)._getIconUrl;

    Lref.value!.Icon.Default.mergeOptions({
      iconRetinaUrl: "/icons/radiationIcon-gray.svg", //markerIcon2x,
      iconUrl: "/icons/radiationIcon-gray.svg", //markerIcon,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -14],
      tooltipAnchor: [14, 0],
      shadowUrl: "/icons/radiationIcon-shadow.svg", // markerShadow,
      shadowSize: [31, 33],
    });

    if (theMap.value) {
      mapInstance.value = Lref.value!.map(theMap.value).setView([49.0069, 8.4037], 11); // Karlsruhe coordinates
    }
  }

  tileLayer.value = Lref.value!.tileLayer(tileSource[tileIdx]!.url, {
    maxZoom: tileIdx == 3 ? 16 : 19,
    attribution: tileSource[tileIdx]!.attr,
  }) as LeafletTileLayer;

  if (tileLayer.value && mapInstance.value as any) tileLayer.value.addTo(mapInstance.value as any);

  await loadData(props.dataUrl);
  // optionally load wind overlay
  // await loadUWind(); // ✅ correct place
  // await attachUWindOverlay(mapInstance.value, "/data/u100_cog.tif");
  await attachUWindOverlay(mapInstance.value as any);
  //await attachVelocityOverlay(mapInstance.value as any);
});

onUnmounted(() => {
  console.log("Map unmounted");
  if (!mapInstance.value as any) return;
  if (geoLayer.value) {
    try {
      geoLayer.value.clearLayers?.();
    } catch {
      // ignore
    }
  }
  if (tileLayer.value && mapInstance.value as any) {
    tileLayer.value.removeFrom(mapInstance.value as any);
  }
  if (geoLayer.value && mapInstance.value as any) {
    geoLayer.value.removeFrom(mapInstance.value as any);
  }
  if (windLayer.value && mapInstance.value as any) {
    windLayer.value.removeFrom(mapInstance.value as any);
  }
  mapInstance.value = null;
});
</script>

<style scoped>
.container {
  height: 100%;
  width: 100%;
  position: relative;
  display: flex;
}

.map {
  height: 100%;
  width: 100%;
}

.wind-legend {
  position: absolute;
  right: 12px;
  bottom: 24px;
  background: rgba(255,255,255,0.85);
  padding: 10px 12px;
  border-radius: 10px;
  font: 12px/1.2 system-ui, sans-serif;
}
.wind-legend .bar {
  width: 180px;
  height: 10px;
  border-radius: 6px;
  background: linear-gradient(90deg, rgba(0,0,255,0.9), rgba(0,0,0,0), rgba(255,0,0,0.9));
}
.wind-legend .labels {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
}


</style>
