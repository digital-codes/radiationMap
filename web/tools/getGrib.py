# https://pypi.org/project/ecmwf-opendata/
# https://www.ecmwf.int/en/forecasts/datasets/open-data
# https://charts.ecmwf.int/products/medium-wind-100m?base_time=202512220000&projection=opencharts_europe&valid_time=202512220000

#!/usr/bin/env python3
# --------------------------------------------------------------
# gribExtract.py (fixed)
# --------------------------------------------------------------
# Purpose:
#   - Read a GRIB (cfgrib/xarray)
#   - Select a variable (default: u100)
#   - Normalize longitudes to -180..180 (if needed)
#   - Ensure latitude is ascending for a north-up raster
#   - Write a temporary GeoTIFF in EPSG:4326 with a correct transform
#   - Reproject to a target CRS (default EPSG:3857)
#   - Write a Cloud-Optimized GeoTIFF (COG) with internal tiling + overviews
#
# Notes on fixes vs previous version:
#   * rasterio.transform.from_origin expects a POSITIVE y pixel size. It
#     internally stores a negative y-scale for north-up rasters. Passing
#     a negative ysize produced an invalid transform.
#   * When longitude values are normalized and re-ordered, the DataArray
#     coordinates must be updated too; otherwise transform/coordinates mismatch.
#   * rasterio profile key is "crs" (lowercase). "CRS" will raise/behave wrongly.
#   * Avoid non-standard GTiff creation options (e.g. "CRS", "RESAMPLING"),
#     which can trigger GDAL errors depending on versions.
# --------------------------------------------------------------

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
import requests

import numpy as np
import xarray as xr
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio import warp
from rasterio.shutil import copy as rio_copy


from ecmwf.opendata import Client



def _find_coord_name(da: xr.DataArray, candidates: tuple[str, ...]) -> str:
    """Return first coordinate name that exists in da (common GRIB names vary)."""
    for name in candidates:
        if name in da.coords:
            return name
    raise KeyError(f"None of the coordinate names {candidates} were found. Available: {list(da.coords)}")


def normalise_longitudes(lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Wrap longitudes to [-180, 180) and return (wrapped_sorted_lons, sort_idx).
    """
    lon = np.asarray(lon)
    lon_wrapped = ((lon + 180.0) % 360.0) - 180.0
    sort_idx = np.argsort(lon_wrapped)
    return lon_wrapped[sort_idx], sort_idx


def build_geographic_transform(lons: np.ndarray, lats: np.ndarray) -> rasterio.Affine:
    """
    Build an EPSG:4326 north-up transform from 1D lon/lat centers.

    Assumes:
      - lons are strictly ascending
      - lats are strictly ascending (south->north)
    """
    if len(lons) < 2 or len(lats) < 2:
        raise ValueError("Need at least 2 longitudes and 2 latitudes to infer pixel size.")

    # Robust pixel size from median step (handles minor rounding noise)
    dx = float(np.median(np.diff(lons)))
    dy = float(np.median(np.diff(lats)))
    if dx <= 0 or dy <= 0:
        raise ValueError(f"Non-positive pixel size inferred (dx={dx}, dy={dy}). Are coords sorted?")

    west = float(lons[0] - dx / 2.0)
    north = float(lats[-1] + dy / 2.0)

    # IMPORTANT: ysize must be POSITIVE here; from_origin creates north-up affine.
    return from_origin(west, north, dx, dy)


def write_epsg4326_geotiff(path: Path, data: np.ndarray, transform: rasterio.Affine, nodata: float | None) -> None:
    profile = {
        "driver": "GTiff",
        "height": int(data.shape[0]),
        "width": int(data.shape[1]),
        "count": 1,
        "dtype": str(data.dtype),
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def reproject_to_cog(
    src_tif: Path,
    dst_cog: Path,
    target_crs: str,
    resampling: Resampling = Resampling.bilinear,
    overview_factors: tuple[int, ...] = (2, 4, 8, 16, 32),
) -> None:
    """
    Reproject src_tif to target_crs, build overviews, then write a COG.

    We first write an intermediate tiled GTiff (so overview building is reliable),
    then (if GDAL supports it) convert to driver=COG. If not, we keep a GTiff
    that is still largely COG-like (tiled + overviews), but may miss some strict
    COG metadata.
    """
    tmp_reproj = src_tif.with_suffix(".reproj.tif")

    with rasterio.open(src_tif) as src:
        dst_transform, dst_width, dst_height = warp.calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds
        )

        reproj_profile = src.profile.copy()
        reproj_profile.update(
            driver="GTiff",
            crs=target_crs,
            transform=dst_transform,
            width=int(dst_width),
            height=int(dst_height),
            tiled=True,
            blockxsize=256,
            blockysize=256,
            compress="deflate",
            predictor=3 if np.issubdtype(src.dtypes[0], np.floating) else 2,
            BIGTIFF="IF_SAFER",
            count=1,
            interleave="band",
        )

        # Allocate destination array and reproject into it (more robust than band->band across versions)
        dest = np.empty((int(dst_height), int(dst_width)), dtype=src.dtypes[0])

        warp.reproject(
            source=rasterio.band(src, 1),
            destination=dest,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            resampling=resampling,
            src_nodata=src.nodata,
            dst_nodata=src.nodata,
        )

        with rasterio.open(tmp_reproj, "w", **reproj_profile) as dst:
            dst.write(dest, 1)
            dst.build_overviews(list(overview_factors), Resampling.nearest)
            dst.update_tags(ns="rio_overview", resampling="nearest")

    # Try to produce a proper COG using the COG driver (if available).
    # Fall back to copying the tiled GeoTIFF if COG driver isn't present.
    try:
        rio_copy(
            tmp_reproj,
            dst_cog,
            driver="COG",
            compress="deflate",
            # These are GDAL COG creation options; ignored if unsupported.
            blocksize=256,
            overview_resampling="NEAREST",
        )
    except Exception:
        # Fallback: keep the reprojected GTiff as-is (still tiled + overviews).
        if dst_cog.exists():
            dst_cog.unlink()
        os.replace(tmp_reproj, dst_cog)
    else:
        # If COG succeeded, remove the intermediate file.
        tmp_reproj.unlink(missing_ok=True)

def rawRequests(target = "aifs_ens_cf_medium-wind-100m.grib") -> None:

    URL = (
        "https://data.ecmwf.int/forecasts/"
        "aifs/ens/cf/medium/"
        "aifs_ens_cf_medium-wind-100m.grib"
    )

    headers = {}
    etag_file = f"{target}.etag"

    if os.path.exists(etag_file):
        with open(etag_file) as f:
            headers["If-None-Match"] = f.read().strip()

    r = requests.get(URL, headers=headers, stream=True, timeout=60)

    if r.status_code == 304:
        print("Already latest")
    else:
        r.raise_for_status()
        with open(target, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        if "ETag" in r.headers:
            with open(etag_file, "w") as f:
                f.write(r.headers["ETag"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract a GRIB field and write a COG GeoTIFF.")
    ap.add_argument("grib", nargs="?", default="aifs_ens_cf_medium-wind-100m.grib", help="Input GRIB path")
    ap.add_argument("--var", default="u100", help="Variable name inside GRIB (default: u100)")
    ap.add_argument("--out", default="u100_cog.tif", help="Output COG GeoTIFF path")
    ap.add_argument("--tmp", default="ugrd_temp_epsg4326.tif", help="Temporary EPSG:4326 GeoTIFF path")
    ap.add_argument("--target-crs", default="EPSG:3857", help="Target CRS (default: EPSG:3857)")
    ap.add_argument("--nodata", type=float, default=np.nan, help="Nodata value to write (default: NaN)")
    ap.add_argument("--raw", action="store_true", help="Use raw requests to download GRIB")
    args = ap.parse_args()

    if args.raw:
        rawRequests(target=args.grib)
    else:
        client = Client("ecmwf", beta=False, model="aifs-ens")

        parameters = ['100u', '100v','msl']
        grib_path = Path(args.grib)

        client.retrieve(
            date=0,
            time=0,
            step=12,
            stream="enfo",
            type="cf",
            levtype="sfc",
            param=parameters,
            target=grib_path
        )


    if not grib_path.exists():
        sys.exit(f"❌ GRIB not found: {grib_path}")

    tmp_tif = Path(args.tmp)
    out_cog = Path(args.out)

    # 1) Open GRIB
    try:
        ds = xr.open_dataset(grib_path, engine="cfgrib")
    except Exception as exc:
        sys.exit(f"❌ Unable to open GRIB with cfgrib: {exc}")

    if args.var not in ds:
        sys.exit(f"❌ Variable '{args.var}' not found. Available: {list(ds.data_vars)}")

    da = ds[args.var]

    # 2) Reduce to 2D lat/lon (pick first index for extra dims)
    lat_name = _find_coord_name(da, ("latitude", "lat"))
    lon_name = _find_coord_name(da, ("longitude", "lon"))

    # If there are extra dimensions (time/step/number/etc.), select the first value deterministically.
    extra_dims = [d for d in da.dims if d not in (lat_name, lon_name)]
    for d in extra_dims:
        da = da.isel({d: 0})

    da = da.squeeze()

    # 3) Normalize longitudes if they look like 0..360
    lons = da[lon_name].values
    if np.nanmax(lons) > 180.0:
        lon_norm, lon_sort_idx = normalise_longitudes(lons)
        da = da.isel({lon_name: lon_sort_idx}).assign_coords({lon_name: lon_norm})
    else:
        lon_norm = np.asarray(lons)

    # Ensure longitude ascending
    if lon_norm[0] > lon_norm[-1]:
        da = da.sortby(lon_name)
        lon_norm = da[lon_name].values

    # 4) Ensure latitude ascending (south->north)
    lats = da[lat_name].values
    if lats[0] > lats[-1]:
        da = da.sortby(lat_name)
        lats = da[lat_name].values

    # 5) Build transform and write EPSG:4326 GeoTIFF
    transform = build_geographic_transform(lon_norm, lats)

    data = da.values.astype(np.float32)
    nodata = None if (isinstance(args.nodata, float) and np.isnan(args.nodata)) else float(args.nodata)

    write_epsg4326_geotiff(tmp_tif, data, transform, nodata)

    # 6) Reproject + COG
    reproject_to_cog(tmp_tif, out_cog, args.target_crs, resampling=Resampling.bilinear)

    # 7) Diagnostics
    with rasterio.open(tmp_tif) as src:
        arr = src.read(1)
        print("\n🔎 EPSG:4326 temp GeoTIFF")
        print(f"  shape    : {arr.shape}")
        print(f"  dtype    : {arr.dtype}")
        print(f"  min / max: {np.nanmin(arr):.3f} / {np.nanmax(arr):.3f}")
        print(f"  CRS      : {src.crs}")
        print(f"  Transform: {src.transform}")

    with rasterio.open(out_cog) as src:
        arr = src.read(1, masked=True)
        print("\n✅ Output COG / tiled GeoTIFF")
        print(f"  path     : {out_cog}")
        print(f"  shape    : {arr.shape}")
        print(f"  dtype    : {arr.dtype}")
        print(f"  min / max: {arr.min():.3f} / {arr.max():.3f}")
        print(f"  CRS      : {src.crs}")
        print(f"  tiled    : {src.is_tiled}")
        print(f"  overviews: {src.overviews(1)}")

    # 8) Cleanup temp
    tmp_tif.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
