
import datetime
import pygrib
import numpy as np
import re
import requests
import os 
import math
import json
from pathlib import Path
import gzip
import matplotlib.pyplot as plt


# reference:  "https://charts.ecmwf.int/products/medium-wind-100m" +  f"?base_time={base_time}&projection=opencharts_europe&valid_time={base_time}"

# make target filename and fallback
# https://data.ecmwf.int/forecasts/
#   -> 20260204/ 
#     00z/ or 06z/ or 12z/ or 18z/
# https://data.ecmwf.int/forecasts/20260204/00z/aifs-single/0p25/oper/20260204000000-6h-oper-fc.grib2
# determine current UTC time and the 6-hour slot containing it
now_utc = datetime.datetime.now(datetime.timezone.utc)
slot_hour = (now_utc.hour // 6) * 6
slot_start = now_utc.replace(hour=slot_hour, minute=0, second=0, microsecond=0)

# build primary remote URL components so we can probe availability
day_date = slot_start.strftime("%Y%m%d")
slot = f"{slot_hour:02d}z"
file_start = slot_start.strftime("%Y%m%d%H%M%S")
prefix = "https://data.ecmwf.int/forecasts/"
postfix = "-6h-oper-fc.grib2"
primary_url = f"{prefix}{day_date}/{slot}/aifs-single/0p25/oper/{file_start}{postfix}"

def _url_exists(url):
    try:
        # prefer HEAD, but fall back to a lightweight GET if HEAD is not supported
        r = requests.head(url, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            return True
        r = requests.get(url, stream=True, timeout=10)
        r.close()
        return r.status_code == 200
    except Exception:
        return False

# If primary file missing, try a fallback 12 hours earlier
if _url_exists(primary_url):
    print("Remote GRIB URL (primary):", primary_url)
else:
    fallback_slot_start = slot_start - datetime.timedelta(hours=12)
    fb_day = fallback_slot_start.strftime("%Y%m%d")
    fb_hour = (fallback_slot_start.hour // 6) * 6
    fb_slot = f"{fb_hour:02d}z"
    fb_file_start = fallback_slot_start.strftime("%Y%m%d%H%M%S")
    fallback_url = f"{prefix}{fb_day}/{fb_slot}/aifs-single/0p25/oper/{fb_file_start}{postfix}"

    if _url_exists(fallback_url):
        print("Primary not available, using fallback (-12h):", fallback_url)
        # switch slot_start/hour so subsequent code builds the fallback filename/url
        slot_start = fallback_slot_start
        slot_hour = fb_hour
    else:
        print("Neither primary nor fallback GRIB found; will attempt primary URL:", primary_url) # build strings used in the path/filename
day_date = slot_start.strftime("%Y%m%d")        # e.g. 20260204
slot = f"{slot_hour:02d}z"                      # e.g. "00z", "06z", "12z", "18z"
file_start = slot_start.strftime("%Y%m%d%H%M%S")# e.g. 20260204000000

prefix = "https://data.ecmwf.int/forecasts/"
postfix = "-6h-oper-fc.grib2"

# full remote URL to the GRIB file
remote_url = f"{prefix}{day_date}/{slot}/aifs-single/0p25/oper/{file_start}{postfix}"
print("Remote GRIB URL:", remote_url)

# local filename (basename) and download if not present
out_dir = Path("wind")
out_dir.mkdir(parents=True, exist_ok=True)
print(f"Ensuring output directory: {out_dir.resolve()}")
# switch working directory so all subsequent relative outputs go into wind/
os.chdir(out_dir)
local_basename = os.path.basename(remote_url)
local_path = Path(local_basename)
if not local_path.exists():
    print("Downloading", local_basename, "...")
    try:
        with requests.get(remote_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
        print("Downloaded to", local_path)
    except Exception as exc:
        print("Failed to download remote GRIB:", exc)
else:
    print("File already present. Stop")
    print("Target file:", local_path)
    exit()

# set filename to the local file path for subsequent pygrib.open(...)
filename = str(local_path)
gribFile = filename    

# exit()

u_wind = None
v_wind = None
lats = lons = None

with pygrib.open(filename) as grbs:
    wind_input_unit = None
    conversion_factor = 1.0

    for grb in grbs:
        sn = (getattr(grb, "shortName", "") or "").lower()
        name = (getattr(grb, "name", "") or "").lower()
        level = getattr(grb, "level", None)
        tlevel = (getattr(grb, "typeOfLevel", "") or "").lower()
        units = (getattr(grb, "units", "") or "").strip()

        print(f"Found field: shortName={sn}, name={name}, level={level}, typeOfLevel={tlevel}, units={units}")

        # try several matching heuristics (shortName/name like '100u'/'100v' or u/v at 100m height)
        if "100u" in sn or "100u" in name or (sn in ("u", "u_component_of_wind") and "height" in tlevel and level == 100):
            print("Matched u wind")
            # determine units and conversion to m/s (1 knot = 0.514444 m/s)
            if wind_input_unit is None and units:
                wind_input_unit = units
                u_units = units.lower()
                if re.search(r'\bknots?\b|\bkt\b|\bkn\b', u_units):
                    conversion_factor = 0.514444
                elif re.search(r'm\s*/\s*s|\bm/s\b|m\s*s-1|m\s*s-?1', u_units):
                    conversion_factor = 1.0
                else:
                    # unknown unit, assume m/s but inform the user
                    conversion_factor = 1.0
                    print(f"Warning: Unrecognized wind units '{units}', assuming m/s")

            u_wind = grb.values * conversion_factor
            lats, lons = grb.latlons()

        if "100v" in sn or "100v" in name or (sn in ("v", "v_component_of_wind") and "height" in tlevel and level == 100):
            print("Matched v wind")
            if wind_input_unit is None and units:
                wind_input_unit = units
                v_units = units.lower()
                if re.search(r'\bknots?\b|\bkt\b|\bkn\b', v_units):
                    conversion_factor = 0.514444
                elif re.search(r'm\s*/\s*s|\bm/s\b|m\s*s-1|m\s*s-?1', v_units):
                    conversion_factor = 1.0
                else:
                    conversion_factor = 1.0
                    print(f"Warning: Unrecognized wind units '{units}', assuming m/s")

            v_wind = grb.values * conversion_factor
            lats, lons = grb.latlons()

        if u_wind is not None and v_wind is not None:
            break

    # Save detected original unit and applied conversion factor for later usage
    wind_meta = {
        "source_grib": filename,
        "original_wind_units": wind_input_unit or "unknown",
        "stored_wind_units": "m/s",
        "conversion_factor_to_m_s": float(conversion_factor),
    }
    try:
        meta_path = Path(filename).with_suffix(Path(filename).suffix + ".meta.json")
        with open(meta_path, "w") as mf:
            json.dump(wind_meta, mf, separators=(",", ":"), ensure_ascii=False)
        print(f"Wrote wind unit metadata to {meta_path}")
    except Exception as exc:
        print("Failed to write wind metadata file:", exc)
if u_wind is None or v_wind is None:
    raise RuntimeError("Could not find 100m u/v fields in GRIB file")

outname = f"extracted_wind100m_{Path(filename).stem}.npz"
print(f"Processing wind data, will write to {outname} ...")

def _data_and_mask(arr):
    if hasattr(arr, "mask"):
        return np.ma.getdata(arr), np.ma.getmaskarray(arr)
    a = np.asarray(arr)
    return a, np.zeros_like(a, dtype=bool)

u_data, u_mask = _data_and_mask(u_wind)
v_data, v_mask = _data_and_mask(v_wind)

speed = np.hypot(u_data, v_data)
speed_mask = u_mask | v_mask

np.savez_compressed(
    outname,
    u=u_data,
    u_mask=u_mask,
    v=v_data,
    v_mask=v_mask,
    speed=speed,
    speed_mask=speed_mask,
    lats=lats,
    lons=lons,
    source_grib=filename,
)
    
print(f"Wrote output to {outname}")

# truncate (don't remove) the downloaded GRIB file to save space (and its metadata if present)
try:
    grib_path = Path(gribFile)
    if grib_path.exists():
        try:
            # open read/write binary and truncate to 0 bytes
            with grib_path.open("r+b") as f:
                f.truncate(0)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            print(f"Truncated GRIB file to 0 bytes: {grib_path}")
        except Exception:
            # fallback: overwrite the file with an empty file
            try:
                with grib_path.open("wb"):
                    pass
                print(f"Truncated (overwritten) GRIB file to 0 bytes: {grib_path}")
            except Exception as exc:
                print("Failed to truncate GRIB file:", exc)
                exit()
    else:
        # create an empty file if it doesn't exist
        try:
            with grib_path.open("wb"):
                pass
            print(f"Created zero-length GRIB file: {grib_path}")
        except Exception as exc:
            print("Failed to create zero-length GRIB file:", exc)
            exit()
except Exception as exc:
    print("Failed to truncate GRIB file:", exc)
    exit()

# also try removing the generated .meta.json sidecar if it exists
try:
    meta_path = Path(gribFile).with_suffix(Path(gribFile).suffix + ".meta.json")
    if meta_path.exists():
        meta_path.unlink()
        print(f"Removed metadata file: {meta_path}")
except Exception:
    # non-fatal: ignore errors when removing metadata
    pass


# Create a combined valid-data mask and masked arrays
mask_all = u_mask | v_mask | np.isnan(u_data) | np.isnan(v_data)
u_ma = np.ma.array(u_data, mask=mask_all)
v_ma = np.ma.array(v_data, mask=mask_all)
speed_ma = np.ma.array(speed, mask=mask_all)

# Decimate the grid for barbs so the plot is legible
ny, nx = u_ma.shape
target_points = 90  # target number of points along long axis
step_x = max(1, nx // target_points)
step_y = max(1, ny // target_points)

lons_s = lons[::step_y, ::step_x]
lats_s = lats[::step_y, ::step_x]
u_s = u_ma[::step_y, ::step_x]
v_s = v_ma[::step_y, ::step_x]

# Create figure: background is wind speed, overlay barbs
fig, ax = plt.subplots(figsize=(16, 8))  # ration is 2 : 1
# pcm = ax.pcolormesh(lons, lats, speed_ma, shading='auto', cmap='viridis') 

#cb = fig.colorbar(pcm, ax=ax, label='Wind speed (m/s)')
# remove side colorbar (if created) and make the axes fill the full figure

fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
ax.set_position([0.0, 0.0, 1.0, 1.0])



# add a small color scale inside the plot area (not on any external side)
#cax = inset_axes(ax, width="3%", height="30%", loc='upper right',
#                 bbox_to_anchor=(0.98, 0.98), bbox_transform=ax.transAxes, borderpad=0)
#fig.colorbar(pcm, cax=cax, orientation='vertical', label='Wind speed (m/s)')
# make the inset colorbar visually subtle so it doesn't reduce usable plot area too much
#cax.yaxis.set_label_position('right')
#cax.yaxis.tick_right()

# Plot barbs
ax.barbs(lons_s, lats_s, u_s, v_s, length=6, linewidth=0.4, pivot='middle', color='k')

ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title('100 m wind speed and barbs')
ax.set_xlim(np.nanmin(lons), np.nanmax(lons))
ax.set_ylim(np.nanmin(lats), np.nanmax(lats))
plt.tight_layout()

figname = outname.replace('.npz', '.png')
plt.savefig(figname, dpi=300)
plt.close(fig)

print(f"Wrote windbarb image to {figname}")

# Create vector tiles with wind barbs (improved decimation + compression)
# - Limit features per tile
# - Deterministic random sampling per tile to preserve spatial spread
# - Reduce numeric precision to shrink JSON
# - Save tiles compressed (.json.gz)

# Create vector tiles with wind barbs

def latlon_to_tile(lat, lon, zoom):
    """Convert lat/lon to tile coordinates at given zoom level"""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y

def tile_bounds(x, y, zoom):
    """Get lat/lon bounds for a tile"""
    n = 2.0 ** zoom
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lat_min, lon_min, lat_max, lon_max

# Create tiles directory
tiles_dir = Path("wind_tiles")
tiles_dir.mkdir(exist_ok=True)

# Generate tiles for zoom levels
zoom_levels = [1, 2, 3, 4, 5, 6]

# parameters to control output size/quality
MAX_FEATURES_PER_TILE = 300       # hard cap per tile
TARGET_FEATURES_PER_TILE = 200    # if N>MAX, downsample to this many
LAT_LON_PREC = 4                  # decimal places for lat/lon
VEL_PREC = 2                      # decimal places for u/v/speed
DIR_PREC = 1                      # decimal places for direction

# precompute global bounds once
global_lat_min = float(np.nanmin(lats))
global_lat_max = float(np.nanmax(lats))
global_lon_min = float(np.nanmin(lons))
global_lon_max = float(np.nanmax(lons))

for zoom in zoom_levels:
    print(f"Generating tiles for zoom level {zoom}...")
    zoom_dir = tiles_dir / str(zoom)
    zoom_dir.mkdir(exist_ok=True)
    
    # Determine tile range covering the data by checking all four corners
    tx1, ty1 = latlon_to_tile(global_lat_min, global_lon_min, zoom)
    tx2, ty2 = latlon_to_tile(global_lat_min, global_lon_max, zoom)
    tx3, ty3 = latlon_to_tile(global_lat_max, global_lon_min, zoom)
    tx4, ty4 = latlon_to_tile(global_lat_max, global_lon_max, zoom)
    min_x = min(tx1, tx2, tx3, tx4)
    max_x = max(tx1, tx2, tx3, tx4)
    min_y = min(ty1, ty2, ty3, ty4)
    max_y = max(ty1, ty2, ty3, ty4)
    
    created = 0
    for tx in range(min_x, max_x + 1):
        x_dir = zoom_dir / str(tx)
        x_dir.mkdir(exist_ok=True)
        
        for ty in range(min_y, max_y + 1):
            # Get tile bounds
            tlat_min, tlon_min, tlat_max, tlon_max = tile_bounds(tx, ty, zoom)
            
            # boolean mask of points in tile (vectorized)
            in_tile = ((lats >= tlat_min) & (lats <= tlat_max) &
                       (lons >= tlon_min) & (lons <= tlon_max) &
                       ~mask_all)
            
            idx = np.flatnonzero(in_tile)
            N = idx.size
            if N == 0:
                continue
            
            # If too many points, pick a deterministic random subset for even spread
            if N > MAX_FEATURES_PER_TILE:
                keep = TARGET_FEATURES_PER_TILE
                seed = ((zoom & 0xFFFF) << 32) ^ ((tx & 0xFFFF) << 16) ^ (ty & 0xFFFF)
                rng = np.random.default_rng(seed)
                choose = rng.choice(idx, size=keep, replace=False)
            else:
                choose = idx  # use all
            
            # Convert flat indices back to 2D indices for fast indexing
            rows, cols = np.unravel_index(choose, lats.shape)
            tile_lats = lats[rows, cols]
            tile_lons = lons[rows, cols]
            tile_u = u_data[rows, cols]
            tile_v = v_data[rows, cols]
            tile_speed = speed[rows, cols]
            
            # Build features with reduced precision to save space
            features = []
            for i in range(tile_lats.size):
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            round(float(tile_lons[i]), LAT_LON_PREC),
                            round(float(tile_lats[i]), LAT_LON_PREC),
                        ],
                    },
                    "properties": {
                        "u": round(float(tile_u[i]), VEL_PREC),
                        "v": round(float(tile_v[i]), VEL_PREC),
                        "speed": round(float(tile_speed[i]), VEL_PREC),
                        "direction": round(float(math.degrees(math.atan2(tile_v[i], tile_u[i]))), DIR_PREC),
                    },
                }
                features.append(feature)
            
            geojson = {"type": "FeatureCollection", "features": features}


            # Decompress in browser:
            #// Browser-friendly decompression: DecompressionStream if available (Chromium/Firefox and recent Safari),
            #// otherwise fall back to inflating the ArrayBuffer client-side (e.g. with pako).
            #// Include pako on the page if you need the fallback:
            #// <script src="https://cdn.jsdelivr.net/npm/pako@2/dist/pako.min.js"></script>
            #//
            #// Example usage in JS:
            #// async function fetchGzJson(url) {
            #//   const res = await fetch(url, { mode: 'cors' });
            #//   if ('DecompressionStream' in self) {
            #//     // Modern browsers (Chromium, Firefox, and recent Safari)
            #//     const ds = res.body.pipeThrough(new DecompressionStream('gzip'));
            #//     const text = await new Response(ds).text();
            #//     return JSON.parse(text);
            #//   } else {
            #//     // Fallback for older Safari / browsers without DecompressionStream
            #//     const buf = await res.arrayBuffer();
            #//     // pako must be available (via CDN or bundled)
            #//     const inflated = pako.inflate(new Uint8Array(buf), { to: 'string' });
            #//     return JSON.parse(inflated);
            #//   }
            #// }
            #//
            #// // call it:
            #// fetchGzJson('/tiles/3/1/2.json.gz').then(geojson => console.log(geojson)).catch(console.error);
            #const res = await fetch('/tiles/3/1/2.json.gz', { mode: 'cors' });
            #const ds = res.body.pipeThrough(new DecompressionStream('gzip'));
            #const text = await new Response(ds).text();
            #const geojson = JSON.parse(text);
            #console.log(geojson); 
            #created += 1
            
            # Save compressed tile to reduce disk/network size
            tile_file = x_dir / f"{ty}.json.gz"
            with gzip.open(tile_file, "wt", compresslevel=6) as f:
                json.dump(geojson, f, separators=(",", ":"))
            
            created += 1
    
    total_files = len(list(zoom_dir.rglob("*.json.gz")))
    print(f"  Generated {total_files} tiles (created this zoom: {created})")

print(f"Wind barb tiles saved to {tiles_dir}/ (compressed .json.gz files)")

# Generate raster PNG tiles with wind barbs (256x256 px tiles) in "raster_tiles" directory
raster_dir = Path("raster_tiles")
raster_dir.mkdir(exist_ok=True)

TILE_PX = 256
DPI = 100.0

for zoom in zoom_levels:
    print(f"Generating raster tiles for zoom level {zoom}...")
    zoom_dir = raster_dir / str(zoom)
    zoom_dir.mkdir(exist_ok=True)

    # Determine tile range covering the data (same approach as vector generation)
    tx1, ty1 = latlon_to_tile(global_lat_min, global_lon_min, zoom)
    tx2, ty2 = latlon_to_tile(global_lat_min, global_lon_max, zoom)
    tx3, ty3 = latlon_to_tile(global_lat_max, global_lon_min, zoom)
    tx4, ty4 = latlon_to_tile(global_lat_max, global_lon_max, zoom)
    min_x = min(tx1, tx2, tx3, tx4)
    max_x = max(tx1, tx2, tx3, tx4)
    min_y = min(ty1, ty2, ty3, ty4)
    max_y = max(ty1, ty2, ty3, ty4)

    created = 0
    for tx in range(min_x, max_x + 1):
        x_dir = zoom_dir / str(tx)
        x_dir.mkdir(exist_ok=True)

        for ty in range(min_y, max_y + 1):
            # tile bounds
            tlat_min, tlon_min, tlat_max, tlon_max = tile_bounds(tx, ty, zoom)

            # boolean mask of points in tile
            in_tile = ((lats >= tlat_min) & (lats <= tlat_max) &
                       (lons >= tlon_min) & (lons <= tlon_max) &
                       ~mask_all)

            idx = np.flatnonzero(in_tile)
            N = idx.size
            if N == 0:
                continue

            # deterministic downsample if too many points
            if N > MAX_FEATURES_PER_TILE:
                keep = TARGET_FEATURES_PER_TILE
                seed = ((zoom & 0xFFFF) << 32) ^ ((tx & 0xFFFF) << 16) ^ (ty & 0xFFFF)
                rng = np.random.default_rng(seed)
                choose = rng.choice(idx, size=keep, replace=False)
            else:
                choose = idx

            rows, cols = np.unravel_index(choose, lats.shape)
            tile_lats = lats[rows, cols]
            tile_lons = lons[rows, cols]
            tile_u = u_data[rows, cols]
            tile_v = v_data[rows, cols]
            tile_speed = speed[rows, cols]

            # create figure sized to TILE_PX at DPI
            fig = plt.figure(figsize=(TILE_PX / DPI, TILE_PX / DPI), dpi=DPI)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_xlim(tlon_min, tlon_max)
            ax.set_ylim(tlat_min, tlat_max)
            ax.axis("off")

            # background: small colored dots for speed (cheap rasterized rendering)
            # use small square markers to roughly fill pixels
            ax.scatter(tile_lons, tile_lats, c=tile_speed, cmap="viridis", s=3, marker="s", linewidths=0, rasterized=True)

            # barb length tuned by zoom (larger zoom -> longer barbs)
            barb_length = 6 + max(0, zoom - 4)
            ax.barbs(tile_lons, tile_lats, tile_u, tile_v, length=barb_length, linewidth=0.5, pivot="middle", color="k")

            out_file = x_dir / f"{ty}.png"
            fig.savefig(out_file, dpi=DPI, transparent=True)
            plt.close(fig)

            created += 1

    total_files = len(list(zoom_dir.rglob("*.png")))
    print(f"  Generated {total_files} raster tiles (created this zoom: {created})")

print(f"Raster wind barb tiles saved to {raster_dir}/ (PNG files)")
