#!/usr/bin/env python3
"""
Wikidata → CSV + cleaned GeoJSON (merge points ≤ 1 km).

Dependencies:
    pip install requests pandas geopandas shapely
"""

import sys
from pathlib import Path

# ----------------------------------------------------------------------
# 1️⃣  Imports & dependency checks
# ----------------------------------------------------------------------
try:
    import requests
except ImportError:  # pragma: no cover
    print("Missing dependency. Run: pip install requests pandas geopandas")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    print("Missing dependency. Run: pip install pandas")
    sys.exit(1)

try:
    import geopandas as gpd
    from shapely import wkt
except ImportError:  # pragma: no cover
    print("Missing dependency. Run: pip install geopandas")
    sys.exit(1)


# ----------------------------------------------------------------------
# 2️⃣  SPARQL query (non‑aggregated version – fixed typo)
# ----------------------------------------------------------------------
QUERY = """
SELECT DISTINCT ?country ?name ?item ?geo ?itemType ?types
               ?itemInception ?itemStarttime ?itemServiceentry
               ?itemServiceretirement ?itemEndtime
WITH {
  SELECT ?item WHERE {
    { ?item wdt:P31/wdt:P279* wd:Q1739545. }   # nuclear power plant
    UNION { ?item wdt:P31/wdt:P279* wd:Q1438105. }   # research reactor
  }
} AS %allitems
WHERE {
  INCLUDE %allitems
  ?item wdt:P31/wdt:P279* wd:Q1739545.          # keep only power‑plant subclass
  ?item wdt:P625 ?geo.                         # geographic point
  ?item wdt:P31 ?itemType.                     # direct type (used for counting)

  OPTIONAL { ?item wdt:P17  ?itemCountry. }           # country
  OPTIONAL { ?item wdt:P729 ?itemServiceentry. }     # service entry date
  OPTIONAL { ?item wdt:P730 ?itemServiceretirement. }# service retirement date
  OPTIONAL { ?item wdt:P582 ?itemEndtime. }          # end of existence
  OPTIONAL { ?item wdt:P571 ?itemInception. }       # inception date
  OPTIONAL { ?item wdt:P580 ?itemStarttime. }        # start time (operational)

  # Build a readable “type” string (same logic as your original query)
  BIND( IF(EXISTS {?item wdt:P31/wdt:P279* wd:Q134447},   "Nuclear power plant, ",    "") AS ?type1)
  BIND( IF(EXISTS {?item wdt:P31/wdt:P279* wd:Q1438105}, "Nuclear research reactor, ","") AS ?type2)
  BIND( IF(EXISTS {?item wdt:P31/wdt:P279* wd:Q21493801},"Nuclear waste facility, ",   "") AS ?type3)
  BIND( IF(EXISTS {?item wdt:P31/wdt:P279* wd:Q14510027},"Fusion reactor, ",         "") AS ?type4)
  BIND( IF(EXISTS {?item wdt:P31/wdt:P279* wd:Q1298668},"Nuclear research project, ","") AS ?type5)
  BIND( IF(EXISTS {?item wdt:P31/wdt:P279* wd:Q1229765},"Vessel, ",                "") AS ?type6)

  BIND( CONCAT(?type1, ?type2, ?type3, ?type4, ?type5, ?type6) AS ?typeConcat)
  BIND( IF(STRLEN(?typeConcat)=0,
           "Nuclear facility (unspecified), ",
           ?typeConcat) AS ?typeTmp)
  BIND( SUBSTR(?typeTmp, 1, STRLEN(?typeTmp)-2) AS ?types)

  # Human‑readable labels for country and name
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en".
    ?itemCountry rdfs:label ?country.
    ?item rdfs:label ?name.
  }
}
ORDER BY ?country ?name
"""


# ----------------------------------------------------------------------
# 3️⃣  Helper – make sure the User‑Agent is pure ASCII (prevents latin‑1 error)
# ----------------------------------------------------------------------
def ascii_header(value: str) -> str:
    """Return an ASCII‑only version of *value*."""
    repl = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "--",
        "\u2212": "-",
    }
    for src, dst in repl.items():
        value = value.replace(src, dst)
    return value.encode("ascii", errors="ignore").decode()


# ----------------------------------------------------------------------
# 4️⃣  Core – run the SPARQL query via HTTP POST
# ----------------------------------------------------------------------
def run_sparql(query: str):
    url = "https://query.wikidata.org/sparql"
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": ascii_header("Lumo-client/1.0 (+https://proton.me/lumo)"),
    }
    payload = {"query": query}

    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover
        print(f"Network error while contacting Wikidata: {exc}")
        sys.exit(1)

    data = resp.json()
    rows = []
    for binding in data["results"]["bindings"]:
        flat = {var: val.get("value") for var, val in binding.items()}
        rows.append(flat)
    return rows


# ----------------------------------------------------------------------
# 5️⃣  Geometry helpers – clustering & merging
# ----------------------------------------------------------------------
def cluster_points(gdf, max_distance_m=1000):
    """
    Assign a cluster id to each point such that any two points
    ≤ max_distance_m apart belong to the same cluster.
    """
    # Work in a metric CRS (Web Mercator) for Euclidean distances ≈ metres.
    metric = gdf.to_crs(epsg=3857)

    # Spatial index for fast neighbor look‑ups.
    sindex = metric.sindex

    # Union‑Find (disjoint‑set) structure.
    parent = list(range(len(metric)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    # Join points that are within the distance threshold.
    for idx, geom in enumerate(metric.geometry):
        # Candidate neighbours (bounding‑box filter)
        candidates = list(sindex.intersection(geom.buffer(max_distance_m).bounds))
        for other in candidates:
            if other <= idx:          # avoid double work / self‑compare
                continue
            if geom.distance(metric.geometry.iloc[other]) <= max_distance_m:
                union(idx, other)

    # Compress to sequential cluster IDs (0, 1, 2, …)
    clusters = {}
    cluster_ids = []
    next_id = 0
    for i in range(len(parent)):
        root = find(i)
        if root not in clusters:
            clusters[root] = next_id
            next_id += 1
        cluster_ids.append(clusters[root])

    return cluster_ids


def merge_clusters(gdf, cluster_ids):
    """
    Collapse each cluster into a single feature:
      • geometry → centroid of the cluster (still EPSG:4326)
      • name   → semicolon‑separated list of distinct names
      • types  → semicolon‑separated list of distinct type strings
      • all other columns → first non‑null value in the cluster
    """
    gdf = gdf.copy()
    gdf["cluster"] = cluster_ids

    merged = []
    for cid, grp in gdf.groupby("cluster"):
        centroid = grp.geometry.unary_union.centroid

        # Helper to build a unique, semicolon‑separated string
        def uniq(series):
            vals = series.dropna().unique()
            return "; ".join(str(v) for v in vals) if vals.size else None

        row = {"geometry": centroid}
        for col in grp.columns:
            if col in {"geometry", "cluster"}:
                continue
            if col in {"name", "types"}:
                row[col] = uniq(grp[col])
            else:
                # first non‑null value (or None)
                row[col] = grp[col].dropna().iloc[0] if not grp[col].dropna().empty else None
        merged.append(row)

    merged_gdf = gpd.GeoDataFrame(merged, crs=gdf.crs)
    return merged_gdf


# ----------------------------------------------------------------------
# 6️⃣  Main routine – fetch, CSV, clean GeoJSON
# ----------------------------------------------------------------------
def main():
    print("Executing SPARQL query …")
    rows = run_sparql(QUERY)

    print(f"Retrieved {len(rows)} rows (first few shown):")
    for i, r in enumerate(rows[:5], start=1):
        print(f"{i}: {r}")

    # ---------- Pandas DataFrame (raw CSV) ----------
    df = pd.DataFrame(rows)

    # Convert ISO‑date strings to proper datetimes (optional, useful later)
    date_cols = [
        "itemInception",
        "itemStarttime",
        "itemServiceentry",
        "itemServiceretirement",
        "itemEndtime",
    ]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    raw_csv = Path("nuclear_facilities_raw.csv")
    df.to_csv(raw_csv, index=False)
    print(f"\nRaw CSV saved to {raw_csv.resolve()}")

    # ---------- GeoPandas GeoDataFrame ----------
    if "geo" not in df.columns:
        print("No 'geo' column – cannot build GeoJSON.")
        return

    gdf = gpd.GeoDataFrame(df.copy())
    gdf["geometry"] = gdf["geo"].apply(
        lambda wkt_str: wkt.loads(wkt_str) if isinstance(wkt_str, str) else None
    )
    # Drop rows without a valid geometry
    before = len(gdf)
    gdf = gdf.dropna(subset=["geometry"]).reset_index(drop=True)
    after = len(gdf)
    if before != after:
        print(f"Dropped {before - after} rows lacking a valid geometry.")

    # Ensure we are in EPSG:4326 (lon/lat)
    gdf.set_crs(epsg=4326, inplace=True)

    # ---------- Cluster & merge ----------
    print("\nClustering points (≤ 1 km)…")
    cluster_ids = cluster_points(gdf, max_distance_m=5000)   # 1 km threshold
    print(f"Found {len(set(cluster_ids))} clusters from {len(gdf)} original points.")

    merged_gdf = merge_clusters(gdf, cluster_ids)

    # ---------- Export cleaned files ----------
    clean_csv = Path("nuclear_facilities_clean.csv")
    merged_gdf.drop(columns="geometry").to_csv(clean_csv, index=False)
    print(f"Clean CSV (one row per merged cluster) saved to {clean_csv.resolve()}")

    clean_geojson = Path("nuclear_facilities_clean.geojson")
    merged_gdf.to_file(clean_geojson, driver="GeoJSON")
    print(f"Clean GeoJSON saved to {clean_geojson.resolve()}")


if __name__ == "__main__":
    main()
    