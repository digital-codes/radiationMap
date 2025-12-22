// uWindOverlay.ts
// Leaflet + GeoTIFF.js (COG) client-side rendering for U-wind (east-west component)
// - Reads only the visible window via HTTP Range requests (COG)
// - Works with EPSG:3857 GeoTIFFs (like your file per gdalinfo)
// - No worker pool (avoid poolOrDecoder.decode error)

import L, { Map as LeafletMap, ImageOverlay } from "leaflet";
import { fromUrl } from "geotiff";

export type UWindOverlayOptions = {
  /** URL to the COG GeoTIFF (served with Range support). Example: "/data/u100_cog.tif" */
  url: string;

  /** Output render size in pixels (square). Lower = faster. Default 512. */
  renderSize?: number;

  /** Max alpha (0..255). Default 110 for subtle overlay. */
  maxAlpha?: number;

  /** Alpha curve gamma (>=0.1). Higher hides weak winds more. Default 0.8. */
  alphaGamma?: number;

  /** Fixed vmax (m/s) for scaling. If undefined, uses a quick per-view estimate. */
  vmax?: number;

  /** Leaflet overlay opacity multiplier (0..1). Default 0.6 */
  opacity?: number;

  /** Redraw debounce in ms. Default 120. */
  debounceMs?: number;

  /** If true, tries to choose a lower-res overview based on zoom (uses getImageForResolution). Default true. */
  useOverviews?: boolean;
};

export type UWindOverlayHandle = {
  /** Force redraw now. */
  redraw: () => Promise<void>;
  /** Remove overlay and listeners. */
  remove: () => void;
};

const WEBMERCATOR_WORLD = 40075016.68557849; // meters

function metersPerPixelForLeafletZoom(zoom: number, tileSize = 256): number {
  return WEBMERCATOR_WORLD / (tileSize * Math.pow(2, zoom));
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

/**
 * Add U-wind overlay to an existing Leaflet map.
 * Your GeoTIFF must be in EPSG:3857 for this helper (matches your u100_cog.tif).
 */
export async function addUWindOverlay(
  map: LeafletMap,
  opts: UWindOverlayOptions
): Promise<UWindOverlayHandle> {
  const url = opts.url;
  const renderSize = opts.renderSize ?? 512;
  const maxAlpha = clamp(opts.maxAlpha ?? 110, 0, 255);
  const alphaGamma = Math.max(opts.alphaGamma ?? 0.8, 0.1);
  const overlayOpacity = clamp(opts.opacity ?? 0.6, 0, 1);
  const debounceMs = Math.max(opts.debounceMs ?? 120, 0);
  const useOverviews = opts.useOverviews ?? true;

  const tiff = await fromUrl(url);

  let layer: ImageOverlay | null = null;
  let disposed = false;
  let timer: number | null = null;
  let inflight = false;
  let queued = false;

  async function drawOnce(): Promise<void> {
    if (disposed) return;
    if (inflight) {
      queued = true;
      return;
    }
    inflight = true;

    try {
      const zoom = map.getZoom();
      const mpp = metersPerPixelForLeafletZoom(zoom);

      const image = useOverviews
        ? await tiff.getImageForResolution(mpp)
        : await tiff.getImage();

      const b = map.getBounds();
      const nw = L.CRS.EPSG3857.project(b.getNorthWest());
      const se = L.CRS.EPSG3857.project(b.getSouthEast());

      const [px0, py0] = image.geoToPixel(nw.x, nw.y);
      const [px1, py1] = image.geoToPixel(se.x, se.y);

      const xMin = clamp(Math.floor(Math.min(px0, px1)), 0, image.getWidth());
      const xMax = clamp(Math.ceil(Math.max(px0, px1)), 0, image.getWidth());
      const yMin = clamp(Math.floor(Math.min(py0, py1)), 0, image.getHeight());
      const yMax = clamp(Math.ceil(Math.max(py0, py1)), 0, image.getHeight());

      if (xMax <= xMin || yMax <= yMin) return;

      const rasters = await image.readRasters({
        samples: [0],
        window: [xMin, yMin, xMax, yMax],
        width: renderSize,
        height: renderSize,
        // IMPORTANT: don't pass pool/decoder here
      });

      const data = (rasters as unknown as ArrayLike<ArrayLike<number>>)[0] as unknown as Float32Array;

      let vmax = opts.vmax;
      if (!vmax || vmax <= 0) {
        let mx = 0;
        const step = 8;
        for (let i = 0; i < data.length; i += step) {
          const u = data[i];
          if (Number.isFinite(u)) mx = Math.max(mx, Math.abs(u));
        }
        vmax = mx > 0 ? mx : 1;
      }

      const w = renderSize;
      const h = renderSize;

      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const img = ctx.createImageData(w, h);

      for (let i = 0; i < data.length; i++) {
        const u = data[i];
        const j = i * 4;

        if (!Number.isFinite(u)) {
          img.data[j + 3] = 0;
          continue;
        }

        const v = clamp(u / vmax, -1, 1);

        const pos = v > 0 ? v : 0;
        const neg = v < 0 ? -v : 0;

        img.data[j + 0] = Math.round(pos * 255);
        img.data[j + 1] = 0;
        img.data[j + 2] = Math.round(neg * 255);

        const a = Math.min(
          maxAlpha,
          Math.pow(Math.abs(v), alphaGamma) * maxAlpha
        );
        img.data[j + 3] = Math.round(a);
      }

      ctx.putImageData(img, 0, 0);

      const overlayBounds = b;
      const dataUrl = canvas.toDataURL("image/png");

      if (layer) layer.remove();
      layer = L.imageOverlay(dataUrl, overlayBounds, {
        opacity: overlayOpacity,
        interactive: false,
      }).addTo(map);
    } finally {
      inflight = false;
      if (queued && !disposed) {
        queued = false;
        void drawOnce();
      }
    }
  }

  function scheduleDraw(): void {
    if (disposed) return;
    if (debounceMs === 0) {
      void drawOnce();
      return;
    }
    if (timer !== null) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      timer = null;
      void drawOnce();
    }, debounceMs);
  }

  map.whenReady(() => scheduleDraw());

  const onMove = () => scheduleDraw();
  map.on("moveend zoomend", onMove);

  return {
    redraw: drawOnce,
    remove: () => {
      disposed = true;
      if (timer !== null) window.clearTimeout(timer);
      map.off("moveend zoomend", onMove);
      if (layer) layer.remove();
      layer = null;
    },
  };
}
