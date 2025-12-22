<template>
  <div class="container">
    <div class="map" ref="theMap"></div>
  </div>
</template>

<script setup lang="ts">
/**
 * SimpleMap.vue
 *
 * Script-setup goals
 * - strict TS + same tsconfig (incl. "possibly undefined" / noUncheckedIndexedAccess)
 * - no non-null assertions required for runtime objects (map, element, tile source)
 * - defensive feature-property access for arbitrary GeoJSON inputs
 *
 * Notes
 * - `dataUrl` is reloaded on change.
 * - If GeoJSON includes EPSG:25832 (common in Germany), coordinates are converted to WGS84 for Leaflet.
 */

import { ref, onMounted, onUnmounted, watch } from "vue";
import L from "leaflet";
import type {
  Map as LeafletMap,
  TileLayer as LeafletTileLayer,
  GeoJSON as LeafletGeoJSON,
  ImageOverlay as LeafletImageOverlay,
} from "leaflet";
import "leaflet/dist/leaflet.css";

import proj4 from "proj4";

import { attachUWindOverlay } from "../services/WindOverlay";
import type { FeatureCollection, Feature, Geometry } from "geojson";

/** Events emitted by this component. */
const emit = defineEmits<{
  (e: "data", payload: { content: FeatureCollection | null; id: HTMLElement | null; L: typeof L | null; map: LeafletMap | null }): void;
  (e: "sensor_click", sensorId: string): void;
}>();

/** Props for the component (defaults provided via withDefaults). */
const props = withDefaults(
  defineProps<{
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
  }>(),
  {
    tileIdx: 2,
    ariaLabel: "Map",
  }
);

// -----------------------------
// State (Leaflet objects)
// -----------------------------
const mapEl = ref<HTMLElement | null>(null);
const mapInstance = ref<LeafletMap | null>(null);
const tileLayer = ref<LeafletTileLayer | null>(null);
const geoLayer = ref<LeafletGeoJSON | null>(null);
const windLayer = ref<LeafletImageOverlay | null>(null);

const geojsonData = ref<FeatureCollection | null>(null);

// -----------------------------
// Tile sources
// -----------------------------
type TileSource = { name: string; url: string; attr: string };

const tileSource: readonly TileSource[] = [
  {
    name: "OpenStreetMap",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr: "&copy; OpenStreetMap contributors",
  },
  {
    name: "OpenTopoMap",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attr: "&copy; OpenTopoMap contributors",
  },
  {
    name: "GeoPortal KA Stadtplan",
    url: "https://geoportal.karlsruhe.de/ags04/rest/services/Stadtplan_Karlsruhe/MapServer/tile/{z}/{y}/{x}",
    attr:
      "Esri Community Maps Contributors, LVermGeo RP, Esri, HERE, Garmin, SafeGraph, GeoTechnologies, Inc, METI/NASA, USGS | © Stadt Karlsruhe | Liegenschaftsamt",
  },
  {
    name: "GeoPortal KA Luftbilder",
    url: "https://geoportal.karlsruhe.de/ags04/rest/services/Luftbilder2024_Cache/MapServer/tile/{z}/{y}/{x}",
    attr:
      "Esri Community Maps Contributors, LVermGeo RP, Esri, HERE, Garmin, SafeGraph, GeoTechnologies, Inc, METI/NASA, USGS | © Stadt Karlsruhe | Liegenschaftsamt",
  },
  {
    name: "BKG World",
    url: "https://sgx.geodatenzentrum.de/wmts_topplus_open/tile/1.0.0/web/default/WEBMERCATOR/{z}/{y}/{x}.png",
    attr:
      '&copy; <a href="https://www.bkg.bund.de" target="_blank">GeoBasis-DE/BKG (' +
      new Date().getFullYear() +
      ')</a> | <a href="https://www.govdata.de/dl-de/by-2-0" target="_blank">Datenlizenz Deutschland - Namensnennung - Version 2.0</a>',
  },
] as const;

function getSelectedTile(idx: number): TileSource {
  // Defensive: avoid "possibly undefined" from array indexing
  const clamped = Number.isFinite(idx) ? Math.trunc(idx) : 0;
  return tileSource[clamped] ?? tileSource[0]!;
}

// -----------------------------
// Coordinate conversion (EPSG:25832 -> WGS84)
// -----------------------------
const EPSG25832 = "+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs";
const EPSG4326 = "+proj=longlat +datum=WGS84 +no_defs";

function isEPSG25832(collection: FeatureCollection): boolean {
  const crs = (collection as unknown as { crs?: { properties?: { name?: unknown } } }).crs;
  const name = crs?.properties?.name;
  return typeof name === "string" && name.toLowerCase().includes("epsg") && name.includes("25832");
}

function transformToWGS84(collection: FeatureCollection): void {
  for (const f of collection.features) {
    const geom = f.geometry;
    if (!geom) continue;

    const type = geom.type.toLowerCase();

    if (type === "point") {
      const coords = geom.coordinates as unknown;
      if (Array.isArray(coords) && coords.length >= 2) {
        const c = coords as [number, number];
        geom.coordinates = proj4(EPSG25832, EPSG4326, c) as [number, number];
      }
      continue;
    }

    if (type === "linestring") {
      const coords = geom.coordinates as unknown;
      if (Array.isArray(coords)) {
        const line = coords as Array<[number, number] | undefined>;
        for (let i = 0; i < line.length; i++) {
          const pt = line[i];
          if (!pt) continue;
          line[i] = proj4(EPSG25832, EPSG4326, pt) as [number, number];
        }
      }
      continue;
    }

    if (type === "polygon") {
      const coords = geom.coordinates as unknown;
      if (Array.isArray(coords)) {
        const rings = coords as Array<Array<[number, number] | undefined> | undefined>;
        for (let r = 0; r < rings.length; r++) {
          const ring = rings[r];
          if (!ring) continue;
          for (let i = 0; i < ring.length; i++) {
            const pt = ring[i];
            if (!pt) continue;
            ring[i] = proj4(EPSG25832, EPSG4326, pt) as [number, number];
          }
        }
      }
    }
  }

  // Make it less likely to transform again on reload
  const anyCrs = collection as unknown as { crs?: { properties?: { name?: string } } };
  if (anyCrs.crs?.properties) anyCrs.crs.properties.name = "WGS84";
}

// -----------------------------
// GeoJSON property helpers
// -----------------------------
function keyOrDefault(key: string, fallback: string): string {
  return props.dataProps?.[key] ?? fallback;
}

function getProps(feature: Feature): Record<string, unknown> {
  return (feature.properties ?? {}) as Record<string, unknown>;
}

function asString(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return null;
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

// -----------------------------
// Data loading + layer creation
// -----------------------------
async function loadData(): Promise<void> {
  if (!props.dataUrl) return;

  const map = mapInstance.value;
  if (!map) return;

  try {
    const response = await fetch(props.dataUrl);
    if (!response.ok) throw new Error(`Failed to fetch GeoJSON: ${response.status}`);

    const fc = (await response.json()) as FeatureCollection;

    // limit number of features (keeps UI responsive)
    const maxFeatures = 100;
    if (fc.features.length > maxFeatures) fc.features = fc.features.slice(0, maxFeatures);

    // coordinate conversion if needed
    if (isEPSG25832(fc)) transformToWGS84(fc);

    geojsonData.value = fc;

    // (re)create layer
    if (geoLayer.value) {
      geoLayer.value.removeFrom(map);
      geoLayer.value = null;
    }

    geoLayer.value = L.geoJSON(fc, {
      onEachFeature: (feature, layer) => {
        const p = getProps(feature);

        // popup
        const nameKey = keyOrDefault("name", "name");
        const descKey = keyOrDefault("description", "description");
        const dateKey = keyOrDefault("date", "date");
        const valueKey = keyOrDefault("value", "value");
        const imgKey = keyOrDefault("img", "img");
        const attributionKey = keyOrDefault("attribution", "attribution");
        const urlKey = keyOrDefault("url", "url");

        const name = asString(p[nameKey]);
        if (name) {
          let popup = `<b>${name}</b><br>`;

          const desc = asString(p[descKey]);
          if (desc) popup += `${desc}<br>`;

          const date = asString(p[dateKey]);
          if (date) popup += `Date: ${date}<br>`;

          const val = asString(p[valueKey]);
          if (val) popup += `Value: ${val}<br>`;

          const img = asString(p[imgKey]);
          if (img) popup += `<img src='${img}' style="max-width: 200px; max-height: 200px;" /><br>`;

          const attribution = asString(p[attributionKey]);
          if (attribution) popup += `<em>${attribution}</em><br>`;

          const url = asString(p[urlKey]);
          if (url) popup += `<a href='${url}' target="_blank" rel="noopener">More</a><br>`;

          layer.bindPopup(popup);
        }

        // click emission
        layer.on("click", () => {
          const sensor = asString(p["sensor_id"]) ?? "unknown";
          emit("sensor_click", sensor);
        });

        // optional icon logic if numeric value available
        const v = asNumber(p[valueKey]);
        if (v !== null && v > 0) {
          // keep original behaviour, but guarded:
          try {
            const icon = L.icon({
              iconUrl: "/icons/radiationIcon.svg",
              iconSize: [28, 28],
              iconAnchor: [14, 14],
              popupAnchor: [0, -14],
              tooltipAnchor: [14, 0],
              shadowUrl: "/icons/radiationIcon-shadow.svg",
              shadowSize: [31, 33],
            });
            (layer as unknown as { setIcon?: (i: unknown) => void }).setIcon?.(icon);
          } catch {
            // ignore icon failures
          }
        }
      },
    }) as LeafletGeoJSON;

    geoLayer.value.addTo(map);

    emit("data", { content: geojsonData.value, id: mapEl.value, L, map });

  } catch (err) {
    console.error("loadData failed:", err);
    geojsonData.value = null;
    emit("data", { content: null, id: mapEl.value, L, map });
  }
}

// -----------------------------
// Map init / teardown
// -----------------------------
function ensureMap(): LeafletMap | null {
  if (mapInstance.value) return mapInstance.value;

  const el = mapEl.value;
  if (!el) return null;

  const map = L.map(el).setView([49.0069, 8.4037], 11); // Karlsruhe
  mapInstance.value = map;
  return map;
}

function applyTileLayer(map: LeafletMap): void {
  const selected = getSelectedTile(props.tileIdx);

  if (tileLayer.value) {
    tileLayer.value.removeFrom(map);
    tileLayer.value = null;
  }

  tileLayer.value = L.tileLayer(selected.url, {
    maxZoom: props.tileIdx === 3 ? 16 : 19,
    attribution: selected.attr,
  });

  tileLayer.value.addTo(map);
}

async function attachWind(map: LeafletMap): Promise<void> {
  // Keep call flexible (service decides defaults)
  await attachUWindOverlay(map);
}

function cleanup(): void {
  const map = mapInstance.value;
  if (!map) return;

  try {
    tileLayer.value?.removeFrom(map);
    geoLayer.value?.removeFrom(map);
    windLayer.value?.removeFrom(map);
  } catch {
    // ignore
  }

  tileLayer.value = null;
  geoLayer.value = null;
  windLayer.value = null;

  map.remove();
  mapInstance.value = null;
}

// -----------------------------
// Lifecycle
// -----------------------------
watch(
  () => props.dataUrl,
  async (newVal, oldVal) => {
    if (newVal !== oldVal) await loadData();
  }
);

watch(
  () => props.tileIdx,
  (idx) => {
    const map = mapInstance.value;
    if (!map) return;
    // re-apply tiles safely
    applyTileLayer(map);
  }
);

onMounted(async () => {
  const map = ensureMap();
  if (!map) return;

  applyTileLayer(map);
  await loadData();
  await attachWind(map);
});

onUnmounted(() => {
  cleanup();
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
