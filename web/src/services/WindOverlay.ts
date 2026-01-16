// import wind overlay from GeoTIFF
import { fromUrl } from "geotiff";
import L from "leaflet";
import type { ImageOverlay as LeafletImageOverlay } from "leaflet";

function lngLatToMercatorMeters(lng: number, lat: number): [number, number] {
  // EPSG:3857
  const R = 6378137;
  const max = 85.0511287798;
  const clampedLat = Math.max(Math.min(lat, max), -max);
  const x = (R * lng * Math.PI) / 180;
  const y = R * Math.log(Math.tan(Math.PI / 4 + (clampedLat * Math.PI) / 360));
  return [x, y];
}

export async function attachUWindOverlay(map: L.Map, url = "/data/u100_cog.tif"): Promise<{ overlay: LeafletImageOverlay; redraw: () => void }> {
  const tiff = await fromUrl(url);
  const image = await tiff.getImage();

  // GeoTransform from your gdalinfo:
  // Origin = (x0, y0)
  // PixelSize = (pxW, pxH) where pxH is negative
  const [x0, y0] = image.getOrigin() as [number, number];      // meters
  const [pxW, pxH] = image.getResolution() as [number, number]; // meters per pixel (pxH negative)
  const fullW = image.getWidth() as number;
  const fullH = image.getHeight() as number;

  // Leaflet canvas overlay
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;

  const overlay = L.imageOverlay(canvas.toDataURL(), map.getBounds(), { opacity: .8 });
  overlay.addTo(map);

  async function draw(): Promise<void> {
    const size = map.getSize();
    if (!size.x || !size.y) return;

    canvas.width = size.x;
    canvas.height = size.y;

    const b = map.getBounds();
    const [minX, minY] = lngLatToMercatorMeters(b.getWest(), b.getSouth());
    const [maxX, maxY] = lngLatToMercatorMeters(b.getEast(), b.getNorth());

    // Convert meters -> pixel coordinates in the GeoTIFF
    // x = (X - x0)/pxW
    // y = (Y - y0)/pxH  (pxH is negative)
    let xMinPx = Math.floor((minX - x0) / pxW);
    let xMaxPx = Math.ceil((maxX - x0) / pxW);
    let yMinPx = Math.floor((maxY - y0) / pxH); // note: using maxY for top
    let yMaxPx = Math.ceil((minY - y0) / pxH);  // minY for bottom

    // Clamp to dataset
    xMinPx = Math.max(0, Math.min(fullW, xMinPx));
    xMaxPx = Math.max(0, Math.min(fullW, xMaxPx));
    yMinPx = Math.max(0, Math.min(fullH, yMinPx));
    yMaxPx = Math.max(0, Math.min(fullH, yMaxPx));

    // No intersection => transparent
    if (xMaxPx <= xMinPx || yMaxPx <= yMinPx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      overlay.setUrl(canvas.toDataURL());
      overlay.setBounds(b);
      return;
    }

    const rasterWindow: [number, number, number, number] = [xMinPx, yMinPx, xMaxPx, yMaxPx];

    // Read only what's visible, resampled to screen size
    const rasters: any = await image.readRasters({
      window: rasterWindow,
      width: canvas.width,
      height: canvas.height,
      samples: [0],     // Band 1 = U
      fillValue: NaN,
      pool: false
    });

    const u = rasters && rasters[0] as (Float32Array | number[] | undefined);

    if (!u || !u.length) {
      // nothing to draw
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      overlay.setUrl(canvas.toDataURL());
      overlay.setBounds(b);
      return;
    }

    // Robust symmetric scaling around 0 (subtle)
    // Compute vmax from a sample for speed
    let vmax = 0;
    for (let i = 0; i < u.length; i += 23) {
      const v = u[i];
      if (Number.isFinite(v)) vmax = Math.max(vmax, Math.abs(v));
    }
    vmax = Math.max(vmax, 1); // avoid divide by 0
    vmax = Math.min(vmax, 25); // optional cap (m/s)

    const img = ctx.createImageData(canvas.width, canvas.height);
    for (let i = 0; i < u.length; i++) {
      const val = u[i];
      if (!Number.isFinite(val)) continue;

      const v = Math.max(-1, Math.min(1, val / vmax)); // -1..1

      // red for +U, blue for -U
      const pos = v > 0 ? v : 0;
      const neg = v < 0 ? -v : 0;

      // subtle alpha: weak winds fade out
      const a = Math.min(140, Math.pow(Math.abs(v), 0.8) * 140);

      img.data[i * 4 + 0] = Math.round(pos * 255);
      img.data[i * 4 + 1] = 0;
      img.data[i * 4 + 2] = Math.round(neg * 255);
      img.data[i * 4 + 3] = Math.round(a);
    }

    ctx.putImageData(img, 0, 0);

    // Update overlay image + bounds
    overlay.setUrl(canvas.toDataURL());
    overlay.setBounds(b);
  }

  // draw once + throttle redraws
  let raf: number | null = null;
  const schedule = (): void => {
    if (raf !== null) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      // handle errors inside the RAF callback
      draw().catch((err: any) => { console.error(err); });
    });
  };

  map.whenReady(schedule);
  // register events separately to satisfy stricter typings
  map.on("moveend", schedule);
  map.on("zoomend", schedule);
  map.on("resize", schedule);

  return { overlay: overlay as LeafletImageOverlay, redraw: schedule };
}
